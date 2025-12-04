"""
Voice Assistant Worker Service

Core do Assistente: Gerencia Conexão, Sessão e Eventos do Azure VoiceLive.
Adaptado para suportar telefonia (G.711 Mu-Law).
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
        
        logger.info(f"🚀 Worker inicializado | Env: {self.settings.APP_ENV} | Voz: {self.agent_config.voice}")

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

                # 2. Agenda a Saudação para rodar EM PARALELO
                asyncio.create_task(self._send_initial_greeting())
                
                # 3. Inicia o processamento de eventos IMEDIATAMENTE
                await self._process_events()

        except Exception as e:
            show_exc_info = self.settings.is_development() or self.settings.is_staging()
            logger.critical(f"❌ Erro fatal no Worker: {e}", exc_info=show_exc_info)

    async def _configure_session(self):
        """Envia configurações para o Azure com VAD calibrado para Telefonia"""
        
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

        # 2. DEFINIÇÃO DE VAD (Calibrado para Telefonia Real)
        vad_config = ServerVad(
            threshold=self.settings.VAD_THRESHOLD,
            prefix_padding_ms=self.settings.VAD_PREFIX_PADDING_MS,
            silence_duration_ms=self.settings.VAD_SILENCE_DURATION_MS
        )
        
        # 3. Configuração da Sessão
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
        logger.info(f"✅ Sessão configurada: VAD(t={vad_config.threshold}, s={vad_config.silence_duration_ms}ms)")

    async def _send_initial_greeting(self):
        """Envia a saudação após um breve delay, permitindo que o loop principal inicie"""
        try:
            # Pequeno delay para garantir que a conexão está estável
            await asyncio.sleep(0.5)
            
            logger.info("👋 Disparando saudação inicial...")
            
            # Força o modelo a falar com instructions
            await self.connection.response.create(
                response={
                    "instructions": "O usuário atendeu o telefone. Diga sua saudação inicial definida nas suas instruções agora. Seja natural e aguarde a resposta do usuário."
                }
            )
        except Exception as e:
            logger.warning(f"⚠️ Saudação inicial não pôde ser enviada (pode ser ignorado se a chamada caiu): {e}")

    async def _process_events(self):
        """Processa eventos recebidos do Azure com Barge-in Não-Bloqueante"""
        async for event in self.connection:
            if self._shutdown_event.is_set():
                break

            # Barge-in (Interrupção)
            if event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                logger.info("👤 Usuário falando (Barge-in)...")
                
                # 1. Limpa áudio local (Dev)
                if self.audio_processor:
                    self.audio_processor.skip_pending_audio()
                
                # 2. Limpa buffer do Twilio (Prod) - ASYNC/FIRE-AND-FORGET
                if self.interruption_handler:
                    asyncio.create_task(self.interruption_handler())

                # 3. Cancela resposta no Azure - ASYNC/FIRE-AND-FORGET
                asyncio.create_task(self._safe_cancel_response())

            elif event.type == ServerEventType.RESPONSE_AUDIO_DELTA:
                if self.audio_output_handler:
                    await self.audio_output_handler(event.delta)
                elif self.audio_processor:
                    self.audio_processor.queue_audio(event.delta)

            elif event.type == ServerEventType.ERROR:
                logger.error(f"❌ Erro Azure: {event.error.message}")

            elif event.type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE:
                logger.info(f"🤖 Agente: {event.transcript}")

            elif event.type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
                logger.info(f"👤 Usuário: {event.transcript}")
            
            elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
                logger.info("🛑 Detecção de silêncio (VAD Stopped) - Processando resposta...")

    async def _safe_cancel_response(self):
        """Helper para cancelar resposta sem crashar em caso de erro"""
        try:
            if self.connection:
                await self.connection.response.cancel()
        except Exception as e:
            logger.debug(f"Info: Cancelamento de resposta falhou/ignorado: {e}")

    def shutdown(self):
        self._shutdown_event.set()
        if self.audio_processor:
            self.audio_processor.shutdown()