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
        
        # Buffer de entrada (Twilio -> Azure)
        self._in_buffer = b"" 
        
        # Buffer de SAÍDA (Azure -> Twilio)
        # ACUMULADOR: Essencial para evitar o som de "teclado"
        self._azure_accumulator = b""
        
        # Constantes para cálculo de buffer (VoIP Standard 20ms)
        # Azure envia PCM16 24kHz (2 bytes/sample)
        # Queremos gerar 20ms de áudio 8kHz U-law (160 bytes)
        # Matemática: 
        # Output desejado: 160 bytes (u-law) -> 160 samples
        # Conversão taxa: 160 samples * (24000/8000) = 480 samples (source)
        # Bytes source: 480 samples * 2 bytes width = 960 bytes
        self.MIN_CHUNK_SIZE = 960 

    def twilio_to_azure(self, base64_payload: Union[str, bytes]) -> Optional[str]:
        """Twilio (Mu-Law 8k) -> Azure (PCM16 24k)"""
        try:
            payload_bytes = self._sanitize_base64_input(base64_payload)
            if not payload_bytes: return None

            # Decodifica Base64 -> Mu-Law
            ulaw_8k = base64.b64decode(payload_bytes)

            # Mu-Law -> Linear PCM16 (8k)
            pcm_8k = audioop.ulaw2lin(ulaw_8k, 2)

            # Upsample: 8k -> 24k
            # state_in garante que a onda não "quebre" entre pacotes
            pcm_24k, self._state_in = audioop.ratecv(pcm_8k, 2, 1, 8000, 24000, self._state_in)

            # Codifica para Base64 (Azure espera Base64 no buffer de input se for via JSON, 
            # mas via SDK geralmente aceita bytes. Mantendo base64 por compatibilidade com ingest_audio)
            return base64.b64encode(pcm_24k).decode('utf-8')

        except Exception:
            return None

    def azure_to_twilio(self, audio_data: Union[str, bytes]) -> Optional[str]:
        """
        Azure (PCM16 24k) -> Twilio (Mu-Law 8k)
        Implementa buffer para garantir pacotes de áudio coesos.
        """
        try:
            # CORREÇÃO PRINCIPAL AQUI:
            # O SDK do Azure envia 'bytes' crus (PCM). Não devemos fazer b64decode neles.
            if isinstance(audio_data, str):
                # Se por acaso vier string, tentamos decodificar (fallback)
                new_chunk = base64.b64decode(audio_data)
            else:
                # Se vier bytes, usamos diretamente
                new_chunk = audio_data

            if not new_chunk: return None
            
            # 2. ACUMULAÇÃO (A Mágica acontece aqui)
            self._azure_accumulator += new_chunk

            # Se não tivermos dados suficientes para um pacote de áudio estável (20ms),
            # retornamos None. O áudio fica guardado para o próximo ciclo.
            if len(self._azure_accumulator) < self.MIN_CHUNK_SIZE:
                return None

            # 3. Processamento em Blocos
            process_size = len(self._azure_accumulator) - (len(self._azure_accumulator) % self.MIN_CHUNK_SIZE)
            
            to_process = self._azure_accumulator[:process_size]
            self._azure_accumulator = self._azure_accumulator[process_size:] # Guarda o resto

            # 4. Downsample: 24k -> 8k
            # Input: 24k PCM16 | Output: 8k PCM16
            pcm_8k, self._state_out = audioop.ratecv(to_process, 2, 1, 24000, 8000, self._state_out)

            # 5. Converte Linear PCM16 -> Mu-Law 8-bit
            ulaw_8k = audioop.lin2ulaw(pcm_8k, 2)

            # 6. Codifica Base64 (O Twilio EXIGE Base64 no JSON)
            return base64.b64encode(ulaw_8k).decode('utf-8')

        except Exception as e:
            logger.error(f"Erro Transcoder OUT: {e}")
            # Em caso de erro, limpamos o buffer para evitar travar em dados corrompidos
            self._azure_accumulator = b"" 
            return None

    def _sanitize_base64_input(self, data: Union[str, bytes]) -> Optional[bytes]:
        """Limpa string Base64 e valida padding"""
        try:
            if isinstance(data, str):
                data = data.encode('ascii', 'ignore')
            
            data = data.strip()
            
            # Se for bytes puro que não parece base64, retorna ele mesmo (segurança)
            if len(data) % 4 == 1:
                return None
                
            missing_padding = len(data) % 4
            if missing_padding:
                data += b'=' * (4 - missing_padding)
                
            return data
        except Exception:
            return None