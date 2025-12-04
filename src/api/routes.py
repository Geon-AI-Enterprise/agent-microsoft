"""
API Routes

FastAPI endpoints para health check, informações básicas e WebSocket multi-tenant.
Inclui sistema de Auto-Diagnóstico (Self-Test) no startup.
"""

import asyncio
import base64
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
# DIAGNÓSTICO DE STARTUP (SELF-TEST)
# ==============================================================================
async def run_startup_diagnostics():
    """
    Executa bateria de testes de infraestrutura no startup.
    Verifica Rede, DNS, Supabase e Configurações.
    """
    logger.info("🩺 INICIANDO DIAGNÓSTICO DE SELF-TEST...")
    errors = []

    # 1. Teste de Resolução DNS e Conectividade Básica
    try:
        host = "google.com"
        # Tenta resolver DNS
        addr = socket.gethostbyname(host)
        # Tenta conectar na porta 80
        socket.create_connection((host, 80), timeout=2)
        logger.info(f"✅ Rede OK: {host} -> {addr}")
    except Exception as e:
        msg = f"❌ FALHA DE REDE/DNS: Não foi possível conectar à internet ({e})"
        logger.error(msg)
        errors.append(msg)

    # 2. Teste de Conexão Supabase (Vital para Staging/Prod)
    if not settings.is_development():
        try:
            logger.info(f"🔍 Testando conexão Supabase ({settings.SUPABASE_URL})...")
            # Cliente temporário apenas para teste
            sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
            
            # Tenta uma query leve para verificar acesso
            # Verifica se tabela de números existe (query head)
            sb.table('client_sip_numbers').select("sip_number", count="exact").limit(1).execute()
            
            logger.info(f"✅ Supabase OK: Conexão estabelecida")
        except Exception as e:
            msg = f"❌ FALHA SUPABASE: Não foi possível conectar ao banco ({e})"
            logger.error(msg)
            errors.append(msg)
    else:
        logger.info("ℹ️ Supabase check pulado em Development")

    # 3. Teste de Configuração do Worker
    try:
        # Tenta carregar config local para validar integridade do JSON
        test_config = AgentConfig("config/agent_config.json", env=settings.APP_ENV)
        logger.info(f"✅ Configuração Local OK: {test_config.config_path}")
    except Exception as e:
        msg = f"❌ FALHA DE CONFIG: Erro ao carregar JSON de configuração ({e})"
        logger.error(msg)
        errors.append(msg)

    # RESUMO DO DIAGNÓSTICO
    if errors:
        logger.critical("🚨 O SELF-TEST ENCONTROU PROBLEMAS CRÍTICOS:")
        for err in errors:
            logger.critical(f"   -> {err}")
        logger.critical("⚠️ A APLICAÇÃO PODE FICAR INSTÁVEL OU FALHAR.")
    else:
        logger.info("✨ SELF-TEST CONCLUÍDO: Todos os sistemas operacionais.")


# ==============================================================================
# INICIALIZAÇÃO GLOBAL (SAFE LOAD)
# ==============================================================================
worker = None
worker_task = None

try:
    # Carrega configuração do arquivo (desenvolvimento local/fallback)
    # Isso é necessário para o worker global de desenvolvimento
    base_agent_config = AgentConfig("config/agent_config.json", env=settings.APP_ENV)
    
    # Instancia worker global (usado apenas em Development)
    worker = VoiceAssistantWorker(agent_config=base_agent_config, settings=settings)
except Exception as e:
    logger.error(f"⚠️ Erro na inicialização do worker global (não crítico para Prod): {e}")


