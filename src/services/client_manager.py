"""
Gerenciador de clientes multi-tenant com Supabase

Este módulo gerencia múltiplos clientes, carregando suas configurações
do Supabase baseado no número SIP da chamada.
"""
import logging
import time
from typing import Optional, Dict, Any
from supabase import create_client, Client
from src.core.config import AgentConfig

logger = logging.getLogger(__name__)


class ClientManager:
    """Gerencia configurações de múltiplos clientes usando Supabase"""
    
    def __init__(self, supabase_url: str, supabase_key: str, cache_ttl: int = 300):
        """
        Inicializa o gerenciador de clientes
        
        Args:
            supabase_url: URL do projeto Supabase
            supabase_key: Chave de API do Supabase (service role)
            cache_ttl: Tempo de vida do cache em segundos (padrão: 5 minutos)
        """
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.cache: Dict[str, tuple[Dict[str, Any], float]] = {}
        self.cache_ttl = cache_ttl
        logger.info("🔌 ClientManager inicializado com Supabase")
    
    def get_client_config(self, sip_number: str) -> Optional[AgentConfig]:
        """
        Obtém a configuração do cliente baseado no número SIP
        
        Args:
            sip_number: Número SIP do cliente (ex: '+5511999990001')
            
        Returns:
            AgentConfig com as configurações do cliente ou None se não encontrado
            
        Raises:
            Exception: Se houver erro ao buscar do Supabase
        """
        # 1. Verifica cache
        cached_config = self._get_from_cache(sip_number)
        if cached_config:
            logger.debug(f"⚡ Cache hit para número SIP: {sip_number}")
            return cached_config
        
        # 2. Cache miss - busca do Supabase
        logger.info(f"🔍 Buscando configuração do Supabase para: {sip_number}")
        
        try:
            # Busca o client_id pelo número SIP
            sip_data = self.supabase.table('client_sip_numbers') \
                .select('client_id, clients(client_id, client_name, active)') \
                .eq('sip_number', sip_number) \
                .eq('active', True) \
                .single() \
                .execute()
            
            if not sip_data.data:
                logger.warning(f"⚠️ Número SIP não encontrado: {sip_number}")
                return None
            
            client_uuid = sip_data.data['client_id']
            client_info = sip_data.data['clients']
            
            # Verifica se o cliente está ativo
            if not client_info or not client_info.get('active', False):
                logger.warning(f"⚠️ Cliente inativo para SIP: {sip_number}")
                return None
            
            # Busca as configurações do cliente
            config_data = self.supabase.table('client_configurations') \
                .select('*') \
                .eq('client_id', client_uuid) \
                .single() \
                .execute()
            
            if not config_data.data:
                logger.warning(f"⚠️ Configuração não encontrada para cliente: {client_info['client_name']}")
                return None
            
            # Converte para formato AgentConfig
            config_dict = self._convert_to_config_dict(config_data.data)
            
            # Cria AgentConfig
            agent_config = AgentConfig.from_dict(config_dict)
            
            # Armazena no cache
            self._store_in_cache(sip_number, agent_config)
            
            logger.info(f"✅ Configuração carregada para cliente: {client_info['client_name']}")
            return agent_config
            
        except Exception as e:
            logger.error(f"❌ Erro ao buscar configuração do Supabase: {e}")
            raise
    
    def _get_from_cache(self, sip_number: str) -> Optional[AgentConfig]:
        """Obtém configuração do cache se ainda válida"""
        if sip_number in self.cache:
            cached_config, timestamp = self.cache[sip_number]
            if time.time() - timestamp < self.cache_ttl:
                return cached_config
            else:
                # Cache expirado - remove
                del self.cache[sip_number]
        return None
    
    def _store_in_cache(self, sip_number: str, config: AgentConfig):
        """Armazena configuração no cache"""
        self.cache[sip_number] = (config, time.time())
        logger.debug(f"💾 Configuração armazenada no cache para: {sip_number}")
    
    def _convert_to_config_dict(self, db_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converte dados do Supabase para formato esperado pelo AgentConfig
        
        Args:
            db_data: Dados retornados do Supabase
            
        Returns:
            Dicionário no formato do agent_config.json
        """
        return {
            "model": db_data.get("model", "gpt-realtime"),
            "voice": db_data.get("voice", "en-US-Andrew:DragonHDLatestNeural"),
            "temperature": float(db_data.get("temperature", 0.7)),
            "max_tokens": int(db_data.get("max_tokens", 800)),
            "speech_rate": float(db_data.get("speech_rate", 1.0)),
            "top_p": float(db_data.get("top_p", 0.9)),
            "frequency_penalty": float(db_data.get("frequency_penalty", 0.0)),
            "presence_penalty": float(db_data.get("presence_penalty", 0.0)),
            "turn_detection": db_data.get("turn_detection", {
                "threshold": 0.5,
                "prefix_padding_ms": 100,
                "silence_duration_ms": 500
            }),
            "audio": db_data.get("audio_config", {
                "input_format": "PCM16",
                "output_format": "PCM16",
                "echo_cancellation": True,
                "noise_reduction": "azure_deep_noise_suppression"
            }),
            "modalities": ["TEXT", "AUDIO"],
            "instructions": db_data.get("instructions", "Você é um assistente útil.")
        }
    
    def invalidate_cache(self, sip_number: Optional[str] = None):
        """
        Invalida o cache
        
        Args:
            sip_number: Se fornecido, invalida apenas este número. 
                       Se None, invalida todo o cache.
        """
        if sip_number:
            if sip_number in self.cache:
                del self.cache[sip_number]
                logger.info(f"🗑️ Cache invalidado para: {sip_number}")
        else:
            self.cache.clear()
            logger.info("🗑️ Cache completo invalidado")
    
    def refresh_cache(self, sip_number: str) -> Optional[AgentConfig]:
        """
        Força atualização do cache para um número SIP
        
        Args:
            sip_number: Número SIP a atualizar
            
        Returns:
            AgentConfig atualizado ou None
        """
        self.invalidate_cache(sip_number)
        return self.get_client_config(sip_number)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache"""
        valid_entries = 0
        expired_entries = 0
        
        current_time = time.time()
        for _, (_, timestamp) in self.cache.items():
            if current_time - timestamp < self.cache_ttl:
                valid_entries += 1
            else:
                expired_entries += 1
        
        return {
            "total_entries": len(self.cache),
            "valid_entries": valid_entries,
            "expired_entries": expired_entries,
            "ttl_seconds": self.cache_ttl
        }


# Exemplo de uso
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Exemplo de teste
    manager = ClientManager(
        supabase_url=os.getenv("SUPABASE_URL"),
        supabase_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )
    
    # Testa com um número SIP
    test_number = "+5511999990001"
    config = manager.get_client_config(test_number)
    
    if config:
        print("✅ Configuração encontrada!")
        print(f"Voz: {config.voice}")
        print(f"Modelo: {config.config.get('model')}")
        print(f"Temperature: {config.temperature}")
    else:
        print(f"❌ Nenhuma configuração encontrada para {test_number}")
