"""
API Routes - Twilio Integration

Adaptado para processar eventos JSON do Twilio Media Streams.
Inclui pré-processamento com Silero VAD para filtragem de ruído em telefonia.
"""

import asyncio
import base64
import json
import logging
import socket
import time
import audioop
import numpy as np
import torch
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from supabase import create_client

from src.core.config import get_settings, AgentConfig
from src.services.voice_assistant import VoiceAssistantWorker
from src.services.client_manager import ClientManager

logger = logging.getLogger(__name__)
settings = get_settings()

# ==============================================================================
# DIAGNÓSTICO DE STARTUP
# ==============================================================================
async def run_startup_diagnostics():
    """Executa bateria de testes de infraestrutura no startup"""
    logger.info("🩺 INICIANDO DIAGNÓSTICO DE SELF-TEST...")
    errors = []
    
    # 1. Teste de Rede
    try:
        host = "google.com"
        socket.create_connection((host, 80), timeout=2)
        logger.info(f"✅ Rede OK")
    except Exception as e:
        logger.error(f"❌ FALHA DE REDE: {e}")
        errors.append(str(e))

    # 2. Teste Supabase
    if not settings.is_development():
        try:
            sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
            sb.table('client_sip_numbers').select("sip_number", count="exact").limit(1).execute()
            logger.info(f"✅ Supabase OK")
        except Exception as e:
            logger.error(f"❌ FALHA SUPABASE: {e}")
            errors.append(str(e))
    
    # 3. Config Check
    try:
        AgentConfig("config/agent_config.json", env=settings.APP_ENV)
        logger.info(f"✅ Configuração OK")
    except Exception as e:
        logger.error(f"❌ FALHA CONFIG: {e}")
        errors.append(str(e))

    if errors:
        logger.critical("🚨 SELF-TEST COM ERROS!")
    else:
        logger.info("✨ SELF-TEST CONCLUÍDO")

# ==============================================================================
# INICIALIZAÇÃO GLOBAL (SAFE LOAD)
# ==============================================================================
worker = None
worker_task = None

try:
    base_agent_config = AgentConfig("config/agent_config.json", env=settings.APP_ENV)
    worker = VoiceAssistantWorker(agent_config=base_agent_config, settings=settings)
except Exception as e:
    logger.error(f"⚠️ Erro worker global: {e}")

# ==============================================================================
# LIFESPAN
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🟢 STARTUP: {settings.APP_ENV.upper()}")
    await run_startup_diagnostics()
    
    global worker_task
    if settings.is_development() and worker:
        worker_task = asyncio.create_task(worker.connect_and_run())
        logger.info("🎙️ Worker dev iniciado")
    
    yield
    
    logger.info("🔴 SHUTDOWN")
    if worker: worker.shutdown()
    if worker_task: 
        worker_task.cancel()
        try: await worker_task
        except: pass

app = FastAPI(title="Azure VoiceLive Agent", lifespan=lifespan)

# ==============================================================================
# HTTP ENDPOINTS
# ==============================================================================
@app.get("/health")
async def health_check():
    # Log condicional para monitorar staging
    if not settings.is_production():
        logger.info(f"💓 HEALTH CHECK RECEBIDO!")
    
    status = "ready"
    if settings.is_development() and worker:
        status = "connected" if worker.connection else "initializing"
    
    return {"status": "ok", "env": settings.APP_ENV, "worker": status}

@app.get("/")
async def root():
    return {"message": "Twilio Media Stream Ready", "docs": "/docs"}

