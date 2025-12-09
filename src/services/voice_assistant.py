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
    AudioProcessor = None  # type: ignore

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
        interruption_handler: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        self.settings = settings or get_settings()
        self.agent_config = agent_config
        self.connection: Optional[VoiceLiveConnection] = None

        # Handlers externos (injeção de dependência)
        self.audio_output_handler = audio_output_handler
        self.interruption_handler = interruption_handler

        # Estado interno
        self.audio_processor = None
        self._shutdown_event = asyncio.Event()
        self.is_agent_speaking = False
        self._ignore_deltas = False

        # Controles de fluxo
        self._is_greeting_mode = False
        self._greeting_sent_at = 0.0

        # Configurações de latência e proteção
        # Usa GREETING_DELAY_SECONDS, com fallback para 1.0s se não existir
        self._greeting_delay = getattr(self.settings, "GREETING_DELAY_SECONDS", 1.0)

        logger.info(f"🚀 Worker inicializado | Voz: {self.agent_config.voice}")

    async def trigger_barge_in(self) -> None:
        """
        Interrompe o agente imediatamente (Barge-in).

        Reutilizado por:
        - Eventos de VAD do Azure (INPUT_AUDIO_BUFFER_SPEECH_STARTED)
        - Detecção antecipada no lado Twilio (chegada de mídia enquanto o agente fala)
        """

        # Se não há conexão ativa, não há o que fazer
        if not self.connection:
            return

        # Se já não está falando e não estamos ignorando deltas,
        # provavelmente não há nada para interromper
        if not self.is_agent_speaking and not self._ignore_deltas:
            return

        logger.info(
            f"⚡ BARGE-IN: Interrompendo agente "
            f"(is_agent_speaking={self.is_agent_speaking}, ignore_deltas={self._ignore_deltas})"
        )

        # Marca estado local: paramos de considerar que o agente está falando
        # e passamos a ignorar qualquer delta remanescente dessa resposta
        self.is_agent_speaking = False
        self._ignore_deltas = True

        # 1) Limpa buffer de saída no Azure (corta áudio já gerado mas ainda não enviado)
        try:
            output_buffer = getattr(self.connection, "output_audio_buffer", None)
            if output_buffer is not None:
                await output_buffer.clear()
                logger.info("🧹 Azure output_audio_buffer.clear() chamado com sucesso")
        except Exception as e:
            logger.warning(f"⚠️ Erro ao limpar output_audio_buffer no Azure: {e}")

        # 2) Cancela a resposta atual no Azure
        try:
            response_resource = getattr(self.connection, "response", None)
            if response_resource is not None:
                await response_resource.cancel()
                logger.info("⛔ Azure response.cancel() enviado com sucesso")
        except Exception as e:
            logger.warning(f"⚠️ Erro ao cancelar resposta no Azure durante barge-in: {e}")

        # 3) Limpa buffers do lado do cliente/Twilio
        try:
            if self.interruption_handler:
                await self.interruption_handler()
        except Exception as e:
            logger.warning(f"⚠️ Erro ao executar interruption_handler durante barge-in: {e}")

        # 4) Limpa qualquer áudio pendente no processador local (dev)
        try:
            if self.audio_processor:
                self.audio_processor.skip_pending_audio()
        except Exception as e:
            logger.warning(f"⚠️ Erro ao limpar áudio pendente durante barge-in: {e}")

    async def connect_and_run(self):
        """
        Gerencia o ciclo de vida completo da conexão com o Azure.
        Projetado para falhar graciosamente e limpar recursos.
        """
        try:
            # 1. Configuração de Credenciais
            if getattr(self.settings, "AZURE_VOICELIVE_API_KEY", None):
                cred = AzureKeyCredential(self.settings.AZURE_VOICELIVE_API_KEY)
            else:
                cred = DefaultAzureCredential()

            # 2. Abre Conexão com o Azure Voice Live
            async with connect(
                endpoint=self.settings.AZURE_VOICELIVE_ENDPOINT,
                credential=cred,
                model=self.settings.AZURE_VOICELIVE_MODEL,
            ) as conn:
                self.connection = conn
                logger.info("✅ Conexão estabelecida com sucesso")

                # 2. Inicialização de Áudio Local (Apenas Dev/Local)
                if getattr(self.settings, "is_development", lambda: False)() and AUDIO_AVAILABLE:
                    self._setup_local_audio(conn)

                # 3. Configura a Sessão (PCM16 para estabilidade)
                await self._configure_session()

                # 4. Inicia Saudação (Em background para não bloquear)
                asyncio.create_task(self._send_greeting_if_needed())

                # 5. Inicia Loop Principal de Eventos
                await self._process_events()

        except Exception as e:
            logger.error(f"❌ Erro crítico na conexão com Azure VoiceLive: {e}", exc_info=True)
        finally:
            await self._cleanup()

    # ------------------------------------------------------------------
    # SETUP DE ÁUDIO LOCAL (DEV)
    # ------------------------------------------------------------------
    def _setup_local_audio(self, conn: VoiceLiveConnection):
        if not AUDIO_AVAILABLE or not AudioProcessor:
            return

        self.audio_processor = AudioProcessor()
        logger.info("🎧 Áudio local habilitado para ambiente de desenvolvimento")

    # ------------------------------------------------------------------
    # CONFIGURAÇÃO DE SESSÃO
    # ------------------------------------------------------------------
    async def _configure_session(self):
        """
        Configura parâmetros da sessão no Azure VoiceLive.
        """
        logger.info("⚙️ Configurando sessão de voz no Azure...")

        voice = AzureStandardVoice(
            name=self.agent_config.voice,
            role="assistant",
        )

        vad = ServerVad(
            enable_vad=True,
            noise_suppression_level="high",
        )

        session = RequestSession(
            modalities=[Modality.INPUT_AUDIO, Modality.OUTPUT_AUDIO],
            assistant_voice=voice,
            input_audio_format=InputAudioFormat(
                encoding="pcm16",
                sample_rate_hz=24000,
            ),
            output_audio_format=OutputAudioFormat(
                encoding="pcm16",
                sample_rate_hz=24000,
            ),
            vad=vad,
        )

        await self.connection.session.configure(session)
        logger.info("✅ Sessão configurada com sucesso")

    # ------------------------------------------------------------------
    # SAUDAÇÃO INICIAL
    # ------------------------------------------------------------------
    async def _send_greeting_if_needed(self):
        """
        Dispara uma saudação inicial, se configurado no AgentConfig.
        """
        if not getattr(self.agent_config, "greeting", None):
            return

        await asyncio.sleep(self._greeting_delay)
        if self._shutdown_event.is_set():
            return

        try:
            self._is_greeting_mode = True
            self._greeting_sent_at = asyncio.get_event_loop().time()
            logger.info("💬 Enviando saudação inicial...")

            await self.connection.request.send(
                input_text=self.agent_config.greeting,
            )
        except Exception as e:
            logger.error(f"Erro ao enviar saudação inicial: {e}")

    # ------------------------------------------------------------------
    # LOOP PRINCIPAL DE EVENTOS
    # ------------------------------------------------------------------
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
                await self.trigger_barge_in()

            # ------------------------------------------------------------------
            # FIM DA FALA DO USUÁRIO
            # ------------------------------------------------------------------
            elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
                logger.info("🤫 [Azure] Usuário parou de falar")
                if self._is_greeting_mode:
                    self._is_greeting_mode = False

            elif event.type == ServerEventType.RESPONSE_CREATED:
                # Sempre que um novo response é criado, liberamos os deltas
                self._ignore_deltas = False

            # ------------------------------------------------------------------
            # ÁUDIO DO AGENTE (OUTPUT)
            # ------------------------------------------------------------------
            elif event.type == ServerEventType.RESPONSE_AUDIO_DELTA:
                if self._ignore_deltas:
                    # Útil para debug: mostra que o barge-in está cortando áudio
                    logger.debug("🔇 Delta de áudio do agente ignorado devido a barge-in")
                    continue

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
                # Só loga como "disse" se os deltas não foram ignorados por barge-in
                if self._ignore_deltas:
                    logger.info(f"🤖 (DESCARTADO) Agente teria dito: {event.transcript}")
                else:
                    logger.info(f"🤖 Agente disse: {event.transcript}")
                    self.is_agent_speaking = False
                    self._is_greeting_mode = False

                # Ao final do transcript, liberamos novamente os deltas
                self._ignore_deltas = False

            elif event.type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
                logger.info(f"👤 Transcrição usuário: {event.transcript}")

            elif event.type == ServerEventType.ERROR:
                logger.error(f"❌ Erro do servidor Azure: {event.error}")

    # ------------------------------------------------------------------
    # INGESTÃO DE ÁUDIO (CHAMADO PELO ROUTER TWILIO)
    # ------------------------------------------------------------------
    async def ingest_audio(self, audio_chunk: bytes):
        """
        Envia áudio de entrada (usuário) para o Azure.
        Chamado pelo controlador WebSocket.
        """
        if not self.connection:
            return

        try:
            await self.connection.input_audio_buffer.append(audio_chunk)
            await self.connection.input_audio_buffer.commit()
        except Exception as e:
            logger.error(f"Erro ao enviar áudio de entrada para Azure: {e}")

    # ------------------------------------------------------------------
    # LIMPEZA E SHUTDOWN
    # ------------------------------------------------------------------
    async def _cleanup(self):
        """
        Limpa recursos de forma segura.
        """
        try:
            if self.audio_processor:
                self.audio_processor.stop()
        except Exception:
            pass

        if self.connection:
            try:
                await self.connection.close()
            except Exception:
                pass

        logger.info("👋 Worker finalizado com sucesso")

    def shutdown(self):
        """
        Dispara sinal de shutdown para encerrar o loop de eventos.
        """
        self._shutdown_event.set()
