"""
Audio Transcoder Service

Responsável por converter áudio entre os formatos:
- Twilio: G.711 Mu-Law @ 8kHz
- Azure: PCM16 Linear @ 24kHz

Implementa sanitização de Base64 e manutenção de estado dos filtros de reamostragem.
"""

import audioop
import base64
import logging
from typing import Optional, Union

logger = logging.getLogger(__name__)

class AudioTranscoder:
    def __init__(self):
        # Mantém o estado dos filtros de conversão (ratecv) entre os chunks
        # Isso evita "cliques" no áudio nas emendas dos pacotes
        self._state_in = None   # Direção: Twilio -> Azure
        self._state_out = None  # Direção: Azure -> Twilio

    def twilio_to_azure(self, base64_payload: Union[str, bytes]) -> Optional[str]:
        """
        Converte áudio do Twilio (Mu-Law 8kHz) para Azure (PCM16 24kHz).
        Retorna string Base64 pronta para o Azure.
        """
        try:
            # 1. Sanitiza entrada (garante bytes válidos e padding)
            payload_bytes = self._sanitize_base64_input(base64_payload)
            if not payload_bytes:
                return None

            # 2. Decodifica Base64 -> Raw Mu-Law
            ulaw_8k = base64.b64decode(payload_bytes)

            # 3. Converte Mu-Law -> PCM16 Linear
            pcm_8k = audioop.ulaw2lin(ulaw_8k, 2)

            # 4. Upsampling (8.000Hz -> 24.000Hz)
            # ratecv(fragment, width, nchannels, inrate, outrate, state)
            pcm_24k, self._state_in = audioop.ratecv(pcm_8k, 2, 1, 8000, 24000, self._state_in)

            # 5. Codifica PCM16 -> String Base64 (Requisito do Azure)
            return base64.b64encode(pcm_24k).decode('utf-8')

        except Exception:
            # Falhas silenciosas na entrada são preferíveis a desconectar
            return None

    def azure_to_twilio(self, base64_payload: Union[str, bytes]) -> Optional[str]:
        """
        Converte áudio do Azure (PCM16 24kHz) para Twilio (Mu-Law 8kHz).
        Retorna string Base64 pronta para o Twilio.
        """
        try:
            # 1. Sanitiza entrada (Corrige erro "ASCII only" e Padding)
            payload_bytes = self._sanitize_base64_input(base64_payload)
            if not payload_bytes:
                return None

            # 2. Decodifica Base64 -> Raw PCM16 24k
            pcm_24k = base64.b64decode(payload_bytes)

            # 3. Correção de Alinhamento (Evita erro "not a whole number of frames")
            # PCM16 usa 2 bytes por amostra. Tamanho ímpar quebra o audioop.
            if len(pcm_24k) % 2 != 0:
                pcm_24k = pcm_24k[:-1]
            
            if not pcm_24k:
                return None

            # 4. Downsampling (24.000Hz -> 8.000Hz)
            pcm_8k, self._state_out = audioop.ratecv(pcm_24k, 2, 1, 24000, 8000, self._state_out)

            # 5. Converte PCM16 Linear -> Mu-Law
            ulaw_8k = audioop.lin2ulaw(pcm_8k, 2)

            # 6. Codifica Mu-Law -> String Base64 (Requisito do Twilio)
            return base64.b64encode(ulaw_8k).decode('utf-8')

        except Exception as e:
            logger.error(f"Erro Transcoder OUT: {e}")
            return None

    def _sanitize_base64_input(self, data: Union[str, bytes]) -> Optional[bytes]:
        """
        Limpa a string Base64 para evitar erros comuns de decodificação.
        - Remove caracteres não-ASCII
        - Corrige Padding (=)
        - Valida tamanho matemático
        """
        try:
            # Se for string, força conversão para bytes ASCII, ignorando lixo UTF-8
            if isinstance(data, str):
                data = data.encode('ascii', 'ignore')
            
            data = data.strip()
            
            # Validação rápida de integridade Base64 (tamanho % 4 != 1)
            if len(data) % 4 == 1:
                return None
                
            # Adiciona Padding faltante se necessário
            missing_padding = len(data) % 4
            if missing_padding:
                data += b'=' * (4 - missing_padding)
                
            return data
        except Exception:
            return None