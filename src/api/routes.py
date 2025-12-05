"""
API Routes - Twilio Integration

Adaptado para processar eventos JSON do Twilio Media Streams.
Inclui pré-processamento com WebRTC VAD (Leve e Eficiente).
"""

import asyncio
import base64
import json
import logging
import socket
import time
import audioop
import webrtcvad  # <--- A nova biblioteca leve
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
    logger.info("🩺 INICIANDO DIAGNÓSTICO...")
    try:
        # Teste rápido do WebRTC VAD
        vad = webrtcvad.Vad(3)
        # Cria um frame de silêncio de 20ms a 8000Hz (320 bytes)
        frame = b'\x00' * 320
        assert vad.is_speech(frame, 8000) is False
        logger.info(f"✅ WebRTC VAD OK")
    except Exception as e:
        logger.error(f"❌ FALHA VAD: {e}")

    # ... (restante dos diagnósticos de rede e supabase) ...
    # Pode manter o código original de teste de rede e supabase aqui

# ==============================================================================
# INICIALIZAÇÃO E LIFESPAN (MANTIDOS IGUAIS)
# ==============================================================================
worker = None
worker_task = None

# ... (Manter código de inicialização global e lifespan igual ao anterior) ...
# Vou resumir para focar na mudança principal, mas você deve manter o código existente.

@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_startup_diagnostics()
    yield
    if worker: worker.shutdown()

app = FastAPI(title="Azure VoiceLive Agent", lifespan=lifespan)

# ... (Endpoints HTTP /health e root mantidos iguais) ...
@app.get("/health")
async def health_check():
    return {"status": "ok", "env": settings.APP_ENV}

@app.get("/")
async def root():
    return {"message": "Twilio Media Stream Ready", "docs": "/docs"}

# ==============================================================================
# WEBSOCKET - TWILIO (COM WEBRTC VAD)
# ==============================================================================
@app.websocket("/ws/audio/{sip_number}")
async def audio_stream(websocket: WebSocket, sip_number: str):
    await websocket.accept()
    logger.info(f"🔌 Conexão Twilio: {sip_number}")
    
    session_worker = None
    session_task = None
    stream_sid = None
    
    # --- CONFIGURAÇÃO VAD ---
    # Modo 3 é o mais agressivo (filtra mais ruído)
    vad = webrtcvad.Vad(3)
    
    # Twilio (G.711) = 8000Hz
    # WebRTC exige frames de 10, 20 ou 30ms.
    # 20ms a 8000Hz = 160 amostras.
    # Em PCM 16-bit (2 bytes/amostra), 160 * 2 = 320 bytes.
    FRAME_SIZE_BYTES = 320 
    SAMPLE_RATE = 8000
    
    # Lógica de Silêncio
    VAD_TIMEOUT_MS = 1000 # 1 segundo de silêncio fecha o turno
    
    try:
        # ... (Lógica de carregar config do cliente - Mantida igual) ...
        client_manager = ClientManager(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        client_config = client_manager.get_client_config(sip_number)
        if not client_config:
            await websocket.close(code=4000)
            return

        # ... (Callbacks send_audio e send_clear - Mantidos iguais) ...
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
        
        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                event_type = data.get("event")

                if event_type == "media":
                    payload = data["media"]["payload"]
                    
                    if session_worker.connection:
                        # 1. Decodificar e Converter
                        chunk_ulaw = base64.b64decode(payload)
                        chunk_pcm = audioop.ulaw2lin(chunk_ulaw, 2)
                        
                        # 2. Bufferizar PCM para análise
                        pcm_buffer.extend(chunk_pcm)
                        packet_queue.append(payload)
                        
                        # 3. Processar frames de tamanho exato (320 bytes = 20ms)
                        while len(pcm_buffer) >= FRAME_SIZE_BYTES:
                            frame = pcm_buffer[:FRAME_SIZE_BYTES]
                            pcm_buffer = pcm_buffer[FRAME_SIZE_BYTES:] # Remove do buffer
                            
                            # VAD Check (Retorna True/False instantaneamente)
                            if vad.is_speech(frame, SAMPLE_RATE):
                                last_speech_time = time.time()
                                if not is_speaking:
                                    is_speaking = True
                                    logger.info("🗣️ Voz detectada")
                        
                        # 4. Decisão de Envio
                        # Se falou nos últimos X ms, envia tudo que está na fila
                        current_time = time.time()
                        silence_duration = (current_time - last_speech_time) * 1000
                        
                        if silence_duration < VAD_TIMEOUT_MS:
                            # Estamos em um turno de fala ativo
                            while packet_queue:
                                p = packet_queue.pop(0)
                                await session_worker.connection.input_audio_buffer.append(audio=p)
                        else:
                            # Silêncio prolongado
                            if is_speaking:
                                logger.info(f"🛑 Silêncio ({silence_duration:.0f}ms). Turno Fechado.")
                                # Limpa buffer do Azure para garantir que ele processe o que recebeu
                                await session_worker.connection.input_audio_buffer.commit()
                                is_speaking = False
                            
                            # Descarta o áudio da fila (é ruído/silêncio)
                            packet_queue.clear()

                elif event_type == "start":
                    stream_sid = data["start"]["streamSid"]
                elif event_type == "stop":
                    break
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"❌ Erro loop: {e}")
                break

    except Exception as e:
        logger.critical(f"❌ Erro crítico: {e}")
    finally:
        if session_worker: session_worker.shutdown()
        if session_task: session_task.cancel()
        logger.info(f"✅ Sessão finalizada: {sip_number}")