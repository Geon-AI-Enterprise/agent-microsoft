import os
from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache

class Settings(BaseSettings):
    # Metadados do App
    APP_ENV: str = "development"  # development, staging, production
    PORT: int = 8000
    
    # Credenciais Azure (Obrigatórias)
    AZURE_OPENAI_ENDPOINT: str
    AZURE_OPENAI_API_KEY: str
    AZURE_OPENAI_REALTIME_MODEL: str = "gpt-4o-realtime-preview"
    
    # VoiceLive Configs
    AZURE_VOICELIVE_ENDPOINT: str
    AZURE_VOICELIVE_API_KEY: str
    AZURE_VOICELIVE_MODEL: str = "gpt-realtime"
    AZURE_VOICELIVE_VOICE: str = "en-US-Andrew:DragonHDLatestNeural"
    
    # Instruções podem ser opcionais ou ter default
    AZURE_VOICELIVE_INSTRUCTIONS: str = "Você é um assistente útil."
    
    # Supabase (Multi-tenant)
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # --- Configurações de VAD (Detecção de Atividade de Voz) ---
    VAD_THRESHOLD: float = Field(0.5, env="VAD_THRESHOLD")
    VAD_PREFIX_PADDING_MS: int = Field(300, env="VAD_PREFIX_PADDING_MS")
    VAD_SILENCE_DURATION_MS: int = Field(500, env="VAD_SILENCE_DURATION_MS")
    
    # --- Configurações de Modelo (LLM) ---
    MODEL_TEMPERATURE: float = Field(0.6, env="MODEL_TEMPERATURE")
    # Nota: No código Python, o parâmetro é 'max_response_output_tokens'
    MAX_RESPONSE_OUTPUT_TOKENS: int = Field(400, env="MAX_RESPONSE_OUTPUT_TOKENS")

    @field_validator('APP_ENV')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Valida que APP_ENV é um dos valores aceitos"""
        valid_envs = ['development', 'staging', 'production']
        if v not in valid_envs:
            raise ValueError(f'APP_ENV deve ser um de: {", ".join(valid_envs)}')
        return v
    
    def is_development(self) -> bool:
        """Retorna True se estiver em ambiente de desenvolvimento"""
        return self.APP_ENV == "development"
    
    def is_staging(self) -> bool:
        """Retorna True se estiver em ambiente de staging"""
        return self.APP_ENV == "staging"
    
    def is_production(self) -> bool:
        """Retorna True se estiver em ambiente de produção"""
        return self.APP_ENV == "production"
    
    def get_log_level(self) -> str:
        """Retorna o nível de log apropriado para o ambiente"""
        if self.is_development():
            return "DEBUG"
        elif self.is_staging():
            return "INFO"
        else:  # production
            return "INFO"

    class Config:
        # Em produção, o arquivo .env será ignorado se não existir, 
        # e o Pydantic lerá das variáveis de ambiente do SO.
        env_file = ".env"
        extra = "ignore"

@lru_cache()
def get_settings():
    return Settings()