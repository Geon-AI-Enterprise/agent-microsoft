"""
API Routes - Twilio Integration com Transcoding (8kHz <-> 24kHz)
Corrige: Erro de Sample Rate e Falha de Interrupção
"""

import asyncio
import base64
import json
import logging
import audioop
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager

from src.core.config import get_settings
from src.services.voice_assistant import VoiceAssistantWorker
from src.services.client_manager import ClientManager

logger = logging.getLogger(__name__)
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🟢 STARTUP: {settings.APP_ENV.upper()}")
    yield
    logger.info("🔴 SHUTDOWN")

app = FastAPI(title="Azure VoiceLive Agent", lifespan=lifespan)

@app.get("/health")
async def health_check():
    return {"status": "ok", "env": settings.APP_ENV}

@app.websocket("/ws/audio/{sip_number}")
async def audio_stream(websocket: WebSocket, sip_number: str):
    await websocket.accept()
    logger.info(f"🔌 Conexão Twilio: {sip_number}")

    session_worker = None
    worker_task = None
    stream_sid = None
    
    # Estados para Transcoding (audioop)
    # state_in: mantem estado do filtro de upsampling
    # state_out: mantem estado do filtro de downsampling
    state_in = None  
    state_out = None

    try:
        # 1. Busca Configuração
        client_manager = ClientManager(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        client_config = client_manager.get_client_config(sip_number)

        if not client_config:
            logger.warning(f"⚠️ Cliente não encontrado: {sip_number}")
            await websocket.close(code=4000)
            return

        # 2. Callback de Saída (Azure 24k -> Twilio 8k)
        async def send_audio_to_twilio(audio_data_24k: bytes):
            nonlocal state_out, stream_sid
            if not stream_sid: return
            
            try:
                # Decodifica Base64 do Azure (PCM16 24kHz)
                pcm_24k = base64.b64decode(audio_data_24k)
                
                # Downsample: 24000 -> 8000
                # audioop.ratecv(fragment, width, nchannels, inrate, outrate, state)
                pcm_8k, state_out = audioop.ratecv(pcm_24k, 2, 1, 24000, 8000, state_out)
                
                # Converte PCM 8k -> Mu-Law
                ulaw_8k = audioop.lin2ulaw(pcm_8k, 2)
                
                # Codifica para enviar ao Twilio
                payload = base64.b64encode(ulaw_8k).decode('utf-8')
                
                await websocket.send_json({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload}
                })
            except Exception as e:
                logger.error(f"Erro transcoding OUT: {e}")

        async def send_clear_buffer():
            if not stream_sid: return
            try:
                await websocket.send_json({"event": "clear", "streamSid": stream_sid})
            except: pass

        # 3. Inicializa Worker
        session_worker = VoiceAssistantWorker(
            agent_config=client_config,
            settings=settings,
            audio_output_handler=send_audio_to_twilio,
            interruption_handler=send_clear_buffer
        )
        worker_task = asyncio.create_task(session_worker.connect_and_run())

        # 4. Loop de Entrada (Twilio 8k -> Azure 24k)
        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                event_type = data.get("event")

                if event_type == "media":
                    payload = data["media"]["payload"]
                    
                    if session_worker.connection:
                        # Decodifica Base64 Twilio (Mu-Law 8k)
                        ulaw_8k = base64.b64decode(payload)
                        
                        # Converte Mu-Law -> PCM 8k
                        pcm_8k = audioop.ulaw2lin(ulaw_8k, 2)
                        
                        # Upsample: 8000 -> 24000
                        pcm_24k, state_in = audioop.ratecv(pcm_8k, 2, 1, 8000, 24000, state_in)
                        
                        # Codifica para Base64 (Azure espera string base64)
                        base64_24k = base64.b64encode(pcm_24k).decode('utf-8')
                        
                        # Envia para Azure
                        await session_worker.ingest_audio(base64_24k)

                elif event_type == "start":
                    stream_sid = data["start"]["streamSid"]
                elif event_type == "stop":
                    break
                    
            except WebSocketDisconnect:
                break
            except Exception:
                break

    except Exception as e:
        logger.critical(f"❌ Erro sessão: {e}")
    finally:
        if session_worker: session_worker.shutdown()
        if worker_task: worker_task.cancel()