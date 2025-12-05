"""
API Routes - Twilio Integration

Adaptado para processar eventos JSON do Twilio Media Streams.
Inclui pré-processamento com Silero VAD (com Buffering) para filtragem de ruído.
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
from typing import List

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
# WEBSOCKET - TWILIO MEDIA STREAMS (COM SILERO VAD BUFFERIZADO)
# ==============================================================================
@app.websocket("/ws/audio/{sip_number}")
async def audio_stream(websocket: WebSocket, sip_number: str):
    """Integração com Twilio Media Streams e Filtro VAD"""
    await websocket.accept()
    logger.info(f"🔌 Conexão Twilio recebida para: {sip_number}")
    
    session_worker = None
    session_task = None
    stream_sid = None
    
    # --- CONFIGURAÇÃO DO VAD LOCAL ---
    # Silero requer chunks exatos de 256, 512 ou 768 amostras para 8kHz
    VAD_WINDOW_SAMPLES = 256   # 32ms (Mínimo suportado pelo Silero 8k)
    VAD_WINDOW_BYTES = VAD_WINDOW_SAMPLES * 2  # 16-bit PCM = 2 bytes por amostra
    
    VAD_TIMEOUT_MS = 1500      # Tempo de silêncio para considerar fim de turno
    SILENCE_THRESHOLD = 0.5    # Sensibilidade
    SAMPLE_RATE = 8000         # Taxa Twilio G.711
    
    vad_model = None
    
    try:
        logger.info("🧠 Carregando modelo Silero VAD...")
        vad_model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                          model='silero_vad',
                                          force_reload=False,
                                          trust_repo=True)
        logger.info("✅ Silero VAD carregado com sucesso")

        # Configuração do Cliente
        client_manager = ClientManager(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        client_config = client_manager.get_client_config(sip_number)
        
        if not client_config:
            logger.warning(f"⚠️ Cliente não encontrado: {sip_number}")
            await websocket.close(code=4000)
            return

        logger.info(f"✅ Config carregada. Iniciando worker...")

        # Callbacks
        async def send_audio_to_twilio(audio_data: bytes):
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
            if not stream_sid: return
            try:
                await websocket.send_json({
                    "event": "clear",
                    "streamSid": stream_sid
                })
                logger.info("🛑 Buffer Twilio limpo (Interrupção)")
            except: pass

        # Inicializa Worker
        session_worker = VoiceAssistantWorker(
            agent_config=client_config,
            settings=settings,
            audio_output_handler=send_audio_to_twilio,
            interruption_handler=send_clear_buffer
        )
        session_task = asyncio.create_task(session_worker.connect_and_run())
        
        # --- BUFFERS DE VAD ---
        # vad_buffer: Acumula bytes PCM para completar a janela do VAD
        vad_buffer = bytearray()
        
        # packet_queue: Acumula os payloads originais da Twilio enquanto bufferizamos o VAD
        # Estrutura: List[str] (lista de payloads base64)
        packet_queue: List[str] = []
        
        # Estado
        last_speech_time = 0.0
        speech_detected_flag = False
        
        # Loop Principal
        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                event_type = data.get("event")

                if event_type == "media":
                    payload = data["media"]["payload"]
                    
                    if session_worker.connection:
                        try:
                            # 1. Decodificar e Converter
                            chunk_ulaw = base64.b64decode(payload)
                            chunk_pcm = audioop.ulaw2lin(chunk_ulaw, 2)
                            
                            # 2. Adicionar aos Buffers
                            vad_buffer.extend(chunk_pcm)
                            packet_queue.append(payload)
                            
                            # 3. Processar VAD se tivermos dados suficientes
                            # Processamos em janelas exatas de 256 amostras (512 bytes)
                            while len(vad_buffer) >= VAD_WINDOW_BYTES:
                                
                                # Extrai janela para análise
                                window_pcm = vad_buffer[:VAD_WINDOW_BYTES]
                                vad_buffer = vad_buffer[VAD_WINDOW_BYTES:] # Remove do buffer
                                
                                # Prepara Tensor
                                audio_float32 = np.frombuffer(window_pcm, dtype=np.int16).astype(np.float32) / 32768.0
                                tensor = torch.from_numpy(audio_float32)
                                
                                # Executa VAD
                                speech_prob = vad_model(tensor, SAMPLE_RATE).item()
                                
                                if speech_prob > SILENCE_THRESHOLD:
                                    last_speech_time = time.time()
                                    if not speech_detected_flag:
                                        speech_detected_flag = True
                                        logger.info("🗣️ VAD: Voz detectada")

                            # 4. Decisão de Envio (Gate)
                            # Se detectou voz recentemente (dentro do timeout), libera a fila
                            current_time = time.time()
                            is_active_speech = speech_detected_flag and (current_time - last_speech_time) * 1000 < VAD_TIMEOUT_MS
                            
                            if is_active_speech:
                                # Envia todos os pacotes acumulados na fila
                                while packet_queue:
                                    p = packet_queue.pop(0)
                                    await session_worker.connection.input_audio_buffer.append(audio=p)
                            else:
                                # Se excedeu o timeout, fecha o turno e limpa fila
                                if speech_detected_flag:
                                    logger.info(f"🛑 VAD: Silêncio > {VAD_TIMEOUT_MS}ms. Fechando turno.")
                                    # Limpa buffer do Azure para forçar resposta (commit implícito pelo silêncio)
                                    # Dependendo da config do Azure VAD, pode precisar de um commit manual,
                                    # mas parar de enviar áudio geralmente funciona se o threshold do Azure estiver baixo.
                                    await session_worker.connection.input_audio_buffer.commit() 
                                    
                                    speech_detected_flag = False
                                
                                # Limpa a fila de pacotes (descarta o ruído/silêncio)
                                packet_queue.clear()

                        except Exception as e_vad:
                            logger.error(f"⚠️ Erro VAD Loop: {e_vad}")
                            # Fallback em caso de erro crítico: envia tudo
                            await session_worker.connection.input_audio_buffer.append(audio=payload)
                
                elif event_type == "start":
                    stream_sid = data["start"]["streamSid"]
                    logger.info(f"📞 Stream iniciado (SID: {stream_sid})")
                
                elif event_type == "stop":
                    logger.info("📞 Chamada encerrada")
                    break
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"❌ Erro processamento: {e}")
                break

    except Exception as e:
        logger.critical(f"❌ Erro sessão: {e}", exc_info=True)
    finally:
        if session_worker: session_worker.shutdown()
        if session_task: session_task.cancel()
        logger.info(f"✅ Sessão finalizada: {sip_number}")