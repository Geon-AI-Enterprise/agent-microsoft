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
from src.services.transcoder import AudioTranscoder
from src.services.voice_assistant import VoiceAssistantWorker
from src.services.client_manager import ClientManager

logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(title="Voice Agent API")

client_manager = ClientManager(settings.DB_URL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Controla inicialização e finalização de recursos da aplicação.
    """
    logger.info("🚀 Voice Agent API iniciando...")
    yield
    logger.info("🧹 Voice Agent API finalizando...")


app.router.lifespan_context = lifespan


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
        client_config = await client_manager.get_agent_config_by_sip(sip_number)
        if not client_config:
            logger.error(f"❌ Cliente não encontrado para o número: {sip_number}")
            await websocket.close()
            return

        logger.info(f"👤 Cliente identificado: {client_config.name}")

        # 2. Configuração do Handler de Saída (Azure -> Twilio)
        async def handle_azure_audio(pcm_24k: bytes):
            """
            Recebe áudio 24k PCM16 do Azure e envia para o Twilio em Mu-Law 8k.
            """
            try:
                base64_chunk = transcoder.azure_to_twilio(pcm_24k)
                if not base64_chunk:
                    return

                if not stream_sid:
                    return

                payload = {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {
                        "payload": base64_chunk
                    }
                }
                await websocket.send_text(json.dumps(payload))
            except Exception as e:
                logger.error(f"Erro ao enviar áudio para Twilio: {e}")

        async def handle_interruption():
            """
            Limpa os buffers internos do Transcoder, garantindo que nenhum áudio residual
            seja enviado após um barge-in.
            """
            try:
                transcoder.clear()
                await websocket.send_text(json.dumps({
                    "event": "clear"
                }))
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

        # 4. Loop principal do WebSocket com Twilio
        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                event_type = data.get("event")

                if event_type == "start":
                    stream_sid = data["start"]["streamSid"]
                    logger.info(f"▶️ Stream iniciado: {stream_sid}")

                elif event_type == "media":
                    # Extrai payload bruto (Mu-Law 8k)
                    raw_payload = data["media"]["payload"]

                    # 🔥 BARGE-IN ANTECIPADO:
                    # Se o agente estiver falando e chegar mídia nova do usuário,
                    # disparamos a interrupção imediatamente (sem esperar VAD do Azure)
                    if session_worker and session_worker.is_agent_speaking:
                        try:
                            await session_worker.trigger_barge_in()
                        except Exception as e:
                            logger.warning(f"⚠️ Falha ao acionar barge-in pelo lado Twilio: {e}")
                    
                    # Delega conversão/limpeza para o Transcoder
                    clean_24k_payload = transcoder.twilio_to_azure(raw_payload)
                    
                    # Se o áudio for válido, envia para o Azure
                    if clean_24k_payload and session_worker.connection:
                        await session_worker.ingest_audio(clean_24k_payload)

                elif event_type == "stop":
                    logger.info("⏹️ Stream finalizado pelo Twilio")
                    break

            except WebSocketDisconnect:
                logger.info(f"🔌 Conexão encerrada para o número: {sip_number}")
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
            try:
                await worker_task 
            except Exception:
                pass