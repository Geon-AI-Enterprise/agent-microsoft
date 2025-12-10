"""
API Routes - Twilio ↔ Azure Audio Proxy

=============================================================================
ARQUITETURA: TWILIO COMO "PIPE BURRO"
=============================================================================

Este módulo implementa um WebSocket proxy SIMPLES entre Twilio e Azure:
- Twilio envia áudio 8 kHz μ-law (base64) → convertemos para PCM 24k → Azure
- Azure envia áudio PCM 24k → convertemos para 8 kHz μ-law (base64) → Twilio

IMPORTANTE: Este módulo NÃO realiza:
- VAD (detecção de voz) → Responsabilidade do Azure (Server VAD)
- Barge-in → Responsabilidade do Azure
- Controle de turnos → Responsabilidade do Azure
- Análise de energia/silêncio → Responsabilidade do Azure

O endpoint WebSocket /ws/audio/{sip_number} apenas:
1. Identifica o cliente via ClientManager (multi-tenant)
2. Conecta ao Azure VoiceLive
3. Roda duas coroutines em paralelo:
   - twilio_to_azure: recebe áudio do Twilio e envia para Azure
   - azure_to_twilio: recebe áudio do Azure e envia para Twilio
=============================================================================
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from src.core.config import get_settings
from src.services.transcoder import AudioTranscoder
from src.services.voice_assistant import VoiceAssistantWorker
from src.services.client_manager import ClientManager
from datetime import datetime

logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(title="Voice Agent API")

# ClientManager configurado com Supabase (multi-tenant)
client_manager = ClientManager(
    supabase_url=settings.SUPABASE_URL,
    supabase_key=settings.SUPABASE_SERVICE_ROLE_KEY,
)

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Controla inicialização e finalização de recursos da aplicação."""
    logger.info("🚀 Voice Agent API iniciando...")
    yield
    logger.info("🧹 Voice Agent API finalizando...")


app.router.lifespan_context = lifespan


