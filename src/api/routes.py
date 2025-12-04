"""
API Routes - Twilio Integration

Adaptado para processar eventos JSON do Twilio Media Streams.
"""

import asyncio
import base64
import json
import logging
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from supabase import create_client

from src.core.config import get_settings, AgentConfig
from src.services.voice_assistant import VoiceAssistantWorker
from src.services.client_manager import ClientManager

logger = logging.getLogger(__name__)
settings = get_settings()

# ==============================================================================
# DIAGNÓSTICO DE STARTUP (MANTIDO IGUAL)
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
# WEBSOCKET - TWILIO MEDIA STREAMS
# ==============================================================================
@app.websocket("/ws/audio/{sip_number}")
async def audio_stream(websocket: WebSocket, sip_number: str):
    """Integração com Twilio Media Streams"""
    await websocket.accept()
    logger.info(f"🔌 Conexão Twilio recebida para: {sip_number}")
    
    session_worker = None
    session_task = None
    stream_sid = None  # ID da chamada na Twilio
    
    try:
        # 1. Configuração do Cliente
        client_manager = ClientManager(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        client_config = client_manager.get_client_config(sip_number)
        
        if not client_config:
            logger.warning(f"⚠️ Cliente não encontrado: {sip_number}")
            await websocket.close(code=4000)
            return

        logger.info(f"✅ Config carregada. Iniciando worker...")

        # 2. Callbacks adaptados para Twilio
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

        # 3. Inicializa Worker
        session_worker = VoiceAssistantWorker(
            agent_config=client_config,
            settings=settings,
            audio_output_handler=send_audio_to_twilio,
            interruption_handler=send_clear_buffer
        )
        session_task = asyncio.create_task(session_worker.connect_and_run())
        
        # 4. Loop de Processamento Twilio
        while True:
            try:
                # Twilio envia TEXTO contendo JSON
                message = await websocket.receive_text()
                data = json.loads(message)
                event_type = data.get("event")

                if event_type == "media":
                    # Extrai áudio e envia para Azure
                    if session_worker.connection:
                        audio_chunk = data["media"]["payload"]
                        # Nota: Azure espera base64 string, que é exatamente o que temos
                        await session_worker.connection.input_audio_buffer.append(audio=audio_chunk)
                
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