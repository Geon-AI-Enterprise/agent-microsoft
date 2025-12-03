"""
Voice Assistant Worker Service

Core do Assistente: Gerencia Conexão, Sessão e Eventos do Azure VoiceLive.
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
from src.services.audio_processor import AudioProcessor, AUDIO_AVAILABLE

logger = logging.getLogger(__name__)


class VoiceAssistantWorker:
    """Core do Assistente: Gerencia Conexão, Sessão e Eventos"""

    def __init__(self, agent_config: AgentConfig, settings=None, audio_output_handler=None):
        """
        Inicializa o Worker com configuração injetada
        
        Args:
            agent_config: Configuração do agente (obrigatório)
            settings: Settings da aplicação (opcional)
            audio_output_handler: Callback assíncrono para enviar áudio de saída (opcional)
                                 Assinatura: async def handler(audio_data: bytes)
        """
        self.settings = settings or get_settings()
        self.agent_config = agent_config  # Config agora vem de fora (injetada)
        self.connection: Optional[VoiceLiveConnection] = None
        self.audio_processor: Optional[AudioProcessor] = None
        self.audio_output_handler = audio_output_handler  # Para WebSocket na Fase 3
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
                
                # Inicializa Áudio APENAS em Development
                if self.settings.is_development() and AUDIO_AVAILABLE:
                    self.audio_processor = AudioProcessor(conn)
                    self.audio_processor.start_capture()
                    self.audio_processor.start_playback()
                    logger.info("🎙️  Modo Development: Áudio Local Ativo")
                else:
                    logger.info("ℹ️  Modo Headless: Áudio Local Desativado (Staging/Prod)")

                # Configura Sessão
                await self._configure_session()
                
                # Loop de Eventos
                await self._process_events()

        except Exception as e:
            logger.critical(f"❌ Erro fatal no Worker: {e}", exc_info=self.settings.is_development())
            # Em produção, pode implementar lógica de retry aqui

    async def _configure_session(self):
        """Envia configurações do agent_config.json para o Azure"""
        
        # Mapeia configurações do JSON para objetos do SDK
        vad_config = ServerVad(
            threshold=self.agent_config.config['turn_detection']['threshold'],
            prefix_padding_ms=self.agent_config.config['turn_detection']['prefix_padding_ms'],
            silence_duration_ms=self.agent_config.config['turn_detection']['silence_duration_ms']
        )
        
        # Redução de ruído (mapeamento string -> objeto)
        noise_type = self.agent_config.config['audio']['noise_reduction']
        noise_config = AudioNoiseReduction(type=noise_type) if noise_type else None

        session_config = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            instructions=self.agent_config.instructions,
            voice=AzureStandardVoice(name=self.agent_config.voice),
            input_audio_format=InputAudioFormat.PCM16,
            output_audio_format=OutputAudioFormat.PCM16,
            turn_detection=vad_config,
            input_audio_echo_cancellation=AudioEchoCancellation() if self.agent_config.config['audio']['echo_cancellation'] else None,
            input_audio_noise_reduction=noise_config,
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

            # 1. Logs de Eventos (filtrados em Prod)
            if self.settings.is_development():
                logger.debug(f"Evento: {event.type}")

            # 2. Usuário começou a falar (Barge-in Logic)
            if event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                logger.info("👤 Usuário detectado falando...")
                if self.audio_processor:
                    self.audio_processor.skip_pending_audio()
                
                # Cancela resposta atual (Barge-in)
                await self.connection.response.cancel()

            # 3. Usuário parou de falar
            elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
                logger.info("👤 Usuário parou de falar. Processando...")

            # 4. Recebimento de Áudio
            elif event.type == ServerEventType.RESPONSE_AUDIO_DELTA:
                # Se temos handler externo (WebSocket), envia para lá
                if self.audio_output_handler:
                    await self.audio_output_handler(event.delta)
                # Caso contrário, usa AudioProcessor local (Dev)
                elif self.audio_processor:
                    self.audio_processor.queue_audio(event.delta)

            # 5. Erros do Servidor
            elif event.type == ServerEventType.ERROR:
                logger.error(f"❌ Erro Azure: {event.error.message}")

            # 6. Transcrição (Opcional - útil para logs)
            elif event.type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE:
                logger.info(f"🤖 Agente disse: {event.transcript}")
            
            elif event.type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
                logger.info(f"👤 Usuário disse: {event.transcript}")

    def shutdown(self):
        """Limpeza de recursos"""
        self._shutdown_event.set()
        if self.audio_processor:
            self.audio_processor.shutdown()
