"""
Services Package

Lógica de negócio e serviços:
- Voice Assistant Worker
- Audio Processor
- Client Manager (Multi-tenant)
"""

from .voice_assistant import VoiceAssistantWorker
from .client_manager import ClientManager

__all__ = ["VoiceAssistantWorker", "ClientManager"]
