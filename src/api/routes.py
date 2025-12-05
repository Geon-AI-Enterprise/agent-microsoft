"""
API Routes - Twilio Integration

Adaptado para processar eventos JSON do Twilio Media Streams.
Inclui pré-processamento com WebRTC VAD (Leve e Eficiente) e proteções de robustez.
"""

import asyncio
import base64
import json
import logging
import socket
import time
import audioop
import webrtcvad
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
# DIAGNÓSTICO DE STARTUP (MANTIDO)
# ==============================================================================
async def run_startup_diagnostics():
    logger.info("🩺 INICIANDO DIAGNÓSTICO...")
    try:
        vad = webrtcvad.Vad(3)
        frame = b'\x00' * 320
        assert vad.is_speech(frame, 8000) is False
        logger.info(f"✅ WebRTC VAD OK")
    except Exception as e:
        logger.error(f"❌ FALHA VAD: {e}")

# ==============================================================================
# INICIALIZAÇÃO GLOBAL (MANTIDO)
# ==============================================================================
worker = None
worker_task = None

try:
    base_agent_config = AgentConfig("config/agent_config.json", env=settings.APP_ENV)
    worker = VoiceAssistantWorker(agent_config=base_agent_config, settings=settings)
except Exception as e:
    logger.error(f"⚠️ Erro worker global: {e}")

# ==============================================================================
# LIFESPAN (MANTIDO)
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
# HTTP ENDPOINTS (MANTIDO)
# ==============================================================================
@app.get("/health")
async def health_check():
    return {"status": "ok", "env": settings.APP_ENV}

@app.get("/")
async def root():
    return {"message": "Twilio Media Stream Ready", "docs": "/docs"}

# ==============================================================================
# WEBSOCKET - TWILIO (COM CORREÇÕES DE ESTABILIDADE)
# ==============================================================================
@app.websocket("/ws/audio/{sip_number}")
async def audio_stream(websocket: WebSocket, sip_number: str):
    await websocket.accept()
    logger.info(f"🔌 Conexão Twilio recebida: {sip_number}")
    
    session_worker = None
    session_task = None
    stream_sid = None
    
    # --- CONFIGURAÇÃO VAD ---
    vad = webrtcvad.Vad(3)
    FRAME_SIZE_BYTES = 320 # 20ms @ 8000Hz PCM16
    SAMPLE_RATE = 8000
    
    # Lógica de Silêncio
    VAD_TIMEOUT_MS = 1000 
    
    # CORREÇÃO 1: Tempo de aquecimento (Warmup)
    # Ignora áudio nos primeiros 3 segundos para proteger a saudação e evitar ruído inicial
    AUDIO_IGNORE_SECONDS = 3.0 
    start_time = time.time()
    
    try:
        # Configuração do Cliente
        client_manager = ClientManager(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        client_config = client_manager.get_client_config(sip_number)
        
        if not client_config:
            logger.warning(f"⚠️ Cliente não encontrado: {sip_number}")
            await websocket.close(code=4000)
            return

        # Callbacks
        async def send_audio_to_twilio(audio_data: bytes):
            if not stream_sid: return
            try:
                payload = base64.b64encode(audio_data).decode('utf-8')
                await websocket.send_json({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload}
                })
            except: pass

        async def send_clear_buffer():
            if not stream_sid: return
            try:
                await websocket.send_json({"event": "clear", "streamSid": stream_sid})
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
        
        # --- BUFFERS ---
        pcm_buffer = bytearray()
        packet_queue: List[str] = []
        
        # Estado VAD
        last_speech_time = 0.0
        is_speaking = False
        bytes_sent_in_turn = 0 # Contador para evitar commit vazio
        
        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                event_type = data.get("event")

                if event_type == "media":
                    # CORREÇÃO 1: Ignora áudio durante período de warmup (saudação)
                    if (time.time() - start_time) < AUDIO_IGNORE_SECONDS:
                        continue

                    payload = data["media"]["payload"]
                    
                    if session_worker.connection:
                        # 1. Decodificar e Converter
                        chunk_ulaw = base64.b64decode(payload)
                        chunk_pcm = audioop.ulaw2lin(chunk_ulaw, 2)
                        
                        # 2. Bufferizar
                        pcm_buffer.extend(chunk_pcm)
                        packet_queue.append(payload)
                        
                        # 3. Processar frames exatos
                        while len(pcm_buffer) >= FRAME_SIZE_BYTES:
                            frame = pcm_buffer[:FRAME_SIZE_BYTES]
                            pcm_buffer = pcm_buffer[FRAME_SIZE_BYTES:]
                            
                            if vad.is_speech(frame, SAMPLE_RATE):
                                last_speech_time = time.time()
                                if not is_speaking:
                                    is_speaking = True
                                    bytes_sent_in_turn = 0 # Novo turno
                                    logger.info("🗣️ Voz detectada")
                        
                        # 4. Decisão de Envio
                        current_time = time.time()
                        silence_duration = (current_time - last_speech_time) * 1000
                        
                        if silence_duration < VAD_TIMEOUT_MS:
                            # Turno ativo: Envia fila
                            while packet_queue:
                                p = packet_queue.pop(0)
                                await session_worker.connection.input_audio_buffer.append(audio=p)
                                bytes_sent_in_turn += len(p) # Contabiliza bytes base64
                        else:
                            # Silêncio detectado
                            if is_speaking:
                                logger.info(f"🛑 Silêncio ({silence_duration:.0f}ms). Tentando fechar turno...")
                                
                                # CORREÇÃO 2: Proteção contra "Buffer too small"
                                # Só faz commit se enviamos dados suficientes (ex: > 1kb de base64)
                                if bytes_sent_in_turn > 1000:
                                    try:
                                        await session_worker.connection.input_audio_buffer.commit()
                                        logger.info("✅ Turno comitado com sucesso")
                                    except Exception as e:
                                        # Captura erro silenciosamente para não derrubar a conexão
                                        logger.warning(f"⚠️ Commit ignorado: {e}")
                                else:
                                    logger.info("⏭️ Turno muito curto/ruído. Ignorando commit.")
                                    # Opcional: Limpar buffer do Azure se possível, ou apenas ignorar
                                    try: await session_worker.connection.input_audio_buffer.clear()
                                    except: pass
                                
                                is_speaking = False
                                bytes_sent_in_turn = 0
                            
                            packet_queue.clear()

                elif event_type == "start":
                    stream_sid = data["start"]["streamSid"]
                    logger.info(f"📞 Stream iniciado (SID: {stream_sid})")
                
                elif event_type == "stop":
                    logger.info("📞 Chamada encerrada")
                    break
                    
            except WebSocketDisconnect:
                logger.info("🔌 WebSocket desconectado")
                break
            except Exception as e:
                logger.error(f"❌ Erro loop principal: {e}")
                # Não quebra o loop por erros menores
                continue

    except Exception as e:
        logger.critical(f"❌ Erro crítico sessão: {e}", exc_info=True)
    finally:
        if session_worker: session_worker.shutdown()
        if session_task: session_task.cancel()
        logger.info(f"✅ Sessão finalizada: {sip_number}")