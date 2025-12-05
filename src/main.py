"""
Azure VoiceLive Agent - Entry Point

Aplicação principal para agentes de voz com Azure OpenAI Realtime API.
"""

import sys
import uvicorn
from pydantic import ValidationError

from src.core.config import get_settings
from src.core.logging import setup_logging

class StderrFilter:
    """Filtra mensagens indesejadas do canal de erro padrão (stderr)"""
    def __init__(self, original_stderr):
        self.original_stderr = original_stderr

    def write(self, message):
        # Se a mensagem contiver o aviso chato do NNPACK, ignora
        if "NNPACK" in message or "Unsupported hardware" in message:
            return
        # Caso contrário, escreve normalmente
        self.original_stderr.write(message)

    def flush(self):
        self.original_stderr.flush()

# Aplica o filtro imediatamente
sys.stderr = StderrFilter(sys.stderr)

# ==============================================================================
# SETUP INICIAL
# ==============================================================================
try:
    settings = get_settings()
except ValidationError as e:
    print(f"❌ Erro de Configuração (.env): {e}")
    sys.exit(1)

logger = setup_logging(settings)

# Import app após logging estar configurado
from src.api.routes import app


# ==============================================================================
# ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    # Configurações de execução baseadas no settings.py
    
    # Em Dev, o reload é útil. Em Prod, o gerenciador de processos (ex: Gunicorn/Systemd) cuida disso
    use_reload = settings.is_development()
    
    logger.info(f"🚀 Iniciando servidor na porta {settings.PORT}")
    
    uvicorn.run(
        "src.main:app", 
        host="0.0.0.0", 
        port=settings.PORT, 
        reload=use_reload,
        log_level=settings.get_log_level().lower()
    )