# ==============================================================================
# WEBSOCKET - TWILIO MEDIA STREAMS (COM SILERO VAD)
# ==============================================================================
@app.websocket("/ws/audio/{sip_number}")
async def audio_stream(websocket: WebSocket, sip_number: str):
    """Integração com Twilio Media Streams e Filtro VAD"""
    await websocket.accept()
    logger.info(f"🔌 Conexão Twilio recebida para: {sip_number}")
    
    session_worker = None
    session_task = None
    stream_sid = None  # ID da chamada na Twilio
    
    # --- CONFIGURAÇÃO DO VAD LOCAL ---
    VAD_TIMEOUT_MS = 1500      # Tempo de silêncio para considerar fim de turno (1.5s)
    SILENCE_THRESHOLD = 0.5    # Probabilidade mínima para considerar voz (0.0 a 1.0)
    SAMPLE_RATE = 8000         # Taxa de amostragem do G.711 (Telefonia)
    
    vad_model = None
    
    try:
        # 1. Carregar Silero VAD
        # O download ocorre na primeira execução e fica em cache
        logger.info("🧠 Carregando modelo Silero VAD...")
        vad_model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                          model='silero_vad',
                                          force_reload=False,
                                          trust_repo=True)
        # Desempacota utils apenas se necessário, mas para este caso uso básico basta o model
        logger.info("✅ Silero VAD carregado com sucesso")

        # 2. Configuração do Cliente
        client_manager = ClientManager(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        client_config = client_manager.get_client_config(sip_number)
        
        if not client_config:
            logger.warning(f"⚠️ Cliente não encontrado: {sip_number}")
            await websocket.close(code=4000)
            return

        logger.info(f"✅ Config carregada. Iniciando worker...")

        # 3. Callbacks adaptados para Twilio
        async def send_audio_to_twilio(audio_data: bytes):
            """Empacota áudio no formato JSON da Twilio"""
            if not stream_sid: return
            try:
                payload = base64.b64encode(audio_data).decode('utf-8')
                message = {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload}
                }
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"❌ Erro envio Twilio: {e}")

        async def send_clear_buffer():
            """Envia evento 'clear' para Twilio (Interrupção/Barge-in)"""
            if not stream_sid: return
            try:
                await websocket.send_json({
                    "event": "clear",
                    "streamSid": stream_sid
                })
                logger.info("🛑 Buffer Twilio limpo (Interrupção)")
            except: pass

        # 4. Inicializa Worker
        session_worker = VoiceAssistantWorker(
            agent_config=client_config,
            settings=settings,
            audio_output_handler=send_audio_to_twilio,
            interruption_handler=send_clear_buffer
        )
        session_task = asyncio.create_task(session_worker.connect_and_run())
        
        # Variáveis de Estado do VAD
        last_speech_time = 0.0
        speech_detected_flag = False
        
        # 5. Loop de Processamento Twilio
        while True:
            try:
                # Twilio envia TEXTO contendo JSON
                message = await websocket.receive_text()
                data = json.loads(message)
                event_type = data.get("event")

                if event_type == "media":
                    # Extrai payload (G.711 u-law base64)
                    payload = data["media"]["payload"]
                    
                    if session_worker.connection:
                        try:
                            # --- PRÉ-PROCESSAMENTO VAD ---
                            
                            # A. Decodifica Base64 para bytes puros (u-law)
                            chunk_ulaw = base64.b64decode(payload)
                            
                            # B. Converte u-law para PCM 16-bit (Linear)
                            # Silero precisa de PCM linear, não u-law comprimido
                            chunk_pcm = audioop.ulaw2lin(chunk_ulaw, 2)
                            
                            # C. Prepara Tensor para o PyTorch
                            # Normaliza int16 para float32 entre -1.0 e 1.0
                            audio_float32 = np.frombuffer(chunk_pcm, dtype=np.int16).astype(np.float32) / 32768.0
                            tensor = torch.from_numpy(audio_float32)
                            
                            # D. Executa detecção
                            speech_prob = vad_model(tensor, SAMPLE_RATE).item()
                            
                            # --- LÓGICA DE GATE ---
                            
                            if speech_prob > SILENCE_THRESHOLD:
                                # >> VOZ DETECTADA <<
                                
                                # Envia o payload original (G.711) para o Azure
                                # Nota: O Azure recebe o áudio original, não o convertido
                                await session_worker.connection.input_audio_buffer.append(audio=payload)
                                
                                # Atualiza estado
                                last_speech_time = time.time()
                                if not speech_detected_flag:
                                    speech_detected_flag = True
                                    logger.info("🗣️ VAD Local: Fala detectada")
                                    
                            else:
                                # >> SILÊNCIO DETECTADO <<
                                # Não envia nada para o Azure (economiza tokens e evita ruído)
                                
                                # Verifica Timeout de Silêncio para encerrar turno
                                current_time = time.time()
                                if speech_detected_flag and (current_time - last_speech_time) * 1000 > VAD_TIMEOUT_MS:
                                    
                                    logger.info(f"🛑 VAD Local: Silêncio > {VAD_TIMEOUT_MS}ms. Fechando turno.")
                                    
                                    # Força o Azure a processar o que ouviu até agora
                                    # O 'clear' aqui pode ser usado se quiser limpar o buffer, 
                                    # mas para comitar o áudio, o Azure geralmente usa o VAD dele.
                                    # Como estamos simulando VAD, o Azure ficará esperando.
                                    # Se o VAD do Azure estiver desligado (threshold 0.01), ele processa contínuo.
                                    # Uma forma de forçar resposta é enviar um commit manual se a API permitir,
                                    # ou confiar que o Azure VAD (configurado permissivo) vai processar o fluxo enviado.
                                    
                                    # Reset do flag
                                    speech_detected_flag = False
                                    last_speech_time = 0.0

                        except Exception as e_vad:
                            # Em caso de erro no VAD, fallback: envia áudio direto
                            logger.error(f"⚠️ Erro VAD: {e_vad}")
                            await session_worker.connection.input_audio_buffer.append(audio=payload)
                
                elif event_type == "start":
                    stream_sid = data["start"]["streamSid"]
                    logger.info(f"📞 Stream iniciado (SID: {stream_sid})")
                
                elif event_type == "stop":
                    logger.info("📞 Chamada encerrada pela Twilio")
                    break
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"❌ Erro processamento msg: {e}")
                break

    except Exception as e:
        logger.critical(f"❌ Erro sessão: {e}", exc_info=True)
    finally:
        if session_worker: session_worker.shutdown()
        if session_task: session_task.cancel()
        logger.info(f"✅ Sessão finalizada: {sip_number}")