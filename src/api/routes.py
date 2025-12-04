"""
API Routes

FastAPI endpoints para health check, informações básicas e WebSocket multi-tenant.
"""

import asyncio
import base64
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from src.core.config import get_settings, AgentConfig
from src.services.voice_assistant import VoiceAssistantWorker
from src.services.client_manager import ClientManager

logger = logging.getLogger(__name__)
settings = get_settings()

# Carrega configuração do arquivo (desenvolvimento local)
# Na Fase 3, cada conexão WebSocket carregará sua própria config do Supabase
agent_config = AgentConfig("config/agent_config.json", env=settings.APP_ENV)

# Worker instance com config injetada
worker_task = None
worker = VoiceAssistantWorker(agent_config=agent_config, settings=settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"🟢 Iniciando aplicação em ambiente: {settings.APP_ENV.upper()}")
    
    # Inicia o Worker em background (apenas para desenvolvimento local)
    global worker_task
    if settings.is_development():
        worker_task = asyncio.create_task(worker.connect_and_run())
        logger.info("🎙️ Worker de desenvolvimento iniciado em background")
    
    yield
    
    # Shutdown
    logger.info("🔴 Encerrando aplicação...")
    worker.shutdown()
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Azure VoiceLive Agent", lifespan=lifespan)


@app.get("/health")
async def health_check():
    """Health Check para monitoramento"""
    # Em desenvolvimento, verifica conexão do worker global
    # Em staging/production, retorna 'ready' pois workers são criados por sessão WebSocket
    if settings.is_development():
        status = "connected" if worker.connection else "initializing"
    else:
        # Staging/Production: servidor está pronto para receber conexões WebSocket
        status = "ready"
    
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "worker_status": status,
        "voice_model": agent_config.voice
    }


@app.get("/")
async def root():
    return {"message": "Geon AI Voice Agent Running", "docs": "/docs"}


# ==============================================================================
# WEBSOCKET ENDPOINT - MULTI-TENANT AUDIO STREAMING
# ==============================================================================
@app.websocket("/ws/audio/{sip_number}")
async def audio_stream(websocket: WebSocket, sip_number: str):
    """
    Endpoint WebSocket para streaming de áudio multi-tenant.
    
    Args:
        sip_number: Número SIP do cliente (ex: '+5511999990001')
        
    Fluxo:
        1. Busca configuração do cliente no Supabase
        2. Cria Worker dedicado para esta conexão
        3. Estabelece ponte bidirecional de áudio:
           - Cliente → WebSocket → Azure (entrada)
           - Azure → WebSocket → Cliente (saída)
    """
    await websocket.accept()
    logger.info(f"🔌 Nova conexão WebSocket: {sip_number}")
    
    session_worker = None
    session_task = None
    
    try:
        # 1. Busca configuração do cliente no Supabase
        client_manager = ClientManager(
            supabase_url=settings.SUPABASE_URL,
            supabase_key=settings.SUPABASE_SERVICE_ROLE_KEY
        )
        
        client_config = client_manager.get_client_config(sip_number)
        
        if not client_config:
            logger.warning(f"⚠️ Cliente não encontrado: {sip_number}")
            await websocket.close(code=4004, reason="Cliente não encontrado no sistema")
            return
        
        logger.info(f"✅ Configuração carregada para: {sip_number}")
        
        # 2. Callback para enviar áudio de volta ao cliente via WebSocket
        async def send_audio_to_client(audio_data: bytes):
            """Envia áudio do Azure de volta para o cliente WebSocket"""
            try:
                # Codifica áudio em base64 para transmissão WebSocket
                encoded = base64.b64encode(audio_data).decode('utf-8')
                await websocket.send_text(encoded)
            except Exception as e:
                logger.error(f"❌ Erro ao enviar áudio para cliente: {e}")
        
        # 3. Cria Worker dedicado para esta sessão
        session_worker = VoiceAssistantWorker(
            agent_config=client_config,
            settings=settings,
            audio_output_handler=send_audio_to_client  # Roteamento de áudio customizado
        )
        
        # 4. Inicia conexão Azure em background
        session_task = asyncio.create_task(session_worker.connect_and_run())
        
        # Aguarda conexão ser estabelecida
        await asyncio.sleep(2)  # Dá tempo para Azure conectar
        
        if not session_worker.connection:
            logger.error(f"❌ Falha ao conectar com Azure para: {sip_number}")
            await websocket.close(code=1011, reason="Erro ao conectar com servidor de voz")
            return
        
        logger.info(f"🎙️ Sessão de áudio iniciada para: {sip_number}")
        
        # 5. Loop principal: recebe áudio do cliente e envia para Azure
        while True:
            try:
                # Recebe áudio do cliente (base64 encoded PCM16)
                audio_data = await websocket.receive_text()
                
                # Envia para o buffer de entrada do Azure
                if session_worker.connection:
                    await session_worker.connection.input_audio_buffer.append(audio=audio_data)
                    
            except WebSocketDisconnect:
                logger.info(f"🔌 Cliente desconectado: {sip_number}")
                break
            except Exception as e:
                logger.error(f"❌ Erro no loop de áudio: {e}")
                break
    
    except Exception as e:
        logger.error(f"❌ Erro crítico na sessão WebSocket: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Erro interno do servidor")
        except:
            pass
    
    finally:
        # 6. Limpeza de recursos
        logger.info(f"🧹 Limpando recursos para: {sip_number}")
        
        if session_worker:
            session_worker.shutdown()
        
        if session_task:
            session_task.cancel()
            try:
                await session_task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"✅ Sessão encerrada: {sip_number}")
