import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator, Field
from functools import lru_cache

class Settings(BaseSettings):
    # Metadados do App
    APP_ENV: str = "development"
    PORT: int = 8000
    
    # Credenciais Azure (Obrigatórias)
    AZURE_OPENAI_ENDPOINT: str
    AZURE_OPENAI_API_KEY: str
    
    # VoiceLive Configs
    AZURE_VOICELIVE_ENDPOINT: str
    AZURE_VOICELIVE_API_KEY: str
    AZURE_VOICELIVE_MODEL: str = "gpt-realtime"
    AZURE_VOICELIVE_VOICE: str = "en-US-Andrew:DragonHDLatestNeural"
    
    # Instruções (Opcional no .env, fallback para JSON)
    AZURE_VOICELIVE_INSTRUCTIONS: Optional[str] = Field(None, env="AZURE_VOICELIVE_INSTRUCTIONS")
    
    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # --- Configurações de VAD (Agora opcionais = None se não estiver no .env) ---
    VAD_THRESHOLD: Optional[float] = Field(None, env="VAD_THRESHOLD")
    VAD_PREFIX_PADDING_MS: Optional[int] = Field(None, env="VAD_PREFIX_PADDING_MS")
    VAD_SILENCE_DURATION_MS: Optional[int] = Field(None, env="VAD_SILENCE_DURATION_MS")
    VAD_DEBOUNCE_MS: Optional[int] = Field(None, env="VAD_DEBOUNCE_MS")
    
    # --- Configurações de Saudação ---
    GREETING_DELAY_SECONDS: Optional[float] = Field(None, env="GREETING_DELAY_SECONDS")
    GREETING_GRACE_PERIOD_SECONDS: Optional[float] = Field(None, env="GREETING_GRACE_PERIOD_SECONDS")
    
    # --- Configurações de Modelo ---
    MODEL_TEMPERATURE: Optional[float] = Field(None, env="MODEL_TEMPERATURE")
    MAX_RESPONSE_OUTPUT_TOKENS: Optional[int] = Field(None, env="MAX_RESPONSE_OUTPUT_TOKENS")

    @field_validator('APP_ENV')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        valid_envs = ['development', 'staging', 'production']
        if v not in valid_envs:
            raise ValueError(f'APP_ENV deve ser um de: {", ".join(valid_envs)}')
        return v
    
    def is_development(self) -> bool: return self.APP_ENV == "development"
    def is_staging(self) -> bool: return self.APP_ENV == "staging"
    def is_production(self) -> bool: return self.APP_ENV == "production"
    
    def get_log_level(self) -> str:
        if self.is_development(): return "DEBUG"
        return "INFO"

    class Config:
        env_file = ".env"
        extra = "ignore"

@lru_cache()
def get_settings():
    return Settings()