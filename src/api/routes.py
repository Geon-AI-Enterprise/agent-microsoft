"""
API Routes - Twilio Integration (Clean Architecture)

Responsabilidade:
- Gerenciar ciclo de vida do WebSocket (Conectar/Desconectar)
- Orquestrar fluxo de dados: Twilio <-> Transcoder <-> Azure Worker
- NÃO realiza processamento de áudio (delegado ao Transcoder)
"""

import asyncio
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager

from src.core.config import get_settings
from src.services.voice_assistant import VoiceAssistantWorker
from src.services.client_manager import ClientManager
from src.services.transcoder import AudioTranscoder

logger = logging.getLogger(__name__)
settings = get_settings()

# ==============================================================================
# LIFESPAN & SETUP
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🟢 STARTUP: {settings.APP_ENV.upper()}")
    yield
    logger.info("🔴 SHUTDOWN")

app = FastAPI(title="Azure VoiceLive Agent", lifespan=lifespan)

@app.get("/health")
async def health_check():
    return {"status": "ok", "env": settings.APP_ENV}

# ==============================================================================
# WEBSOCKET CONTROLLER
# ==============================================================================
@app.websocket("/ws/audio/{sip_number}")
async def audio_stream(websocket: WebSocket, sip_number: str):
    """
    Controlador principal da sessão de voz.
    Conecta o telefone (Twilio) à inteligência (Azure) usando o Transcoder como ponte.
    """
    await websocket.accept()
    logger.info(f"🔌 Conexão Twilio recebida: {sip_number}")

    session_worker = None
    worker_task = None
    stream_sid = None
    
    # Instancia o especialista em áudio (Isolamento de Responsabilidade)
    transcoder = AudioTranscoder()

    try:
        # 1. Identificação do Cliente (Banco de Dados)
        client_manager = ClientManager(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        client_config = client_manager.get_client_config(sip_number)

        if not client_config:
            logger.warning(f"⚠️ Cliente não encontrado ou inativo: {sip_number}")
            await websocket.close(code=4000)
            return

        # 2. Callback de Saída: Azure (24k) -> Transcoder -> Twilio (8k)
        async def handle_azure_audio(audio_data_24k: str):
            nonlocal stream_sid
            if not stream_sid: return
            
            # Delega a conversão complexa para o Transcoder
            payload_8k = transcoder.azure_to_twilio(audio_data_24k)
            
            if payload_8k:
                try:
                    await websocket.send_json({
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": payload_8k}
                    })
                except Exception as e:
                    logger.warning(f"Falha envio WebSocket: {e}")

        # Callback de Interrupção
        async def handle_interruption():
            if not stream_sid: 
                logger.warning("⚠️ Tentativa de limpar buffer sem Stream SID")
                return
            try:
                transcoder.clear()
                await websocket.send_json({
                    "event": "clear", 
                    "streamSid": stream_sid
                })
                logger.info("⚡ Buffer de áudio limpo (Barge-in)")
            except Exception as e:
                logger.error(f"❌ Falha ao limpar buffer de áudio: {e}") 

        # 3. Inicializa o Worker do Azure (Inteligência)
        session_worker = VoiceAssistantWorker(
            agent_config=client_config,
            settings=settings,
            audio_output_handler=handle_azure_audio,
            interruption_handler=handle_interruption
        )
        
        # Inicia conexão em background
        worker_task = asyncio.create_task(session_worker.connect_and_run())

        # 4. Loop Principal: Twilio (8k) -> Transcoder -> Azure (24k)
        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                event_type = data.get("event")

                if event_type == "media":
                    # Extrai payload bruto (Mu-Law 8k)
                    raw_payload = data["media"]["payload"]
                    
                    # Delega conversão/limpeza para o Transcoder
                    clean_24k_payload = transcoder.twilio_to_azure(raw_payload)
                    
                    # Se o áudio for válido, envia para o Azure
                    if clean_24k_payload and session_worker.connection:
                        await session_worker.ingest_audio(clean_24k_payload)

                elif event_type == "start":
                    stream_sid = data["start"]["streamSid"]
                    logger.info(f"📞 Stream iniciado (SID: {stream_sid})")
                
                elif event_type == "stop":
                    logger.info("📞 Chamada finalizada pelo Twilio")
                    break
                    
            except WebSocketDisconnect:
                logger.info("🔌 WebSocket desconectado")
                break
            except Exception as e:
                # Erros de JSON ou protocolo não devem derrubar o servidor
                logger.error(f"Erro no loop de eventos: {e}")
                break

    except Exception as e:
        logger.critical(f"❌ Erro crítico na sessão: {e}", exc_info=True)
    
    finally:
        # Limpeza robusta de recursos
        if session_worker: 
            session_worker.shutdown()
        if worker_task: 
            worker_task.cancel()
            try: await worker_task 
            except: pass