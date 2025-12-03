"""
Configuration Package

Gerenciamento de configurações:
- Settings de ambiente (.env)
- Configurações do agente (agent_config.json)
"""

from .settings import get_settings, Settings
from .agent_config_loader import AgentConfig

__all__ = ["get_settings", "Settings", "AgentConfig"]
