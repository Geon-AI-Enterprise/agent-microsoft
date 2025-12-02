"""
Módulo para carregar e gerenciar configurações do agente de voz
"""
import json
from pathlib import Path


class AgentConfig:
    """Classe para gerenciar configurações do agente de forma simples"""
    
    def __init__(self, config_path: str = "agent_config.json"):
        """
        Inicializa a configuração do agente
        
        Args:
            config_path: Caminho para o arquivo de configuração JSON
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
    
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
