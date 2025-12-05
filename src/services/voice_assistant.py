import asyncio
import logging
import random
import time
from typing import Optional

from azure.core.credentials import AzureKeyCredential
from azure.identity.aio import DefaultAzureCredential
from azure.ai.voicelive.aio import connect, VoiceLiveConnection
from azure.ai.voicelive.models import (
    AudioEchoCancellation,
    AudioNoiseReduction,
    AzureStandardVoice,
    InputAudioFormat,
    Modality,
    OutputAudioFormat,
    RequestSession,
    ServerEventType,
    ServerVad,
)

from src.core.config import get_settings, AgentConfig
# Import condicional para manter compatibilidade com dev local
try:
    from src.services.audio_processor import AudioProcessor, AUDIO_AVAILABLE
except ImportError:
    AUDIO_AVAILABLE = False

logger = logging.getLogger(__name__)


class VoiceAssistantWorker:
    """Core do Assistente: Gerencia Conexão, Sessão e Eventos"""

    def __init__(self, agent_config: AgentConfig, settings=None, audio_output_handler=None, interruption_handler=None):
        self.settings = settings or get_settings()
        self.agent_config = agent_config
        self.connection: Optional[VoiceLiveConnection] = None
        self.audio_processor = None
        self.audio_output_handler = audio_output_handler
        self.interruption_handler = interruption_handler
        self._shutdown_event = asyncio.Event()

        # Sistema de Estados
        self.is_agent_speaking = False
        self._state_lock = asyncio.Lock()  # Protege leituras/escritas de estado crítico
        self._greeting_sent_at_monotonic: Optional[float] = None  # use monotonic clock
        self._is_greeting_mode = False
        self._last_vad_event_monotonic_ms = 0.0  # guarda em ms (monotonic)

        # Configurações de Proteção
        self._grace_period_seconds = getattr(self.settings, "GREETING_GRACE_PERIOD_SECONDS", 2)
        self._vad_debounce_ms = getattr(self.settings, "VAD_DEBOUNCE_MS", 300)
        self._greeting_delay = getattr(self.settings, "GREETING_DELAY_SECONDS", 0.6)

        # Reconexão
        self._reconnect_max_retries = getattr(self.settings, "RECONNECT_MAX_RETRIES", 5)
        self._reconnect_base_backoff = getattr(self.settings, "RECONNECT_BASE_BACKOFF", 1.0)

        logger.info(
            f"🚀 Worker inicializado | Env: {getattr(self.settings, 'APP_ENV', 'unknown')} | Voz: {self.agent_config.voice}"
        )
        logger.debug(
            f"🛡️ Proteções: Grace={self._grace_period_seconds}s | Debounce={self._vad_debounce_ms}ms | Delay={self._greeting_delay}s"
        )

    async def connect_and_run(self):
        """Loop principal de conexão com reconexão automática."""
        attempt = 0
        while not self._shutdown_event.is_set():
            try:
                # Autenticação
                if getattr(self.settings, "AZURE_VOICELIVE_API_KEY", None):
                    cred = AzureKeyCredential(self.settings.AZURE_VOICELIVE_API_KEY)
                else:
                    # Em servidores recomendamos chave; DefaultAzureCredential pode demorar
                    cred = DefaultAzureCredential()

                logger.info(f"🔌 Conectando ao modelo: {self.settings.AZURE_VOICELIVE_MODEL}.")

                async with connect(
                    endpoint=self.settings.AZURE_VOICELIVE_ENDPOINT,
                    credential=cred,
                    model=self.settings.AZURE_VOICELIVE_MODEL
                ) as conn:
                    # Se conectou com sucesso, zera contador de tentativas
                    attempt = 0
                    self.connection = conn

                    # Inicializa Áudio Local (Apenas se não for G711)
                    audio_config = self.agent_config.config.get('audio', {})
                    input_fmt_str = str(audio_config.get('input_format', 'PCM16')).upper()
                    is_pcm16 = input_fmt_str == 'PCM16'

                    if getattr(self.settings, "is_development", lambda: False)() and AUDIO_AVAILABLE and is_pcm16:
                        # AudioProcessor pode depender de conn internamente
                        self.audio_processor = AudioProcessor(conn)
                        self.audio_processor.start_capture()
                        self.audio_processor.start_playback()
                        logger.info("🎙️ Modo Development: Áudio Local Ativo")
                    else:
                        logger.info(f"ℹ️ Modo Headless/Telefonia: Áudio Local Desativado (Format: {input_fmt_str})")

                    # 1. Configura Sessão (VAD Calibrado)
                    await self._configure_session()

                    # 2. Agenda a Saudação para rodar EM PARALELO (com delay aumentado)
                    # Note: não marcamos greeting como enviado até que efetivamente seja disparado
                    asyncio.create_task(self._send_initial_greeting())

                    # 3. Inicia o processamento de eventos IMEDIATAMENTE (bloqueante neste contexto)
                    await self._process_events()

            except Exception as e:
                # Se ocorrer erro fora do contexto do "async with", tenta reconectar
                show_exc_info = getattr(self.settings, "is_development", lambda: False)() or getattr(self.settings, "is_staging", lambda: False)()
                logger.exception(f"❌ Erro no Worker durante loop de conexão: {e}", exc_info=show_exc_info)

                # Backoff exponencial com jitter
                attempt += 1
                if attempt > self._reconnect_max_retries:
                    logger.critical(f"🔴 Ultrapassado número máximo de tentativas ({self._reconnect_max_retries}). Encerrando.")
                    break
                backoff = self._reconnect_base_backoff * (2 ** (attempt - 1))
                jitter = random.uniform(0, backoff * 0.2)
                sleep_for = backoff + jitter
                logger.info(f"⏳ Tentando reconectar em {sleep_for:.1f}s (attempt {attempt}/{self._reconnect_max_retries})")
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=sleep_for)
                    # se o shutdown for setado, saímos imediatamente
                    break
                except asyncio.TimeoutError:
                    continue

        logger.info("🛑 connect_and_run finalizado (shutdown ou max retries atingido)")

    async def _configure_session(self):
        """Envia configurações para o Azure lendo das variáveis de ambiente."""
        # 1. Recupera Configuração de Codec
        audio_config = self.agent_config.config.get('audio', {})
        input_fmt_str = str(audio_config.get('input_format', 'PCM16')).upper()
        output_fmt_str = str(audio_config.get('output_format', 'PCM16')).upper()

        # Mapeamento Seguro de Formatos
        try:
            input_fmt = getattr(InputAudioFormat, input_fmt_str)
        except AttributeError:
            logger.warning(f"⚠️ Formato Input '{input_fmt_str}' inválido. Usando PCM16.")
            input_fmt = InputAudioFormat.PCM16

        try:
            output_fmt = getattr(OutputAudioFormat, output_fmt_str)
        except AttributeError:
            logger.warning(f"⚠️ Formato Output '{output_fmt_str}' inválido. Usando PCM16.")
            output_fmt = OutputAudioFormat.PCM16

        logger.info(f"🎛️ Configurando Áudio Sessão: Input={input_fmt} | Output={output_fmt}")

        # 2. DEFINIÇÃO DE VAD (Lendo das Variáveis de Ambiente)
        vad_config = ServerVad(
            threshold=getattr(self.settings, "VAD_THRESHOLD", 0.5),
            prefix_padding_ms=getattr(self.settings, "VAD_PREFIX_PADDING_MS", 100),
            silence_duration_ms=getattr(self.settings, "VAD_SILENCE_DURATION_MS", 600)
        )

        # 3. Configuração da Sessão (Lendo das Variáveis de Ambiente)
        session_config = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            instructions=self.agent_config.instructions,
            voice=AzureStandardVoice(name=self.agent_config.voice),
            input_audio_format=input_fmt,
            output_audio_format=output_fmt,
            turn_detection=vad_config,
            temperature=getattr(self.settings, "MODEL_TEMPERATURE", 0.0),
            max_response_output_tokens=getattr(self.settings, "MAX_RESPONSE_OUTPUT_TOKENS", 400)
        )

        # Executa update com try/except para capturar problemas de sessão
        try:
            await self.connection.session.update(session=session_config)
            logger.info(
                f"✅ Sessão configurada: VAD(t={vad_config.threshold}, s={vad_config.silence_duration_ms}ms) | "
                f"Temp: {getattr(self.settings, 'MODEL_TEMPERATURE', 0.0)} | "
                f"Max Tokens: {getattr(self.settings, 'MAX_RESPONSE_OUTPUT_TOKENS', 400)}"
            )
        except Exception as e:
            logger.exception(f"❗ Falha ao configurar sessão: {e}")
            raise

    async def _send_initial_greeting(self):
        """Envia a saudação após delay configurável, com proteção contra auto-resposta.

        Observações:
        - Usa monotonic clock para medir grace period reliably.
        - Marca o momento real do envio apenas quando a create() completar com sucesso.
        """
        try:
            # Delay para estabilização da conexão e da sessão
            await asyncio.sleep(self._greeting_delay)

            # Proteção: marca que estamos em modo greeting (impede que silêncio inicial dispare processamento)
            self._is_greeting_mode = True
            logger.debug(f"🛡️ Modo saudação ativado (aguardando envio) - delay {self._greeting_delay}s")

            # Prepara a instrução — preferimos usar as instructions do session quando disponíveis,
            # aqui usamos explicitamente uma instrução curta para forçar fala inicial.
            await self.connection.response.create(
                response={
                    "instructions": (
                        "O usuário atendeu o telefone. Diga sua saudação inicial definida nas suas instruções agora. "
                        "Seja natural e aguarde a resposta do usuário."
                    )
                }
            )

            # Marca o instante (monotonic) em que a saudação foi enviada com sucesso
            self._greeting_sent_at_monotonic = time.monotonic()
            logger.info("👋 Saudação inicial enviada com sucesso.")
            logger.debug(f"🕒 greeting_sent_at (monotonic) = {self._greeting_sent_at_monotonic}")

        except Exception as e:
            logger.warning(f"⚠️ Saudação inicial não pôde ser enviada (pode ser ignorado se a chamada caiu): {e}")
            # desativa o modo saudação se falhar
            self._is_greeting_mode = False
            self._greeting_sent_at_monotonic = None

    def _is_in_grace_period(self) -> bool:
        """Verifica se ainda está no período de proteção após a saudação usando clock monotônico."""
        if not self._greeting_sent_at_monotonic:
            return False
        elapsed = time.monotonic() - self._greeting_sent_at_monotonic
        return elapsed < float(self._grace_period_seconds)

    def _should_process_vad_event(self) -> bool:
        """Debouncing para evitar processar eventos VAD repetitivos (usa monotonic em ms)."""
        now_ms = time.monotonic() * 1000.0  # ms monotonic
        if (now_ms - self._last_vad_event_monotonic_ms) < float(self._vad_debounce_ms):
            # não processar — evento muito próximo do anterior
            return False
        self._last_vad_event_monotonic_ms = now_ms
        return True

    async def _process_events(self):
        """Processa eventos recebidos do Azure com Barge-in, Grace Period e Debouncing."""
        try:
            async for event in self.connection:
                if self._shutdown_event.is_set():
                    logger.debug("Shutdown requisitado — saindo do loop de eventos.")
                    break

                # ========== BARGE-IN (INTERRUPÇÃO) ==========
                if event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                    # Proteção 1: Grace Period após saudação
                    if self._is_in_grace_period() or self._is_greeting_mode:
                        logger.debug("🛡️ Grace period / greeting ativo - ignorando detecção de fala (proteção de saudação)")
                        continue

                    # Proteção 2: Debouncing (filtro de ruído de linha)
                    if not self._should_process_vad_event():
                        logger.debug("⏭️ Evento VAD ignorado (debouncing - muito próximo do anterior)")
                        continue

                    # Lógica de Barge-in
                    async with self._state_lock:
                        was_agent_speaking = self.is_agent_speaking

                    if was_agent_speaking:
                        logger.info("👤 Usuário falando: BARGE-IN DETECTADO! Interrompendo agente.")

                        # 1. Limpa áudio local (Dev)
                        try:
                            if self.audio_processor:
                                self.audio_processor.skip_pending_audio()
                        except Exception as e:
                            logger.debug(f"ℹ️ Falha ao limpar áudio local: {e}")

                        # 2. Handler externo de interrupção (fire-and-forget)
                        if self.interruption_handler:
                            asyncio.create_task(self._safe_call_interruption_handler())

                        # 3. Cancela resposta E limpa buffers (Non-Blocking)
                        asyncio.create_task(self._cancel_and_clear())

                        # Observação: o estado is_agent_speaking será atualizado quando
                        # recebermos o evento RESPONSE_AUDIO_TRANSCRIPT_DONE (ou similar).
                    else:
                        logger.debug("👤 Usuário falando: Turno normal (Agente estava em silêncio).")

                # ========== ÁUDIO DO AGENTE ==========
                elif event.type == ServerEventType.RESPONSE_AUDIO_DELTA:
                    # Rastreamento de estado quando o agente começa a falar
                    async with self._state_lock:
                        if not self.is_agent_speaking:
                            self.is_agent_speaking = True
                            logger.debug("🔊 Agente começou a falar (state is_agent_speaking=True)")

                    # Entrega do delta (respeitando backpressure / handler)
                    try:
                        if self.audio_output_handler:
                            # handler pode ser coroutine
                            maybe_coro = self.audio_output_handler(event.delta)
                            if asyncio.iscoroutine(maybe_coro):
                                await maybe_coro
                        elif self.audio_processor:
                            # queue_audio deve ser rápido; se lançar exceção, capturamos
                            self.audio_processor.queue_audio(event.delta)
                    except Exception as e:
                        logger.debug(f"ℹ️ Falha ao processar delta de áudio do agente: {e}")

                # ========== ERROS ==========
                elif event.type == ServerEventType.ERROR:
                    try:
                        # event.error pode não existir em todas versões; use getattr
                        err_msg = getattr(event, "error", None)
                        if err_msg and getattr(err_msg, "message", None):
                            logger.error(f"❌ Erro Azure: {err_msg.message}")
                        else:
                            logger.error("❌ Erro Azure recebido (detalhes indisponíveis).")
                    except Exception:
                        logger.exception("❌ Evento de erro recebido, falha ao logar conteúdo.")

                # ========== TRANSCRIÇÃO DO AGENTE ==========
                elif event.type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE:
                    # Se existir transcript, loga
                    transcript_text = getattr(event, "transcript", None)
                    logger.info(f"🤖 Agente: {transcript_text}")

                    # Rastreamento de estado quando o agente termina de falar
                    async with self._state_lock:
                        self.is_agent_speaking = False
                    logger.debug("🔇 Agente terminou de falar (state is_agent_speaking=False)")

                    # Finaliza modo saudação após primeira transcrição
                    if self._is_greeting_mode:
                        self._is_greeting_mode = False
                        logger.debug("✅ Modo saudação finalizado")

                # ========== TRANSCRIÇÃO DO USUÁRIO ==========
                elif event.type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
                    user_trans = getattr(event, "transcript", None)
                    logger.info(f"👤 Usuário: {user_trans}")

                # ========== DETECÇÃO DE SILÊNCIO ==========
                elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
                    # Ignora silêncio durante modo saudação
                    if self._is_greeting_mode:
                        logger.debug("🚫 Modo saudação - ignorando detecção de silêncio")
                        continue

                    logger.info("🛑 Silêncio detectado (VAD) - Processando provável fim de turno.")
                    # Aqui o comportamento depende da lógica externa (p.ex. envio do conteúdo para LLM).
                    # Mantemos a escuta para eventos subsequentes.

                else:
                    # Eventos não tratados explicitamente
                    logger.debug(f"ℹ️ Evento não tratado: {getattr(event, 'type', 'unknown')}")

        except Exception as e:
            # Se o loop for interrompido por exceção, propaga para forçar reconexão no connect_and_run
            logger.exception(f"❗ Exceção não tratada no loop de eventos: {e}")
            raise

    async def _safe_call_interruption_handler(self):
        """Wrapper que chama interruption_handler e captura exceções."""
        try:
            res = self.interruption_handler()
            if asyncio.iscoroutine(res):
                await res
        except Exception as e:
            logger.debug(f"ℹ️ interruption_handler falhou: {e}")

    async def _cancel_and_clear(self):
        """Cancela resposta E limpa buffer de entrada (barge-in completo)."""
        try:
            if not self.connection:
                logger.debug("ℹ️ _cancel_and_clear chamado sem conexão ativa.")
                return

            # Cancel response (se suportado)
            try:
                if hasattr(self.connection, "response") and hasattr(self.connection.response, "cancel"):
                    await self.connection.response.cancel()
                    logger.debug("✂️ response.cancel() foi chamado")
            except Exception as e:
                logger.debug(f"ℹ️ Falha ao cancelar response: {e}")

            # Limpa buffer de entrada (se suportado)
            try:
                if hasattr(self.connection, "input_audio_buffer") and hasattr(self.connection.input_audio_buffer, "clear"):
                    await self.connection.input_audio_buffer.clear()
                    logger.debug("🧹 input_audio_buffer.clear() foi chamado")
            except Exception as e:
                logger.debug(f"ℹ️ Falha ao limpar input_audio_buffer: {e}")

            # Tenta também limpar buffers de saída/assistente se existirem (algumas versões expõem output buffer)
            try:
                if hasattr(self.connection, "output_audio_buffer") and hasattr(self.connection.output_audio_buffer, "clear"):
                    await self.connection.output_audio_buffer.clear()
                    logger.debug("🧹 output_audio_buffer.clear() foi chamado")
            except Exception:
                # Não crítico se não existir
                pass

            logger.info("✂️ Resposta e buffers (quando aplicável) cancelados/limpos com sucesso.")
        except Exception as e:
            logger.debug(f"ℹ️ Cancelamento falhou/ignorando: {e}")

    async def _safe_cancel_response(self):
        """Helper para cancelar resposta sem crashar (DEPRECATED - usar _cancel_and_clear)."""
        try:
            if self.connection and hasattr(self.connection, "response") and hasattr(self.connection.response, "cancel"):
                await self.connection.response.cancel()
                logger.debug("✂️ Resposta do Azure cancelada com sucesso")
        except Exception as e:
            logger.debug(f"ℹ️ Cancelamento de resposta falhou/ignorado: {e}")

    def shutdown(self):
        """Encerra o worker gracefully."""
        logger.info("🛑 Encerrando Voice Assistant Worker.")
        self._shutdown_event.set()
        # Tenta fechar audio processor de forma segura
        try:
            if self.audio_processor:
                self.audio_processor.shutdown()
        except Exception as e:
            logger.debug(f"ℹ️ Falha ao encerrar audio_processor: {e}")

        # Se houver conexão ativa, tenta fechá-la assincronamente (não bloqueante aqui)
        try:
            conn = self.connection
            if conn:
                # se conn é um context manager, o 'async with' se encarrega de fechar,
                # mas podemos tentar um close se a implementação expuser.
                close_coro = getattr(conn, "close", None)
                if callable(close_coro):
                    # dispara close sem aguardar
                    asyncio.create_task(close_coro())
        except Exception as e:
            logger.debug(f"ℹ️ Falha ao disparar fechamento da conexão: {e}")