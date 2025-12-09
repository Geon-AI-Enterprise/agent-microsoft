"""
Voice Assistant Worker Service - Production Ready

Core do Assistente: Gerencia Conexão, Sessão e Eventos do Azure VoiceLive.
Otimizado para arquitetura baseada em WebSocket (Twilio/EasyPanel) com Transcoding.
"""

import asyncio
import logging
from typing import Optional, Callable, Awaitable

from azure.core.credentials import AzureKeyCredential
from azure.identity.aio import DefaultAzureCredential
from azure.ai.voicelive.aio import connect, VoiceLiveConnection
from azure.ai.voicelive.models import (
    AzureStandardVoice,
    InputAudioFormat,
    Modality,
    OutputAudioFormat,
    RequestSession,
    ServerEventType,
    ServerVad,
)

from src.core.config import get_settings, AgentConfig

# Tenta importar processador de áudio local apenas se necessário (Development)
try:
    from src.services.audio_processor import AudioProcessor, AUDIO_AVAILABLE
except ImportError:
    AUDIO_AVAILABLE = False

logger = logging.getLogger(__name__)


class VoiceAssistantWorker:
    """
    Worker resiliente para gerenciar a sessão de voz.
    Foca em manter a conexão estável e gerenciar o estado da conversação.
    """

    def __init__(
        self, 
        agent_config: AgentConfig, 
        settings=None, 
        audio_output_handler: Optional[Callable[[bytes], Awaitable[None]]] = None, 
        interruption_handler: Optional[Callable[[], Awaitable[None]]] = None
    ):
        self.settings = settings or get_settings()
        self.agent_config = agent_config
        self.connection: Optional[VoiceLiveConnection] = None
        
        # Handlers externos (Injeção de dependência para o WebSocket)
        self.audio_output_handler = audio_output_handler
        self.interruption_handler = interruption_handler
        
        # Estado interno
        self.audio_processor = None
        self._shutdown_event = asyncio.Event()
        self.is_agent_speaking = False
        
        # Controles de fluxo
        self._is_greeting_mode = False
        self._greeting_sent_at = 0
        
        # Configurações de latência e proteção
        self._greeting_delay = self.settings.GREETING_DELAY_SECONDS or 1.0
        
        logger.info(f"🚀 Worker inicializado | Voz: {self.agent_config.voice}")

    async def connect_and_run(self):
        """
        Gerencia o ciclo de vida completo da conexão com o Azure.
        Projetado para falhar graciosamente e limpar recursos.
        """
        try:
            # 1. Configuração de Credenciais
            if self.settings.AZURE_VOICELIVE_API_KEY:
                cred = AzureKeyCredential(self.settings.AZURE_VOICELIVE_API_KEY)
            else:
                cred = DefaultAzureCredential()

            logger.info(f"🔌 Conectando ao Azure VoiceLive (Modelo: {self.settings.AZURE_VOICELIVE_MODEL})...")
            
            async with connect(
                endpoint=self.settings.AZURE_VOICELIVE_ENDPOINT,
                credential=cred,
                model=self.settings.AZURE_VOICELIVE_MODEL
            ) as conn:
                self.connection = conn
                logger.info("✅ Conexão estabelecida com sucesso")

                # 2. Inicialização de Áudio Local (Apenas Dev/Local)
                if self.settings.is_development() and AUDIO_AVAILABLE:
                    self._setup_local_audio(conn)

                # 3. Configura a Sessão (PCM16 para estabilidade)
                await self._configure_session()

                # 4. Inicia Saudação (Em background para não bloquear)
                asyncio.create_task(self._send_initial_greeting())
                
                # 5. Loop Principal de Eventos (Bloqueante até desconexão)
                await self._process_events()

        except asyncio.CancelledError:
            logger.info("🛑 Worker cancelado (Shutdown normal)")
        except Exception as e:
            logger.error(f"❌ Erro na conexão do Worker: {e}", exc_info=self.settings.is_development())
        finally:
            self.connection = None
            if self.audio_processor:
                self.audio_processor.shutdown()
            logger.info("👋 Worker finalizado")

    async def ingest_audio(self, base64_audio: str):
        """
        Método seguro para receber áudio (já convertido para 24k) do WebSocket.
        """
        if not self.connection:
            return

        try:
            # Envia para o buffer do Azure
            await self.connection.input_audio_buffer.append(audio=base64_audio)
        except Exception as e:
            logger.debug(f"⚠️ Falha ao ingerir áudio: {e}")

    async def _configure_session(self):
        """
        Configura sessão usando PCM16 (24kHz).
        O Azure VAD funciona perfeitamente neste formato.
        A conversão 8k <-> 24k é responsabilidade do routes.py.
        """
        
        input_fmt = InputAudioFormat.PCM16
        output_fmt = OutputAudioFormat.PCM16

        # Recupera configs com fallback seguro
        turn_config = self.agent_config.config.get('turn_detection', {})
        threshold = self.settings.VAD_THRESHOLD or turn_config.get('threshold', 0.5)
        silence_ms = self.settings.VAD_SILENCE_DURATION_MS or turn_config.get('silence_duration_ms', 500)
        prefix_ms = self.settings.VAD_PREFIX_PADDING_MS or turn_config.get('prefix_padding_ms', 300)

        vad_config = ServerVad(
            threshold=threshold,
            prefix_padding_ms=prefix_ms,
            silence_duration_ms=silence_ms
        )

        session_config = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            instructions=self.agent_config.instructions,
            voice=AzureStandardVoice(name=self.agent_config.voice),
            input_audio_format=input_fmt,
            output_audio_format=output_fmt,
            turn_detection=vad_config,
            temperature=self.settings.MODEL_TEMPERATURE or self.agent_config.temperature,
            max_response_output_tokens=self.settings.MAX_RESPONSE_OUTPUT_TOKENS or self.agent_config.max_tokens
        )
        
        await self.connection.session.update(session=session_config)
        logger.info(f"⚙️ Sessão configurada: PCM16 24kHz (Transcoding Ativo) | VAD(t={threshold})")

    async def _process_events(self):
        """
        O Coração do Assistente: Processa eventos do Azure e gerencia interrupções.
        """
        async for event in self.connection:
            if self._shutdown_event.is_set():
                break

            # ------------------------------------------------------------------
            # DETECÇÃO DE FALA DO USUÁRIO (VAD) & BARGE-IN
            # ------------------------------------------------------------------
            if event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                logger.info("🗣️ [Azure] Usuário começou a falar")
                
                # Interrupção Inteligente
                if self.is_agent_speaking:
                    logger.info("⚡ BARGE-IN DETECTADO: Interrompendo agente...")
                    self.is_agent_speaking = False
                    
                    # 1. Cancela a resposta do Azure IMEDIATAMENTE
                    await self.connection.response.cancel()
                    
                    # 2. Limpa o buffer do Twilio/Cliente
                    if self.interruption_handler:
                        asyncio.create_task(self.interruption_handler())
                    
                    if self.audio_processor:
                        self.audio_processor.skip_pending_audio()

            # ------------------------------------------------------------------
            # FIM DA FALA DO USUÁRIO
            # ------------------------------------------------------------------
            elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
                logger.info("🤫 [Azure] Usuário parou de falar")
                if self._is_greeting_mode:
                    self._is_greeting_mode = False

            # ------------------------------------------------------------------
            # ÁUDIO DO AGENTE (OUTPUT)
            # ------------------------------------------------------------------
            elif event.type == ServerEventType.RESPONSE_AUDIO_DELTA:
                if not self.is_agent_speaking:
                    self.is_agent_speaking = True
                
                if self.audio_output_handler:
                    await self.audio_output_handler(event.delta)
                elif self.audio_processor:
                    self.audio_processor.queue_audio(event.delta)

            # ------------------------------------------------------------------
            # TRANSCRIÇÃO E LOGS
            # ------------------------------------------------------------------
            elif event.type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE:
                logger.info(f"🤖 Agente disse: {event.transcript}")
                self.is_agent_speaking = False
                self._is_greeting_mode = False

            elif event.type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
                logger.info(f"👤 Transcrição usuário: {event.transcript}")

            elif event.type == ServerEventType.ERROR:
                logger.error(f"❌ Erro Azure: {event.error.message}")

    async def _send_initial_greeting(self):
        """Envia saudação inicial"""
        try:
            self._is_greeting_mode = True
            await asyncio.sleep(self._greeting_delay)
            
            if not self.connection: 
                return

            logger.info("👋 Enviando saudação inicial...")
            await self.connection.response.create(
                response={
                    "instructions": "Diga sua saudação inicial definida nas instruções agora de forma natural."
                }
            )
        except Exception as e:
            logger.warning(f"⚠️ Erro ao enviar saudação: {e}")
            self._is_greeting_mode = False

    def _setup_local_audio(self, conn):
        """Configura áudio local apenas para desenvolvimento"""
        try:
            audio_config = self.agent_config.config.get('audio', {})
            if str(audio_config.get('input_format', '')).upper() == 'PCM16':
                self.audio_processor = AudioProcessor(conn)
                self.audio_processor.start_capture()
                self.audio_processor.start_playback()
                logger.info("🎙️ Áudio Local Ativado (Dev Mode)")
        except Exception as e:
            logger.warning(f"⚠️ Falha ao iniciar áudio local: {e}")

    def shutdown(self):
        """Encerra graciosamente"""
        self._shutdown_event.set()
        if self.audio_processor:
            self.audio_processor.shutdown()