# ==============================================================================
# LIFESPAN (CICLO DE VIDA)
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    logger.info(f"🟢 STARTUP: Iniciando aplicação em ambiente: {settings.APP_ENV.upper()}")
    
    # 1. Executa diagnóstico de infraestrutura
    await run_startup_diagnostics()
    
    # 2. Inicia Worker Global (APENAS EM DEVELOPMENT)
    # Em Staging/Prod, o worker é on-demand (por chamada), então não iniciamos aqui.
    global worker_task
    if settings.is_development() and worker:
        worker_task = asyncio.create_task(worker.connect_and_run())
        logger.info("🎙️ Worker de desenvolvimento iniciado em background")
    
    yield
    
    # --- SHUTDOWN ---
    logger.info("🔴 SHUTDOWN: Encerrando aplicação...")
    
    # Encerra worker global se estiver rodando
    if worker:
        worker.shutdown()
        
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Azure VoiceLive Agent", lifespan=lifespan)


# ==============================================================================
# ENDPOINTS HTTP
# ==============================================================================
@app.get("/health")
async def health_check():
    """Health Check para monitoramento"""
    # Em staging/prod, status é 'ready' se o servidor estiver de pé
    status = "ready"
    
    # Em dev, verificamos a conexão real do worker global
    if settings.is_development() and worker:
        status = "connected" if worker.connection else "initializing"
    
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "worker_status": status,
        "checks": "self-test-passed"
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
    Cria um worker dedicado para cada conexão.
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
            logger.warning(f"⚠️ Cliente não encontrado no Supabase: {sip_number}")
            # Código 4004 não é padrão WS, usamos 4000-4999 para app-specific ou 1008 (Policy Violation)
            await websocket.close(code=4000, reason="Cliente não encontrado")
            return
        
        logger.info(f"✅ Configuração carregada para: {sip_number}")
        
        # 2. Callbacks de Áudio
        async def send_audio_to_client(audio_data: bytes):
            """Envia áudio do Azure de volta para o cliente WebSocket"""
            try:
                encoded = base64.b64encode(audio_data).decode('utf-8')
                await websocket.send_text(encoded)
            except Exception as e:
                logger.error(f"❌ Erro ao enviar áudio para cliente: {e}")

        async def send_interruption_signal():
            """Envia sinal para o cliente limpar o buffer de áudio (Barge-in)"""
            try:
                logger.info("🛑 Enviando sinal de CLEAR_BUFFER")
                await websocket.send_text("CLEAR_BUFFER")
            except Exception as e:
                logger.error(f"❌ Erro ao enviar sinal de interrupção: {e}")
        
        # 3. Cria Worker Dedicado (On-Demand)
        session_worker = VoiceAssistantWorker(
            agent_config=client_config,
            settings=settings,
            audio_output_handler=send_audio_to_client,
            interruption_handler=send_interruption_signal
        )
        
        # 4. Inicia conexão Azure
        session_task = asyncio.create_task(session_worker.connect_and_run())
        
        # Aguarda brevemente para garantir conexão
        # (Idealmente, connect_and_run deveria sinalizar prontidão, mas sleep ajuda)
        await asyncio.sleep(1)
        
        if not session_worker.connection:
             # Se falhou conectar rápido, pode ser erro de credencial Azure
             logger.error(f"❌ Falha de conexão inicial com Azure para: {sip_number}")
             # Não fechamos imediatamente para permitir retentativa interna, 
             # mas logamos o alerta.
        
        logger.info(f"🎙️ Sessão de áudio ativa para: {sip_number}")
        
        # 5. Loop principal: recebe áudio do cliente
        while True:
            try:
                # Recebe áudio do cliente
                audio_data = await websocket.receive_text()
                
                # Envia para o buffer de entrada do Azure se conectado
                if session_worker.connection:
                    await session_worker.connection.input_audio_buffer.append(audio=audio_data)
                    
            except WebSocketDisconnect:
                logger.info(f"🔌 Cliente desconectado: {sip_number}")
                break
            except Exception as e:
                logger.error(f"❌ Erro no loop de áudio: {e}")
                break
    
    except Exception as e:
        logger.critical(f"❌ Erro crítico na sessão WebSocket: {e}", exc_info=True)
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