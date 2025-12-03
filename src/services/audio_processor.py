"""
Audio Processor Service

Gerencia captura e reprodução de áudio local (apenas Development).
"""

import asyncio
import base64
import logging
import queue
from typing import Optional

from azure.ai.voicelive.aio import VoiceLiveConnection

# Audio Library (Conditional Import)
try:
    import pyaudio
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

logger = logging.getLogger(__name__)


class AudioProcessor:
    """Gerencia captura e reprodução de áudio local (apenas Development)"""
    
    class AudioPlaybackPacket:
        def __init__(self, seq_num: int, data: Optional[bytes]):
            self.seq_num = seq_num
            self.data = data

    def __init__(self, connection: VoiceLiveConnection):
        if not AUDIO_AVAILABLE:
            raise RuntimeError("PyAudio não está instalado.")
            
        self.connection = connection
        self.audio = pyaudio.PyAudio()
        
        # Configurações de Áudio (Conforme documentação)
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 24000
        self.chunk_size = 960  # 40ms para baixa latência

        self.input_stream = None
        self.output_stream = None
        
        self.playback_queue: queue.Queue = queue.Queue()
        self.playback_base = 0
        self.next_seq_num = 0
        self.is_agent_speaking = False
        self.loop = asyncio.get_running_loop()

    def start_capture(self):
        """Inicia captura do microfone"""
        def _callback(in_data, frame_count, time_info, status):
            if self.connection:
                audio_base64 = base64.b64encode(in_data).decode("utf-8")
                asyncio.run_coroutine_threadsafe(
                    self.connection.input_audio_buffer.append(audio=audio_base64),
                    self.loop
                )
            return (None, pyaudio.paContinue)

        self.input_stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=_callback,
        )
        logger.debug("🎤 Captura de áudio iniciada")

    def start_playback(self):
        """Inicia reprodução de áudio"""
        remaining = bytes()

        def _callback(in_data, frame_count, time_info, status):
            nonlocal remaining
            # Lógica simplificada de playback buffer
            bytes_needed = frame_count * 2  # 16-bit = 2 bytes
            out_data = bytearray(bytes_needed)
            
            # (Implementação simplificada para brevidade - foco na estrutura)
            try:
                while len(remaining) < bytes_needed:
                    packet = self.playback_queue.get_nowait()
                    if packet.data and packet.seq_num >= self.playback_base:
                        remaining += packet.data
            except queue.Empty:
                pass
            
            valid_len = min(len(remaining), bytes_needed)
            out_data[:valid_len] = remaining[:valid_len]
            remaining = remaining[valid_len:]
            
            return (bytes(out_data), pyaudio.paContinue)

        self.output_stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            output=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=_callback,
        )
        logger.debug("🔊 Reprodução de áudio iniciada")

    def queue_audio(self, data: bytes):
        packet = self.AudioPlaybackPacket(self.next_seq_num, data)
        self.next_seq_num += 1
        self.playback_queue.put(packet)

    def skip_pending_audio(self):
        """Limpa áudio pendente (Correção de Barge-in)"""
        with self.playback_queue.mutex:
            self.playback_queue.queue.clear()
        self.playback_base = self.next_seq_num
        self.is_agent_speaking = False

    def shutdown(self):
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
        if self.audio:
            self.audio.terminate()
        logger.debug("🛑 AudioProcessor encerrado")
