"""
Audio Transcoder Service - Versão com Buffer de Alinhamento
Corrige: Som de "teclado/cliques" causado por desalinhamento de bytes PCM.
"""

import audioop
import base64
import logging
from typing import Optional, Union

logger = logging.getLogger(__name__)

class AudioTranscoder:
    def __init__(self):
        # Estados dos filtros de conversão
        self._state_in = None
        self._state_out = None
        
        # --- NOVO: Buffers de Alinhamento ---
        # Guardam bytes "sozinhos" de um pacote para juntar com o próximo
        self._in_buffer = b""   # Twilio -> Azure
        self._out_buffer = b""  # Azure -> Twilio

    def twilio_to_azure(self, base64_payload: Union[str, bytes]) -> Optional[str]:
        """Twilio (Mu-Law 8k) -> Azure (PCM16 24k)"""
        try:
            payload_bytes = self._sanitize_base64_input(base64_payload)
            if not payload_bytes: return None

            # Decodifica Base64 -> Mu-Law
            ulaw_8k = base64.b64decode(payload_bytes)

            # Mu-Law é 1 byte por amostra, então não sofre de desalinhamento de frames.
            # Mas convertemos para Linear (PCM16) para fazer o upsample.
            pcm_8k = audioop.ulaw2lin(ulaw_8k, 2)

            # Upsample: 8k -> 24k
            pcm_24k, self._state_in = audioop.ratecv(pcm_8k, 2, 1, 8000, 24000, self._state_in)

            # Codifica para Base64
            return base64.b64encode(pcm_24k).decode('utf-8')

        except Exception:
            return None

    def azure_to_twilio(self, base64_payload: Union[str, bytes]) -> Optional[str]:
        """Azure (PCM16 24k) -> Twilio (Mu-Law 8k)"""
        try:
            # 1. Sanitiza
            payload_bytes = self._sanitize_base64_input(base64_payload)
            if not payload_bytes: return None

            # 2. Decodifica Base64 -> Raw PCM16 24k
            chunk = base64.b64decode(payload_bytes)

            # 3. --- LÓGICA DE ALINHAMENTO DE BYTES (CORREÇÃO DO CHIADO) ---
            # Recupera o que sobrou do último pacote e junta com o atual
            chunk = self._out_buffer + chunk
            
            # PCM16 exige pares de bytes. Se o total for ímpar, sobra 1 byte.
            if len(chunk) % 2 != 0:
                # Guarda o último byte para o próximo round
                self._out_buffer = chunk[-1:]
                chunk = chunk[:-1] # Processa apenas os pares
            else:
                # Tudo alinhado, limpa o buffer
                self._out_buffer = b""

            # Se depois de alinhar não sobrou nada para processar, retorna
            if not chunk:
                return None
            # -----------------------------------------------------------

            # 4. Downsample: 24k -> 8k
            # state mantém a continuidade da onda sonora
            pcm_8k, self._state_out = audioop.ratecv(chunk, 2, 1, 24000, 8000, self._state_out)

            # 5. Converte Linear -> Mu-Law
            ulaw_8k = audioop.lin2ulaw(pcm_8k, 2)

            # 6. Codifica Base64
            return base64.b64encode(ulaw_8k).decode('utf-8')

        except Exception as e:
            logger.error(f"Erro Transcoder OUT: {e}")
            return None

    def _sanitize_base64_input(self, data: Union[str, bytes]) -> Optional[bytes]:
        """Limpa string Base64"""
        try:
            if isinstance(data, str):
                data = data.encode('ascii', 'ignore')
            
            data = data.strip()
            
            # Validação matemática Base64
            if len(data) % 4 == 1:
                return None
                
            missing_padding = len(data) % 4
            if missing_padding:
                data += b'=' * (4 - missing_padding)
                
            return data
        except Exception:
            return None