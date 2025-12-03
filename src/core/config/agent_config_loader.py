"""
Módulo para carregar e gerenciar configurações do agente de voz
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class AgentConfig:
    """Classe para gerenciar configurações do agente de forma simples"""
    
    def __init__(self, config_path: str = "agent_config.json", env: str = "development"):
        """
        Inicializa a configuração do agente
        
        Args:
            config_path: Caminho para o arquivo de configuração JSON padrão
            env: Ambiente atual (development, staging, production)
        """
        self.env = env
        self.default_config_path = Path(config_path)
        self.config_path = self._resolve_config_path(config_path, env)
        self.config = self._load_config()
    
    @classmethod
    def from_dict(cls, config_dict: dict, env: str = "production"):
        """
        Cria uma instância de AgentConfig a partir de um dicionário
        
        Args:
            config_dict: Dicionário com as configurações
            env: Ambiente (padrão: production)
            
        Returns:
            Instância de AgentConfig
        """
        instance = cls.__new__(cls)
        instance.env = env
        instance.default_config_path = None
        instance.config_path = None
        instance.config = config_dict
        return instance
    
    def _resolve_config_path(self, default_path: str, env: str) -> Path:
        """
        Resolve o caminho do arquivo de configuração baseado no ambiente
        
        Args:
            default_path: Caminho padrão do config
            env: Ambiente (development, staging, production)
            
        Returns:
            Path para o arquivo de configuração apropriado
        """
        # Para development, usa o arquivo padrão
        if env == "development":
            return Path(default_path)
        
        # Para staging e production, tenta usar arquivo específico
        base_path = Path(default_path)
        env_config_path = base_path.parent / f"{base_path.stem}.{env}{base_path.suffix}"
        
        # Se o arquivo específico existir, usa ele
        if env_config_path.exists():
            logger.info(f"📋 Usando configuração específica: {env_config_path}")
            return env_config_path
        
        # Caso contrário, usa o padrão e avisa
        logger.warning(
            f"⚠️ Arquivo {env_config_path} não encontrado. "
            f"Usando configuração padrão: {base_path}"
        )
        return Path(default_path)
    
    def _load_config(self) -> dict:
        """Carrega o arquivo de configuração JSON"""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Arquivo de configuração não encontrado: {self.config_path}"
            )
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def reload(self):
        """Recarrega as configurações do arquivo"""
        self.config = self._load_config()
    
    @property
    def voice(self) -> str:
        """Modelo de voz do agente"""
        return self.config.get('voice', 'en-US-Andrew:DragonHDLatestNeural')
    
    @property
    def temperature(self) -> float:
        """Temperatura do modelo (0.0 - 1.0)"""
        return self.config.get('temperature', 0.7)
    
    @property
    def max_tokens(self) -> int:
        """Número máximo de tokens na resposta"""
        return self.config.get('max_tokens', 800)
    
    @property
    def instructions(self) -> str:
        """Instruções/prompt completo do agente"""
        return self.config.get('instructions', '')
    
    def update_voice(self, voice: str):
        """
        Atualiza o modelo de voz e salva
        
        Args:
            voice: Novo modelo de voz (ex: 'en-US-Andrew:DragonHDLatestNeural')
        """
        self.config['voice'] = voice
        self._save_config()
    
    def update_temperature(self, temperature: float):
        """
        Atualiza a temperatura e salva
        
        Args:
            temperature: Nova temperatura (0.0 - 1.0)
        """
        self.config['temperature'] = temperature
        self._save_config()
    
    def update_max_tokens(self, max_tokens: int):
        """
        Atualiza o max_tokens e salva
        
        Args:
            max_tokens: Novo valor de max_tokens
        """
        self.config['max_tokens'] = max_tokens
        self._save_config()
    
    def update_instructions(self, instructions: str):
        """
        Atualiza as instruções/prompt e salva
        
        Args:
            instructions: Novo texto de instruções
        """
        self.config['instructions'] = instructions
        self._save_config()
    
    def _save_config(self):
        """Salva as configurações atualizadas no arquivo JSON"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
        print(f"✅ Configurações salvas em {self.config_path}")


# Exemplo de uso
if __name__ == "__main__":
    # Carregar configuração
    config = AgentConfig("agent_config.json")
    
    print("=" * 60)
    print("📝 CONFIGURAÇÕES DO AGENTE")
    print("=" * 60)
    print(f"Voz: {config.voice}")
    print(f"Temperature: {config.temperature}")
    print(f"Max Tokens: {config.max_tokens}")
    print(f"\nInstruções (primeiros 200 caracteres):")
    print(config.instructions[:200] + "...")
    print("=" * 60)
