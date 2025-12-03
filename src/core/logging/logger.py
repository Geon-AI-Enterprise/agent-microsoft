"""
Módulo de configuração de logging amigável
Fornece formatação limpa, cores e filtros para logs
"""

import logging
import sys
from typing import Optional


class Colors:
    """Cores ANSI para terminal"""
    # Cores principais
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    
    # Estilos
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    
    # Reset
    RESET = '\033[0m'
    
    @staticmethod
    def strip_colors(text: str) -> str:
        """Remove códigos de cor de uma string"""
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)


class CustomFormatter(logging.Formatter):
    """
    Formatter customizado para logs amigáveis
    - Development: Colorido com emojis
    - Staging: Moderado sem cores
    - Production: Mínimo sem cores
    """
    
    # Emojis por nível de log
    EMOJI_MAP = {
        'DEBUG': '🔍',
        'INFO': 'ℹ️ ',
        'WARNING': '⚠️ ',
        'ERROR': '❌',
        'CRITICAL': '🚨'
    }
    
    # Cores por nível de log
    COLOR_MAP = {
        'DEBUG': Colors.CYAN,
        'INFO': Colors.BLUE,
        'WARNING': Colors.YELLOW,
        'ERROR': Colors.RED,
        'CRITICAL': Colors.RED + Colors.BOLD
    }
    
    def __init__(self, use_colors: bool = True, use_emoji: bool = True, detailed: bool = True):
        """
        Args:
            use_colors: Se deve usar cores ANSI
            use_emoji: Se deve usar emojis
            detailed: Se deve incluir timestamp e nome do logger
        """
        self.use_colors = use_colors
        self.use_emoji = use_emoji
        self.detailed = detailed
        
        if detailed:
            # Development: formato completo
            fmt = '%(emoji)s%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
        else:
            # Production: formato mínimo
            fmt = '[%(asctime)s] %(message)s'
        
        super().__init__(fmt, datefmt='%Y-%m-%d %H:%M:%S')
    
    def format(self, record: logging.LogRecord) -> str:
        """Formata o log record com cores e emojis"""
        # Adiciona emoji
        if self.use_emoji and self.detailed:
            record.emoji = self.EMOJI_MAP.get(record.levelname, '  ')
        else:
            record.emoji = ''
        
        # Formata a mensagem base
        formatted = super().format(record)
        
        # Adiciona cores se habilitado
        if self.use_colors and self.detailed:
            color = self.COLOR_MAP.get(record.levelname, '')
            formatted = f"{color}{formatted}{Colors.RESET}"
        
        return formatted


