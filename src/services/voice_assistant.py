"""
Voice Assistant Worker Service - Arquitetura Simplificada

=============================================================================
ARQUITETURA: TWILIO COMO "PIPE BURRO"
=============================================================================

Este módulo gerencia a sessão com o Azure VoiceLive de forma ENXUTA:
- Abre e fecha a conexão com Azure
- Recebe áudio do usuário via `send_user_audio(pcm_bytes)`
- Expõe áudio do agente via `iter_agent_audio()` (gerador assíncrono)

IMPORTANTE: Este módulo NÃO realiza:
- VAD (detecção de voz) → Responsabilidade do Azure (Server VAD habilitado)
- Barge-in → Responsabilidade do Azure
- Controle de turnos → Responsabilidade do Azure
- Commit manual de buffer → Server VAD faz isso automaticamente

O Azure VoiceLive com Server VAD cuida de:
- Detectar início/fim de fala do usuário
- Interromper resposta quando usuário fala (barge-in)
- Gerenciar turnos de conversação
=============================================================================
"""

import asyncio
import logging
from typing import Optional, AsyncIterator

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

logger = logging.getLogger(__name__)


class VoiceAssistantWorker:
    """
    Worker enxuto para gerenciar a sessão de voz com Azure VoiceLive.
    
    Responsabilidades:
    - Abrir/fechar conexão com Azure
    - Configurar sessão com Server VAD
    - Receber áudio do usuário (send_user_audio)
    - Expor áudio do agente (iter_agent_audio)
    - Enviar saudação inicial (se configurado)
    
    NÃO responsável por:
    - VAD, barge-in, controle de turnos (delegado ao Azure)
    """

    def __init__(
        self,
        agent_config: AgentConfig,
        settings=None,
    ):
        """
        Inicializa o worker.
        
        Args:
            agent_config: Configurações do agente (voz, modelo, etc.)
            settings: Configurações da aplicação (credenciais Azure, etc.)
        """
        self.settings = settings or get_settings()
        self.agent_config = agent_config
        self.connection: Optional[VoiceLiveConnection] = None

        # Fila para áudio de saída do agente (Azure → Twilio)
        self._agent_audio_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()

        # Controle de shutdown
        self._shutdown_event = asyncio.Event()

        # Configurações de saudação
        self._greeting_delay = getattr(self.settings, "GREETING_DELAY_SECONDS", 1.0)

        logger.info(f"🚀 Worker inicializado | Voz: {self.agent_config.voice}")

    # ==========================================================================
    # CONEXÃO E CICLO DE VIDA
    # ==========================================================================
    async def connect_and_run(self):
        """
        Gerencia o ciclo de vida completo da conexão com o Azure.
        
        1. Estabelece conexão com Azure VoiceLive
        2. Configura sessão com Server VAD
        3. Dispara saudação inicial (se configurado)
        4. Processa eventos do Azure até shutdown
        """
        try:
            # 1. Configuração de Credenciais
            if getattr(self.settings, "AZURE_VOICELIVE_API_KEY", None):
                cred = AzureKeyCredential(self.settings.AZURE_VOICELIVE_API_KEY)
            else:
                cred = DefaultAzureCredential()

            # 2. Abre Conexão com o Azure VoiceLive
            async with connect(
                endpoint=self.settings.AZURE_VOICELIVE_ENDPOINT,
                credential=cred,
                model=self.settings.AZURE_VOICELIVE_MODEL,
            ) as conn:
                self.connection = conn
                logger.info("✅ Conexão com Azure VoiceLive estabelecida")

                # 3. Configura a Sessão (com Server VAD)
                await self._configure_session()

                # 4. Inicia Saudação em background (não bloqueia)
                asyncio.create_task(self._send_greeting_if_needed())

                # 5. Loop Principal de Eventos
                await self._process_events()

        except Exception as e:
            logger.error(f"❌ Erro crítico na conexão com Azure VoiceLive: {e}", exc_info=True)
        finally:
            # Sinaliza fim do stream de áudio
            await self._agent_audio_queue.put(None)
            await self._cleanup()

    # ==========================================================================
    # CONFIGURAÇÃO DE SESSÃO COM SERVER VAD
    # ==========================================================================
    async def _configure_session(self):
        """
        Configura a sessão no Azure VoiceLive com Server VAD habilitado.
        
        Server VAD (Voice Activity Detection) faz:
        - Detecta início/fim de fala automaticamente
        - Commit automático do buffer de áudio
        - Gerencia barge-in nativamente
        """
        logger.info("⚙️ Configurando sessão com Server VAD...")

        # Configuração de voz do agente
        voice = AzureStandardVoice(
            name=self.agent_config.voice,
            role="assistant",
        )

        # Server VAD - TODA a inteligência de detecção de fala fica aqui
        vad = ServerVad(
            enable_vad=True,
            noise_suppression_level="high",
            # Parâmetros opcionais do AgentConfig (se existirem)
            # threshold=getattr(self.agent_config, 'vad_threshold', None),
            # silence_duration_ms=getattr(self.agent_config, 'silence_duration_ms', None),
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
        logger.info("✅ Sessão configurada com Server VAD habilitado")

    # ==========================================================================
    # SAUDAÇÃO INICIAL
    # ==========================================================================
    async def _send_greeting_if_needed(self):
        """
        Envia saudação inicial após pequeno delay.
        
        Se o AgentConfig tiver campo 'greeting', envia como primeira mensagem.
        O delay evita problemas de timing com o estabelecimento da conexão.
        """
        greeting = getattr(self.agent_config, "greeting", None)
        if not greeting:
            # Tenta também no config dict
            greeting = self.agent_config.config.get("greeting") if hasattr(self.agent_config, "config") else None
        
        if not greeting:
            return

        await asyncio.sleep(self._greeting_delay)
        
        if self._shutdown_event.is_set():
            return

        try:
            logger.info("💬 Enviando saudação inicial...")
            await self.connection.request.send(input_text=greeting)
        except Exception as e:
            logger.error(f"❌ Erro ao enviar saudação inicial: {e}")

    # ==========================================================================
    # LOOP PRINCIPAL DE EVENTOS (SIMPLIFICADO)
    # ==========================================================================
    async def _process_events(self):
        """
        Processa eventos do Azure VoiceLive.
        
        Este loop é SIMPLES porque toda a lógica de VAD/barge-in está no Azure:
        - Recebe áudio do agente → enfileira para envio ao Twilio
        - Recebe eventos de fala → apenas loga (Azure já cuida do barge-in)
        - Recebe transcrições → loga para debug/auditoria
        """
        async for event in self.connection:
            if self._shutdown_event.is_set():
                break

            # ------------------------------------------------------------------
            # ÁUDIO DO AGENTE (OUTPUT) - Enfileira para envio ao Twilio
            # ------------------------------------------------------------------
            if event.type == ServerEventType.RESPONSE_AUDIO_DELTA:
                # Enfileira os bytes PCM 24k para serem convertidos e enviados
                await self._agent_audio_queue.put(event.delta)

            # ------------------------------------------------------------------
            # EVENTOS DE VAD (Apenas logging - Azure cuida de tudo)
            # ------------------------------------------------------------------
            elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                # Azure detectou que usuário começou a falar
                # Se havia resposta em andamento, Azure já interrompe automaticamente
                logger.info("🗣️ [Azure VAD] Usuário começou a falar")

            elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
                # Azure detectou que usuário parou de falar
                # Azure vai processar a fala e gerar resposta automaticamente
                logger.info("🤫 [Azure VAD] Usuário parou de falar")

            # ------------------------------------------------------------------
            # EVENTOS DE RESPOSTA
            # ------------------------------------------------------------------
            elif event.type == ServerEventType.RESPONSE_CREATED:
                logger.debug("📝 Nova resposta criada pelo Azure")

            elif event.type == ServerEventType.RESPONSE_DONE:
                logger.debug("✅ Resposta do Azure finalizada")

            # ------------------------------------------------------------------
            # TRANSCRIÇÕES (Logging para debug/auditoria)
            # ------------------------------------------------------------------
            elif event.type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE:
                logger.info(f"🤖 Agente disse: {event.transcript}")

            elif event.type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
                logger.info(f"👤 Usuário disse: {event.transcript}")

            # ------------------------------------------------------------------
            # ERROS
            # ------------------------------------------------------------------
            elif event.type == ServerEventType.ERROR:
                logger.error(f"❌ Erro do Azure: {event.error}")

    # ==========================================================================
    # API PÚBLICA: ENTRADA DE ÁUDIO (Twilio → Azure)
    # ==========================================================================
    async def send_user_audio(self, pcm_bytes: bytes) -> None:
        """
        Envia áudio do usuário para o Azure.
        
        Chamado pelo WebSocket handler quando recebe áudio do Twilio.
        
        NOTA: Com Server VAD habilitado, NÃO fazemos commit() manual.
        O Azure detecta automaticamente quando o usuário para de falar
        e faz o commit internamente.
        
        Args:
            pcm_bytes: Bytes PCM16 24 kHz já convertidos pelo transcoder
        """
        if not self.connection:
            return

        try:
            # Apenas append - Server VAD cuida do commit automaticamente
            await self.connection.input_audio_buffer.append(pcm_bytes)
        except Exception as e:
            logger.error(f"❌ Erro ao enviar áudio para Azure: {e}")

    # ==========================================================================
    # API PÚBLICA: SAÍDA DE ÁUDIO (Azure → Twilio)
    # ==========================================================================
    async def iter_agent_audio(self) -> AsyncIterator[bytes]:
        """
        Gerador assíncrono que produz chunks de áudio do agente.
        
        Uso no routes.py:
        ```python
        async for pcm_bytes in worker.iter_agent_audio():
            base64_chunk = transcoder.azure_to_twilio(pcm_bytes)
            await websocket.send_json({"event": "media", ...})
        ```
        
        Yields:
            Bytes PCM16 24 kHz para serem convertidos e enviados ao Twilio
        """
        while True:
            chunk = await self._agent_audio_queue.get()
            if chunk is None:
                # Sinal de finalização
                break
            yield chunk

    # ==========================================================================
    # LIMPEZA E SHUTDOWN
    # ==========================================================================
    async def _cleanup(self):
        """Limpa recursos de forma segura."""
        if self.connection:
            try:
                await self.connection.close()
            except Exception:
                pass

        logger.info("👋 Worker finalizado")

    def shutdown(self):
        """Dispara sinal de shutdown para encerrar o loop de eventos."""
        self._shutdown_event.set()
