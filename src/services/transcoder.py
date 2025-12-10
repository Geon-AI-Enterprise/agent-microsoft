"""
Audio Transcoder Service - Conversão de Formato Twilio ↔ Azure

=============================================================================
ARQUITETURA: TWILIO COMO "PIPE BURRO"
=============================================================================

Este módulo é responsável APENAS por conversão de formato de áudio:
- Twilio → Azure: 8 kHz μ-law (base64) → 24 kHz PCM16 (bytes)
- Azure → Twilio: 24 kHz PCM16 (bytes) → 8 kHz μ-law (base64)

IMPORTANTE: Este módulo NÃO realiza:
- VAD (detecção de voz) → Responsabilidade do Azure (Server VAD)
- Barge-in → Responsabilidade do Azure
- Controle de turnos → Responsabilidade do Azure
- Análise de energia/silêncio → Responsabilidade do Azure

O backend atua apenas como proxy de áudio, convertendo formatos entre Twilio e Azure.
=============================================================================
"""

import audioop
import base64
import logging
from typing import Optional, Union, List

logger = logging.getLogger(__name__)


class AudioTranscoder:
    """
    Conversor de áudio entre formatos Twilio e Azure.
    
    Fluxo:
    - Twilio (8 kHz μ-law, base64) ←→ Azure (24 kHz PCM16, bytes)
    
    Mantém um pequeno jitter buffer (2-4 frames) para garantir
    pacotes de áudio coesos e evitar áudio picotado.
    """

    # Tamanho mínimo de chunk para a Twilio (20ms de áudio μ-law @ 8kHz = 160 bytes)
    MIN_TWILIO_CHUNK_SIZE = 160
    
    # Tamanho mínimo de PCM 24kHz para gerar um frame de 20ms @ 8kHz
    # 20ms @ 24kHz = 480 samples * 2 bytes (16-bit) = 960 bytes
    MIN_PCM_24K_FRAME_SIZE = 960

    def __init__(self):
        """Inicializa o transcoder com buffers vazios."""
        # Estados dos filtros de conversão (audioop mantém contexto da onda para resample suave)
        self._state_in = None   # Estado para conversão Twilio → Azure
        self._state_out = None  # Estado para conversão Azure → Twilio
        
        # Buffers internos para garantir tamanhos de frame consistentes
        self._twilio_buffer = b""       # Buffer de saída para Twilio (μ-law)
        self._azure_accumulator = b""   # Acumulador de entrada do Azure (PCM 24k)

        logger.debug("🔄 AudioTranscoder inicializado")

    # ==========================================================================
    # TWILIO → AZURE (Entrada de áudio do usuário)
    # ==========================================================================
    def twilio_to_azure(self, base64_audio: str) -> Optional[bytes]:
        """
        Converte áudio do Twilio para formato Azure.
        
        Direção: Twilio (usuário) → Azure (modelo)
        
        Conversão:
        1. Base64 decode → bytes μ-law 8 kHz
        2. μ-law → PCM16 linear
        3. Resample 8 kHz → 24 kHz
        
        Args:
            base64_audio: Payload base64 do evento 'media' do Twilio
            
        Returns:
            Bytes PCM16 24 kHz prontos para enviar ao Azure, ou None se erro
        """
        try:
            if not base64_audio:
                return None

            # 1. Decodifica base64 → bytes μ-law 8 kHz
            mulaw_8k = base64.b64decode(base64_audio)

            # 2. Converte μ-law → PCM16 linear (8 kHz)
            pcm_8k = audioop.ulaw2lin(mulaw_8k, 2)  # 2 = 16 bits

            # 3. Resample 8 kHz → 24 kHz (fator 3x)
            pcm_24k, self._state_in = audioop.ratecv(
                pcm_8k,
                2,      # 16 bits por sample
                1,      # mono
                8000,   # sample rate origem
                24000,  # sample rate destino
                self._state_in
            )

            return pcm_24k

        except Exception as e:
            logger.error(f"❌ Erro ao converter áudio Twilio → Azure: {e}")
            return None

    # ==========================================================================
    # AZURE → TWILIO (Saída de áudio do agente)
    # ==========================================================================
    def azure_to_twilio(self, audio_data: Union[str, bytes]) -> Optional[str]:
        """
        Converte áudio do Azure para formato Twilio.
        
        Direção: Azure (modelo) → Twilio (usuário)
        
        Conversão:
        1. PCM16 24 kHz → Resample para 8 kHz
        2. PCM16 → μ-law
        3. Encode base64
        
        Implementa jitter buffer pequeno (~2-4 frames de 20ms) para
        garantir pacotes coesos e evitar áudio picotado.
        
        Args:
            audio_data: Bytes PCM16 24 kHz do Azure (ou string base64 para compatibilidade)
            
        Returns:
            String base64 com áudio μ-law 8 kHz pronto para enviar ao Twilio, ou None
        """
        try:
            # Compatibilidade: se receber string (base64), decodifica primeiro
            # Fluxo normal: SDK Azure já entrega bytes PCM16 diretamente
            if isinstance(audio_data, str):
                pcm_24k = base64.b64decode(audio_data)
            else:
                pcm_24k = audio_data

            # Acumula no buffer interno
            self._azure_accumulator += pcm_24k

            # Lista de chunks prontos para envio
            chunks: List[str] = []

            # Processa enquanto houver frames completos de 20ms
            while len(self._azure_accumulator) >= self.MIN_PCM_24K_FRAME_SIZE:
                # Extrai um frame de 20ms (960 bytes @ 24 kHz PCM16)
                frame_24k = self._azure_accumulator[:self.MIN_PCM_24K_FRAME_SIZE]
                self._azure_accumulator = self._azure_accumulator[self.MIN_PCM_24K_FRAME_SIZE:]

                # Resample 24 kHz → 8 kHz
                pcm_8k, self._state_out = audioop.ratecv(
                    frame_24k,
                    2,      # 16 bits
                    1,      # mono
                    24000,  # origem
                    8000,   # destino
                    self._state_out
                )

                # Converte PCM16 → μ-law
                mulaw_8k = audioop.lin2ulaw(pcm_8k, 2)

                # Acumula no buffer de saída para garantir tamanho mínimo
                self._twilio_buffer += mulaw_8k

                # Empacota em chunks de 20ms (160 bytes μ-law)
                while len(self._twilio_buffer) >= self.MIN_TWILIO_CHUNK_SIZE:
                    chunk = self._twilio_buffer[:self.MIN_TWILIO_CHUNK_SIZE]
                    self._twilio_buffer = self._twilio_buffer[self.MIN_TWILIO_CHUNK_SIZE:]
                    
                    # Codifica em base64 para envio ao Twilio
                    chunks.append(base64.b64encode(chunk).decode("utf-8"))

            # Retorna o último chunk gerado (mais recente)
            # Nota: Em um sistema real, você pode querer retornar todos os chunks
            if not chunks:
                return None

            return chunks[-1]

        except Exception as e:
            logger.error(f"❌ Erro ao converter áudio Azure → Twilio: {e}")
            return None

    def azure_to_twilio_all(self, audio_data: Union[str, bytes]) -> List[str]:
        """
        Versão que retorna TODOS os chunks gerados (para streaming mais granular).
        
        Útil quando você quer enviar cada chunk individualmente para menor latência.
        
        Args:
            audio_data: Bytes PCM16 24 kHz do Azure
            
        Returns:
            Lista de strings base64, cada uma com 20ms de áudio μ-law 8 kHz
        """
        try:
            if isinstance(audio_data, str):
                pcm_24k = base64.b64decode(audio_data)
            else:
                pcm_24k = audio_data

            self._azure_accumulator += pcm_24k
            chunks: List[str] = []

            while len(self._azure_accumulator) >= self.MIN_PCM_24K_FRAME_SIZE:
                frame_24k = self._azure_accumulator[:self.MIN_PCM_24K_FRAME_SIZE]
                self._azure_accumulator = self._azure_accumulator[self.MIN_PCM_24K_FRAME_SIZE:]

                pcm_8k, self._state_out = audioop.ratecv(
                    frame_24k, 2, 1, 24000, 8000, self._state_out
                )

                mulaw_8k = audioop.lin2ulaw(pcm_8k, 2)
                self._twilio_buffer += mulaw_8k

                while len(self._twilio_buffer) >= self.MIN_TWILIO_CHUNK_SIZE:
                    chunk = self._twilio_buffer[:self.MIN_TWILIO_CHUNK_SIZE]
                    self._twilio_buffer = self._twilio_buffer[self.MIN_TWILIO_CHUNK_SIZE:]
                    chunks.append(base64.b64encode(chunk).decode("utf-8"))

            return chunks

        except Exception as e:
            logger.error(f"❌ Erro ao converter áudio Azure → Twilio (all): {e}")
            return []

    # ==========================================================================
    # LIMPEZA DE BUFFERS
    # ==========================================================================
    def clear(self):
        """
        Limpa todos os buffers e estados internos.
        
        Chamado quando a Azure sinaliza interrupção/barge-in para garantir
        que nenhum áudio residual da resposta anterior seja enviado.
        """
        self._state_in = None
        self._state_out = None
        self._twilio_buffer = b""
        self._azure_accumulator = b""
        logger.debug("🔁 AudioTranscoder: buffers e estados resetados")
