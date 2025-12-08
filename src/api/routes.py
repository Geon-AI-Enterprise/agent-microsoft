"""
API Routes - Twilio Integration (Refatorado para Estabilidade)

Mudanças Críticas:
1. Remoção do VAD local (webrtcvad) dentro do loop de recebimento.
   Motivo: O VAD local bloqueia o event loop em alta escala. Deixe o Azure lidar com VAD.
2. Gerenciamento de Tasks mais robusto para evitar "zombie tasks".
3. Tratamento de exceções específico para WebSocketDisconnect.
"""

import asyncio
import base64
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager

from src.core.config import get_settings, AgentConfig
from src.services.voice_assistant import VoiceAssistantWorker
from src.services.client_manager import ClientManager

logger = logging.getLogger(__name__)
settings = get_settings()

# --- Gerenciamento de Lifespan (Mantido) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🟢 STARTUP: {settings.APP_ENV.upper()}")
    yield
    logger.info("🔴 SHUTDOWN")

app = FastAPI(title="Azure VoiceLive Agent", lifespan=lifespan)

@app.get("/health")
async def health_check():
    return {"status": "ok", "env": settings.APP_ENV}

# --- WebSocket Otimizado ---
@app.websocket("/ws/audio/{sip_number}")
async def audio_stream(websocket: WebSocket, sip_number: str):
    await websocket.accept()
    logger.info(f"🔌 Conexão Twilio iniciada: {sip_number}")

    session_worker = None
    worker_task = None
    stream_sid = None

    try:
        # 1. Configuração do Cliente (Rápida)
        # Nota: Se o Supabase demorar, isso pode causar timeout no Twilio.
        # Idealmente, use cache agressivo no ClientManager.
        client_manager = ClientManager(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        client_config = client_manager.get_client_config(sip_number)

        if not client_config:
            logger.warning(f"⚠️ Cliente não encontrado ou inativo: {sip_number}")
            await websocket.close(code=4000)
            return

        # 2. Callbacks de Áudio (Definidos para serem Non-Blocking)
        async def send_audio_to_twilio(audio_data: bytes):
            if not stream_sid: return
            try:
                # Codificação Base64 é rápida, mas em alta escala considere threads separadas se notar lag
                payload = base64.b64encode(audio_data).decode('utf-8')
                await websocket.send_json({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload}
                })
            except Exception as e:
                logger.debug(f"Falha ao enviar áudio Twilio: {e}")

        async def send_clear_buffer():
            if not stream_sid: return
            try:
                # O comando 'clear' é crucial para a interrupção funcionar bem no Twilio
                await websocket.send_json({"event": "clear", "streamSid": stream_sid})
            except Exception:
                pass

        # 3. Inicializa Worker
        session_worker = VoiceAssistantWorker(
            agent_config=client_config,
            settings=settings,
            audio_output_handler=send_audio_to_twilio,
            interruption_handler=send_clear_buffer
        )
        
        # Inicia a conexão com Azure em background
        worker_task = asyncio.create_task(session_worker.connect_and_run())

        # 4. Loop Principal (Simplificado e Otimizado)
        # Removemos o VAD local pesado. Enviamos tudo para o Azure processar.
        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                event_type = data.get("event")

                if event_type == "media":
                    # Extrai payload
                    payload = data["media"]["payload"]
                    
                    # Envia diretamente para o Azure (Fire and Forget)
                    # O Worker deve lidar com o buffer interno
                    if session_worker.connection:
                        # append é async, mas aqui usamos create_task ou await rápido
                        # para não bloquear a leitura do próximo pacote Twilio
                        await session_worker.ingest_audio(payload)

                elif event_type == "start":
                    stream_sid = data["start"]["streamSid"]
                    logger.info(f"📞 Stream SID: {stream_sid}")

                elif event_type == "stop":
                    logger.info("📞 Chamada encerrada pelo Twilio")
                    break
                
                elif event_type == "mark":
                    # Eventos de marcação (opcional: logs)
                    pass

            except WebSocketDisconnect:
                logger.info("🔌 WebSocket desconectado pelo cliente")
                break
            except Exception as e:
                logger.error(f"❌ Erro no loop WebSocket: {e}")
                break

    except Exception as e:
        logger.critical(f"❌ Erro crítico na sessão: {e}")
    
    finally:
        # Limpeza Robusta
        logger.info(f"🧹 Limpando sessão {sip_number}")
        if session_worker:
            session_worker.shutdown()
        
        if worker_task:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
        
        try:
            await websocket.close()
        except:
            pass