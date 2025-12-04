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
                
                # Inicializa Áudio Local (Apenas Dev/PCM16)
                # Se estiver usando G711 (Twilio), não ativamos o processador local
                is_pcm16 = self.agent_config.config.get('audio', {}).get('input_format') == 'PCM16'
                if self.settings.is_development() and AUDIO_AVAILABLE and is_pcm16:
                    self.audio_processor = AudioProcessor(conn)
                    self.audio_processor.start_capture()
                    self.audio_processor.start_playback()
                    logger.info("🎙️ Modo Development: Áudio Local Ativo")
                else:
                    logger.info("ℹ️ Modo Headless/Telefonia: Áudio Local Desativado")

                # Configura Sessão
                await self._configure_session()

                # --- SAUDAÇÃO INICIAL (ALÔ) ---
                logger.info("👋 Enviando saudação inicial...")
                await self.connection.response.create(
                    response={
                        "instructions": "Diga apenas 'Alô' e aguarde."
                    }
                )
                
                # Loop de Eventos
                await self._process_events()

        except Exception as e:
            # Habilita stack trace em staging/dev
            show_exc_info = self.settings.is_development() or self.settings.is_staging()
            logger.critical(f"❌ Erro fatal no Worker: {e}", exc_info=show_exc_info)

    async def _configure_session(self):
        """Envia configurações para o Azure com suporte a Codecs"""
        
        # 1. Mapeamento de Formatos (PCM16 vs G711)
        audio_config = self.agent_config.config.get('audio', {})
        input_fmt_str = audio_config.get('input_format', 'PCM16')
        output_fmt_str = audio_config.get('output_format', 'PCM16')

        # Mapeia string do JSON para Enum do Azure SDK
        # Nota: G711_ULAW é o padrão para Twilio
        input_fmt = getattr(InputAudioFormat, input_fmt_str, InputAudioFormat.PCM16)
        output_fmt = getattr(OutputAudioFormat, output_fmt_str, OutputAudioFormat.PCM16)

        logger.info(f"🎛️ Configurando Áudio: Input={input_fmt} | Output={output_fmt}")

        vad_config = ServerVad(
            threshold=self.agent_config.config['turn_detection']['threshold'],
            prefix_padding_ms=self.agent_config.config['turn_detection']['prefix_padding_ms'],
            silence_duration_ms=self.agent_config.config['turn_detection']['silence_duration_ms']
        )
        
        session_config = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            instructions=self.agent_config.instructions,
            voice=AzureStandardVoice(name=self.agent_config.voice),
            input_audio_format=input_fmt,   # Dinâmico
            output_audio_format=output_fmt, # Dinâmico
            turn_detection=vad_config,
            temperature=self.agent_config.temperature,
            max_response_output_tokens=self.agent_config.max_tokens
        )
        
        await self.connection.session.update(session=session_config)
        logger.info("✅ Sessão configurada com sucesso")

    async def _process_events(self):
        """Processa eventos recebidos do Azure"""
        async for event in self.connection:
            if self._shutdown_event.is_set():
                break

            # Barge-in (Interrupção)
            if event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                logger.info("👤 Usuário falando (Barge-in)...")
                if self.audio_processor:
                    self.audio_processor.skip_pending_audio()
                
                await self.connection.response.cancel()
                
                if self.interruption_handler:
                    await self.interruption_handler()

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

    def shutdown(self):
        self._shutdown_event.set()
        if self.audio_processor:
            self.audio_processor.shutdown()