class AzureLogFilter(logging.Filter):
    """
    Filtro para reduzir verbosidade de logs do Azure SDK
    Em staging/production, permite apenas WARNING+
    Em development, permite tudo
    """
    
    def __init__(self, environment: str):
        super().__init__()
        self.environment = environment
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Filtra logs do Azure baseado no ambiente"""
        # Se não é log do Azure, permite
        if not record.name.startswith('azure'):
            return True
        
        # Development: permite todos os logs do Azure
        if self.environment == 'development':
            return True
        
        # Staging/Production: apenas WARNING e acima
        return record.levelno >= logging.WARNING


def setup_logging(settings) -> logging.Logger:
    """
    Configura o sistema de logging baseado no ambiente
    
    Args:
        settings: Objeto Settings com configurações do app
        
    Returns:
        Logger configurado para a aplicação
    """
    env = settings.APP_ENV
    is_dev = settings.is_development()
    is_staging = settings.is_staging()
    
    # Remove handlers existentes
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Configura nível base
    log_level = getattr(logging, settings.get_log_level())
    root_logger.setLevel(log_level)
    
    # Cria handler para console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Configura formatter baseado no ambiente
    if is_dev:
        # Development: colorido, com emoji, detalhado
        formatter = CustomFormatter(use_colors=True, use_emoji=True, detailed=True)
    elif is_staging:
        # Staging: sem cores, com emoji, detalhado
        formatter = CustomFormatter(use_colors=False, use_emoji=True, detailed=True)
    else:
        # Production: sem cores, sem emoji, mínimo
        formatter = CustomFormatter(use_colors=False, use_emoji=False, detailed=False)
    
    console_handler.setFormatter(formatter)
    
    # Adiciona filtro do Azure
    azure_filter = AzureLogFilter(env)
    console_handler.addFilter(azure_filter)
    
    root_logger.addHandler(console_handler)
    
    # Configura níveis de bibliotecas terceiras
    configure_third_party_loggers(env)
    
    # Retorna logger da aplicação
    app_logger = logging.getLogger(__name__)
    return app_logger


def configure_third_party_loggers(environment: str):
    """
    Configura níveis de log para bibliotecas terceiras
    Reduz verbosidade em staging/production
    """
    is_dev = environment == 'development'
    
    # Azure SDK - muito verbose em DEBUG
    logging.getLogger('azure').setLevel(logging.WARNING)
    logging.getLogger('azure.core').setLevel(logging.WARNING)
    
    if is_dev:
        # Em development, permite INFO do VoiceLive para debug
        logging.getLogger('azure.ai.voicelive').setLevel(logging.INFO)
    else:
        # Em staging/production, apenas WARNING+
        logging.getLogger('azure.ai.voicelive').setLevel(logging.WARNING)
    
    # Uvicorn - logs de acesso muito verbosos
    if is_dev:
        logging.getLogger('uvicorn').setLevel(logging.INFO)
        logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    else:
        logging.getLogger('uvicorn').setLevel(logging.WARNING)
        logging.getLogger('uvicorn.access').setLevel(logging.ERROR)
    
    # FastAPI
    if not is_dev:
        logging.getLogger('fastapi').setLevel(logging.WARNING)


def get_user_friendly_error(exception: Exception, environment: str) -> str:
    """
    Converte exceções técnicas em mensagens amigáveis
    
    Args:
        exception: A exceção capturada
        environment: Ambiente atual (development, staging, production)
        
    Returns:
        Mensagem de erro amigável
    """
    error_type = type(exception).__name__
    error_msg = str(exception)
    
    # Mapeamento de erros comuns
    friendly_messages = {
        'ConnectionError': '❌ Não foi possível conectar ao servidor Azure\n💡 Verifique sua conexão de internet',
        'TimeoutError': '❌ Tempo esgotado ao conectar com Azure\n💡 Tente novamente em alguns instantes',
        'AuthenticationError': '❌ Falha na autenticação com Azure\n💡 Verifique AZURE_VOICELIVE_API_KEY no arquivo .env',
        'KeyError': '❌ Configuração faltando\n💡 Verifique se todas as variáveis necessárias estão no .env',
        'FileNotFoundError': f'❌ Arquivo não encontrado\n💡 Verifique se o arquivo existe: {error_msg}',
    }
    
    # Tenta encontrar mensagem amigável
    for error_name, friendly_msg in friendly_messages.items():
        if error_name in error_type or error_name.lower() in error_msg.lower():
            return friendly_msg
    
    # Mensagem genérica
    if environment == 'development':
        return f'❌ Erro: {error_type}\n🔍 Detalhes: {error_msg}'
    else:
        return f'❌ Erro inesperado\n💡 Consulte os logs para mais detalhes'


if __name__ == '__main__':
    # Teste do módulo
    print("Testando formatadores de log...\n")
    
    # Simula settings
    class MockSettings:
        APP_ENV = 'development'
        def is_development(self): return True
        def is_staging(self): return False
        def is_production(self): return False
        def get_log_level(self): return 'DEBUG'
    
    settings = MockSettings()
    logger = setup_logging(settings)
    
    # Testa diferentes níveis
    logger.debug("Mensagem de DEBUG")
    logger.info("Mensagem de INFO")
    logger.warning("Mensagem de WARNING")
    logger.error("Mensagem de ERROR")
    
    print("\n" + "="*60)
    print("Teste concluído!")