@app.websocket("/ws/audio/{sip_number}")
async def audio_stream(websocket: WebSocket, sip_number: str):
    """
    WebSocket endpoint que atua como proxy de áudio entre Twilio e Azure.
    
    Fluxo:
    1. Aceita conexão WebSocket da Twilio
    2. Identifica cliente via sip_number (Supabase/ClientManager)
    3. Inicia worker do Azure VoiceLive
    4. Executa duas coroutines em paralelo:
       - twilio_to_azure(): Twilio → Transcoder → Azure
       - azure_to_twilio(): Azure → Transcoder → Twilio
    5. Encerra tudo quando qualquer lado desconecta
    
    Args:
        websocket: Conexão WebSocket da Twilio
        sip_number: Número SIP para identificar o cliente
    """
    await websocket.accept()
    logger.info(f"📞 Conexão Twilio recebida: {sip_number}")

    session_worker: VoiceAssistantWorker | None = None
    worker_task: asyncio.Task | None = None
    stream_sid: str | None = None

    # Instancia o transcoder (conversão de formato apenas)
    transcoder = AudioTranscoder()

    try:
        # ======================================================================
        # 1. IDENTIFICAÇÃO DO CLIENTE (Multi-tenant via Supabase)
        # ======================================================================
        client_config = client_manager.get_client_config(sip_number)
        if not client_config:
            logger.error(f"❌ Cliente não encontrado: {sip_number}")
            await websocket.close(code=4004, reason="Client not found")
            return

        logger.info(f"👤 Cliente identificado: {getattr(client_config, 'name', sip_number)}")

        # ======================================================================
        # 2. INICIALIZA WORKER DO AZURE (Sem callbacks - usa streaming)
        # ======================================================================
        session_worker = VoiceAssistantWorker(
            agent_config=client_config,
            settings=settings,
        )

        # Inicia conexão com Azure em background
        worker_task = asyncio.create_task(session_worker.connect_and_run())

        # Aguarda conexão estar pronta (pequeno delay para setup)
        await asyncio.sleep(0.1)

        # ======================================================================
        # 3. DEFINE COROUTINES DE STREAMING BIDIRECIONAL
        # ======================================================================
        
        async def twilio_to_azure():
            """
            Recebe áudio do Twilio e envia para o Azure.
            
            Loop infinito que:
            1. Lê mensagens JSON do WebSocket Twilio
            2. Filtra apenas eventos 'media'
            3. Converte áudio 8kHz μ-law → 24kHz PCM
            4. Envia para o Azure via worker.send_user_audio()
            """
            nonlocal stream_sid
            
            try:
                while True:
                    message = await websocket.receive_text()
                    data = json.loads(message)
                    event_type = data.get("event")

                    if event_type == "start":
                        # Twilio inicia o stream - captura o streamSid
                        stream_sid = data["start"]["streamSid"]
                        logger.info(f"▶️ Stream Twilio iniciado: {stream_sid}")

                    elif event_type == "media":
                        # Áudio do usuário chegou
                        if session_worker and session_worker.connection:
                            # Extrai payload base64 (8kHz μ-law)
                            raw_payload = data["media"]["payload"]
                            
                            # Converte para PCM 24kHz
                            pcm_24k = transcoder.twilio_to_azure(raw_payload)
                            
                            if pcm_24k:
                                # Envia para Azure (sem barge-in manual!)
                                await session_worker.send_user_audio(pcm_24k)

                    elif event_type == "stop":
                        # Twilio encerrou o stream
                        logger.info("⏹️ Stream finalizado pelo Twilio")
                        break

            except WebSocketDisconnect:
                logger.info(f"🔌 Twilio desconectou: {sip_number}")
            except Exception as e:
                logger.error(f"❌ Erro no loop Twilio → Azure: {e}")

        async def azure_to_twilio():
            """
            Recebe áudio do Azure e envia para o Twilio.
            
            Loop assíncrono que:
            1. Itera sobre chunks de áudio via worker.iter_agent_audio()
            2. Converte PCM 24kHz → 8kHz μ-law base64
            3. Envia para Twilio como evento 'media'
            """
            try:
                # Aguarda worker estar pronto
                while not session_worker or not session_worker.connection:
                    await asyncio.sleep(0.05)
                    if worker_task and worker_task.done():
                        return

                # Itera sobre chunks de áudio do agente
                async for pcm_bytes in session_worker.iter_agent_audio():
                    if not stream_sid:
                        continue

                    # Converte PCM 24k → μ-law 8k base64
                    # Usa azure_to_twilio_all para pegar todos os chunks gerados
                    base64_chunks = transcoder.azure_to_twilio_all(pcm_bytes)
                    
                    for base64_chunk in base64_chunks:
                        if base64_chunk:
                            # Monta payload no formato Twilio
                            payload = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": base64_chunk,
                                },
                            }
                            await websocket.send_text(json.dumps(payload))

            except WebSocketDisconnect:
                logger.info(f"🔌 Twilio desconectou durante envio: {sip_number}")
            except Exception as e:
                logger.error(f"❌ Erro no loop Azure → Twilio: {e}")

        # ======================================================================
        # 4. EXECUTA AMBAS AS DIREÇÕES EM PARALELO
        # ======================================================================
        await asyncio.gather(
            twilio_to_azure(),
            azure_to_twilio(),
            return_exceptions=True
        )

    except Exception as e:
        logger.critical(f"❌ Erro crítico na sessão: {e}", exc_info=True)

    finally:
        # ======================================================================
        # 5. LIMPEZA DE RECURSOS
        # ======================================================================
        logger.info(f"🧹 Encerrando sessão: {sip_number}")
        
        if session_worker:
            session_worker.shutdown()
        
        if worker_task:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        logger.info(f"👋 Sessão encerrada: {sip_number}")
