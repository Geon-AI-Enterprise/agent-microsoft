"""
Voice Assistant Worker Service

Core do Assistente: Gerencia Conexão, Sessão e Eventos do Azure VoiceLive.
Adaptado para suportar telefonia (G.711 Mu-Law).

Correções v2.2:
- Removido código duplicado
- Implementado grace period para proteção de saudação
- Adicionado debouncing para eventos VAD
- Melhorado logging e rastreamento de estados
- NOVO: Limpeza de input_audio_buffer no barge-in
- NOVO: Modo saudação para prevenir auto-resposta
"""

import asyncio
import logging
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
        self._greeting_sent_at = None
        self._is_greeting_mode = False  # NOVO: Flag para modo saudação
        self._last_vad_event = 0
        
        # Configurações de Proteção
        self._grace_period_seconds = getattr(settings, 'GREETING_GRACE_PERIOD_SECONDS', 2.0)
        self._vad_debounce_ms = getattr(settings, 'VAD_DEBOUNCE_MS', 300)
        self._greeting_delay = getattr(settings, 'GREETING_DELAY_SECONDS', 1.5)
        
        logger.info(f"🚀 Worker inicializado | Env: {self.settings.APP_ENV} | Voz: {self.agent_config.voice}")
        logger.debug(f"🛡️ Proteções: Grace={self._grace_period_seconds}s | Debounce={self._vad_debounce_ms}ms | Delay={self._greeting_delay}s")

    async def connect_and_run(self):
        """Loop principal de conexão"""
        try:
            # Autenticação
            if self.settings.AZURE_VOICELIVE_API_KEY:
                cred = AzureKeyCredential(self.settings.AZURE_VOICELIVE_API_KEY)
            else:
                cred = DefaultAzureCredential()

            logger.info(f"🔌 Conectando ao modelo: {self.settings.AZURE_VOICELIVE_MODEL}...")
            
            async with connect(
                endpoint=self.settings.AZURE_VOICELIVE_ENDPOINT,
                credential=cred,
                model=self.settings.AZURE_VOICELIVE_MODEL
            ) as conn:
                self.connection = conn
                
                # Inicializa Áudio Local (Apenas se não for G711)
                audio_config = self.agent_config.config.get('audio', {})
                input_fmt_str = str(audio_config.get('input_format', 'PCM16')).upper()
                is_pcm16 = input_fmt_str == 'PCM16'
                
                if self.settings.is_development() and AUDIO_AVAILABLE and is_pcm16:
                    self.audio_processor = AudioProcessor(conn)
                    self.audio_processor.start_capture()
                    self.audio_processor.start_playback()
                    logger.info("🎙️ Modo Development: Áudio Local Ativo")
                else:
                    logger.info(f"ℹ️ Modo Headless/Telefonia: Áudio Local Desativado (Format: {input_fmt_str})")

                # 1. Configura Sessão (VAD Calibrado)
                await self._configure_session()

                # 2. Agenda a Saudação para rodar EM PARALELO (com delay aumentado)
                asyncio.create_task(self._send_initial_greeting())
                
                # 3. Inicia o processamento de eventos IMEDIATAMENTE
                await self._process_events()

        except Exception as e:
            show_exc_info = self.settings.is_development() or self.settings.is_staging()
            logger.critical(f"❌ Erro fatal no Worker: {e}", exc_info=show_exc_info)

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
            threshold=self.settings.VAD_THRESHOLD,
            prefix_padding_ms=self.settings.VAD_PREFIX_PADDING_MS,
            silence_duration_ms=self.settings.VAD_SILENCE_DURATION_MS
        )
        
        # 3. Configuração da Sessão (Lendo das Variáveis de Ambiente)
        session_config = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            instructions=self.agent_config.instructions,
            voice=AzureStandardVoice(name=self.agent_config.voice),
            input_audio_format=input_fmt,
            output_audio_format=output_fmt,
            turn_detection=vad_config,
            temperature=self.settings.MODEL_TEMPERATURE,
            max_response_output_tokens=self.settings.MAX_RESPONSE_OUTPUT_TOKENS 
        )
        
        await self.connection.session.update(session=session_config)
        logger.info(f"✅ Sessão configurada: VAD(t={vad_config.threshold}, s={vad_config.silence_duration_ms}ms) | Temp: {self.settings.MODEL_TEMPERATURE} | Max Tokens: {self.settings.MAX_RESPONSE_OUTPUT_TOKENS}")

    async def _send_initial_greeting(self):
        """Envia a saudação após delay configurável, com proteção contra auto-resposta"""
        try:
            # CORREÇÃO: Ativa proteções ANTES de enviar a saudação
            self._greeting_sent_at = asyncio.get_event_loop().time()
            self._is_greeting_mode = True
            logger.debug(f"🛡️ Modo saudação ativado (grace={self._grace_period_seconds}s)")
            
            # Delay para estabilização da conexão
            await asyncio.sleep(self._greeting_delay)
            
            logger.info("👋 Disparando saudação inicial...")
            
            # Força o modelo a falar com instructions
            await self.connection.response.create(
                response={
                    "instructions": "O usuário atendeu o telefone. Diga sua saudação inicial definida nas suas instruções agora. Seja natural e aguarde a resposta do usuário."
                }
            )
            
        except Exception as e:
            logger.warning(f"⚠️ Saudação inicial não pôde ser enviada (pode ser ignorado se a chamada caiu): {e}")
            self._is_greeting_mode = False  # Desativa em caso de erro

    def _is_in_grace_period(self) -> bool:
        """Verifica se ainda está no período de proteção após a saudação"""
        if not self._greeting_sent_at:
            return False
        elapsed = asyncio.get_event_loop().time() - self._greeting_sent_at
        return elapsed < self._grace_period_seconds

    def _should_process_vad_event(self) -> bool:
        """Debouncing para evitar processar eventos VAD repetitivos"""
        now = asyncio.get_event_loop().time() * 1000  # em ms
        if (now - self._last_vad_event) < self._vad_debounce_ms:
            return False
        self._last_vad_event = now
        return True

    async def _process_events(self):
        """Processa eventos recebidos do Azure com Barge-in, Grace Period e Debouncing"""
        async for event in self.connection:
            if self._shutdown_event.is_set():
                break

            # ========== BARGE-IN (INTERRUPÇÃO) ==========
            if event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                
                # Proteção 1: Grace Period após saudação
                if self._is_in_grace_period():
                    logger.debug("🛡️ Grace period ativo - ignorando detecção de fala (proteção de saudação)")
                    continue
                
                # Proteção 2: Debouncing
                if not self._should_process_vad_event():
                    logger.debug("⏭️ Evento VAD ignorado (debouncing - muito próximo do anterior)")
                    continue
                
                # Lógica de Barge-in
                if self.is_agent_speaking:
                    logger.info("👤 Usuário falando: BARGE-IN DETECTADO! Interrompendo agente.")
                    
                    # 1. Limpa áudio local (Dev)
                    if self.audio_processor:
                        self.audio_processor.skip_pending_audio()
                    
                    # 2. Limpa buffer do Twilio (Prod) - ASYNC/FIRE-AND-FORGET
                    if self.interruption_handler:
                        asyncio.create_task(self.interruption_handler())

                    # 3. CORREÇÃO: Cancela resposta E limpa buffer de entrada
                    asyncio.create_task(self._cancel_and_clear())
                    
                    # Reseta o estado
                    self.is_agent_speaking = False
                    
                else:
                    logger.debug("👤 Usuário falando: Turno normal (Agente estava em silêncio).")

            # ========== ÁUDIO DO AGENTE ==========
            elif event.type == ServerEventType.RESPONSE_AUDIO_DELTA:
                # Rastreamento de estado quando o agente começa a falar
                if not self.is_agent_speaking:
                    self.is_agent_speaking = True
                    logger.debug("🔊 Agente começou a falar")

                if self.audio_output_handler:
                    await self.audio_output_handler(event.delta)
                elif self.audio_processor:
                    self.audio_processor.queue_audio(event.delta)

            # ========== ERROS ==========
            elif event.type == ServerEventType.ERROR:
                logger.error(f"❌ Erro Azure: {event.error.message}")

            # ========== TRANSCRIÇÃO DO AGENTE ==========
            elif event.type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE:
                logger.info(f"🤖 Agente: {event.transcript}")
                
                # Rastreamento de estado quando o agente termina de falar
                self.is_agent_speaking = False
                logger.debug("🔇 Agente terminou de falar")
                
                # CORREÇÃO: Finaliza modo saudação após primeira transcrição
                if self._is_greeting_mode:
                    self._is_greeting_mode = False
                    logger.debug("✅ Modo saudação finalizado")

            # ========== TRANSCRIÇÃO DO USUÁRIO ==========
            elif event.type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
                logger.info(f"👤 Usuário: {event.transcript}")
            
            # ========== DETECÇÃO DE SILÊNCIO ==========
            elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
                # CORREÇÃO: Ignora silêncio durante modo saudação
                if self._is_greeting_mode:
                    logger.debug("🚫 Modo saudação - ignorando detecção de silêncio")
                    continue
                
                logger.info("🛑 Silêncio detectado (VAD) - Processando resposta...")

    async def _cancel_and_clear(self):
        """NOVO: Cancela resposta E limpa buffer de entrada (barge-in completo)"""
        try:
            if self.connection:
                await self.connection.response.cancel()
                await self.connection.input_audio_buffer.clear()
                logger.info("✂️ Resposta e buffer de entrada cancelados")
        except Exception as e:
            logger.debug(f"ℹ️ Cancelamento falhou/ignorado: {e}")

    async def _safe_cancel_response(self):
        """Helper para cancelar resposta sem crashar em caso de erro (DEPRECATED - usar _cancel_and_clear)"""
        try:
            if self.connection:
                await self.connection.response.cancel()
                logger.debug("✂️ Resposta do Azure cancelada com sucesso")
        except Exception as e:
            logger.debug(f"ℹ️ Cancelamento de resposta falhou/ignorado: {e}")

    def shutdown(self):
        """Encerra o worker gracefully"""
        logger.info("🛑 Encerrando Voice Assistant Worker...")
        self._shutdown_event.set()
        if self.audio_processor:
            self.audio_processor.shutdown()