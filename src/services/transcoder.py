"""
Audio Transcoder Service - Com Jitter Buffer para Twilio
Correção: Remove decodificação Base64 redundante na saída do Azure (SDK já entrega bytes).
"""

import audioop
import base64
import logging
from typing import Optional, Union

logger = logging.getLogger(__name__)

class AudioTranscoder:
    def __init__(self):
        # Estados dos filtros de conversão (audioop mantém o contexto da onda)
        self._state_in = None
        self._state_out = None
        
        # Buffer interno para garantir tamanhos de frame consistentes (20ms @ 8kHz = 160 bytes)
        self._twilio_buffer = b""
        self._azure_accumulator = b""

        # Tamanho mínimo de chunk para a Twilio (20ms de áudio Mu-Law @ 8kHz)
        self.MIN_CHUNK_SIZE = 160  

    # ------------------------------------------------------------------
    # TWILIO (Mu-Law 8kHz) -> AZURE (PCM16 24kHz)
    # ------------------------------------------------------------------
    def twilio_to_azure(self, base64_audio: str) -> Optional[bytes]:
        """
        Twilio (Mu-Law 8kHz) -> Azure (PCM16 24kHz)
        - Decodifica Base64
        - Converte de Mu-Law para PCM16
        - Faz resample de 8kHz -> 24kHz
        """
        try:
            if not base64_audio:
                return None

            mulaw_8k = base64.b64decode(base64_audio)

            # Converte de Mu-Law para PCM16 8kHz
            pcm_8k, self._state_in = audioop.ulaw2lin(mulaw_8k, 2), self._state_in

            # Resample 8kHz -> 24kHz (fator 3x)
            pcm_24k, self._state_out = audioop.ratecv(
                pcm_8k, 
                2,  # 16 bits
                1,  # mono
                8000, 
                24000,
                self._state_out
            )

            return pcm_24k

        except Exception as e:
            logger.error(f"Erro ao converter áudio Twilio -> Azure: {e}")
            return None

    # ------------------------------------------------------------------
    # AZURE (PCM16 24kHz) -> TWILIO (Mu-Law 8kHz) + Jitter Buffer
    # ------------------------------------------------------------------
    def azure_to_twilio(self, audio_data: Union[str, bytes]) -> Optional[str]:
        """
        Azure (PCM16 24k) -> Twilio (Mu-Law 8k)
        Implementa buffer para garantir pacotes de áudio coesos.
        """
        try:
            # CORREÇÃO PRINCIPAL AQUI:
            # - Se o SDK do Azure já nos entrega bytes (PCM16 24k), não devemos 
            #   decodificar Base64 novamente. Apenas quando recebermos string.
            if isinstance(audio_data, str):
                # Mantido por compatibilidade, caso algum fluxo ainda envie Base64
                pcm_24k = base64.b64decode(audio_data)
            else:
                # Fluxo normal: já é bytes PCM16 24k
                pcm_24k = audio_data

            # Acumula no buffer interno
            self._azure_accumulator += pcm_24k

            # Lista de chunks prontos para envio
            chunks = []

            # Precisamos de pelo menos 20ms de áudio em 8kHz para enviar ao Twilio
            # 20ms @ 8kHz = 160 samples mono = 160 bytes em Mu-Law
            # Em 24kHz PCM16, isso equivale a 480 samples * 2 bytes = 960 bytes
            MIN_PCM_24K_BYTES = 960

            while len(self._azure_accumulator) >= MIN_PCM_24K_BYTES:
                # Separa um frame de 20ms em 24kHz
                frame_24k = self._azure_accumulator[:MIN_PCM_24K_BYTES]
                self._azure_accumulator = self._azure_accumulator[MIN_PCM_24K_BYTES:]

                # Converte 24kHz -> 8kHz
                pcm_8k, self._state_out = audioop.ratecv(
                    frame_24k,
                    2,  # 16 bits
                    1,  # mono
                    24000,
                    8000,
                    self._state_out
                )

                # Converte PCM16 -> Mu-Law
                mulaw_8k = audioop.lin2ulaw(pcm_8k, 2)

                # Acumula no buffer de saída para garantir tamanho mínimo
                self._twilio_buffer += mulaw_8k

                # Enquanto houver pelo menos 20ms de áudio, cortamos e empacotamos
                while len(self._twilio_buffer) >= self.MIN_CHUNK_SIZE:
                    chunk = self._twilio_buffer[:self.MIN_CHUNK_SIZE]
                    self._twilio_buffer = self._twilio_buffer[self.MIN_CHUNK_SIZE:]

                    # Codifica em Base64 para envio ao Twilio
                    chunks.append(base64.b64encode(chunk).decode("utf-8"))

            # Se nenhum chunk completo foi gerado, não envia nada
            if not chunks:
                return None

            # Retornamos o maior chunk gerado (ou você pode escolher concatenar, 
            # dependendo da granularidade desejada).
            return chunks[-1]

        except Exception as e:
            logger.error(f"Erro ao converter áudio Azure -> Twilio: {e}")
            return None

    # ------------------------------------------------------------------
    # Funções de limpeza (para barge-in / interrupções)
    # ------------------------------------------------------------------
    def clear(self):
        """
        Limpa todos os buffers e estados internos (usado em interrupções).
        """
        self._state_in = None
        self._state_out = None
        self._twilio_buffer = b""
        self._azure_accumulator = b""
        logger.debug("🔁 AudioTranscoder: estados e buffers resetados")
