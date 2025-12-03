"""
Script de teste para ClientManager com Supabase

Este script testa a integração multi-tenant, buscando configurações
do Supabase baseado em números SIP.
"""
import os
import sys
from dotenv import load_dotenv
from src.services.client_manager import ClientManager

# Carrega variáveis de ambiente
load_dotenv()

def test_client_manager():
    """Testa o ClientManager com números SIP"""
    
    print("=" * 70)
    print(" TESTE DO CLIENT MANAGER - MULTI-TENANT")
    print("=" * 70)
    
    # Inicializa o ClientManager
    try:
        manager = ClientManager(
            supabase_url=os.getenv("SUPABASE_URL"),
            supabase_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
            cache_ttl=300  # 5 minutos
        )
        print("✅ ClientManager inicializado com sucesso\n")
    except Exception as e:
        print(f"❌ Erro ao inicializar ClientManager: {e}")
        sys.exit(1)
    
    # Lista de números SIP para testar
    test_numbers = [
        "+5511999990003"  # Cliente Sofia teste
    ]
    
    for sip_number in test_numbers:
        print(f"\n{'=' * 70}")
        print(f"🔍 Testando número SIP: {sip_number}")
        print("=" * 70)
        
        try:
            # Busca configuração
            config = manager.get_client_config(sip_number)
            
            if config:
                print(f"✅ Configuração encontrada!\n")
                print(f"  📋 Modelo: {config.config.get('model')}")
                print(f"  🎤 Voz: {config.voice}")
                print(f"  🌡️  Temperature: {config.temperature}")
                print(f"  📝 Max Tokens: {config.max_tokens}")
                print(f"  📄 Instructions (primeiros 100 chars):")
                print(f"     {config.instructions[:100]}...")
            else:
                print(f"⚠️  Nenhuma configuração encontrada para {sip_number}")
                
        except Exception as e:
            print(f"❌ Erro ao buscar configuração: {e}")
    
    # Testa cache
    print(f"\n{'=' * 70}")
    print("⚡ TESTE DE CACHE")
    print("=" * 70)
    
    test_number = test_numbers[0]
    print(f"\n1️⃣ Primeira busca (cache miss): {test_number}")
    config1 = manager.get_client_config(test_number)
    
    print(f"\n2️⃣ Segunda busca (cache hit): {test_number}")
    config2 = manager.get_client_config(test_number)
    
    if config1 and config2:
        print("✅ Ambas as buscas retornaram configuração")
        print(f"   São a mesma instância? {config1 is config2}")
    
    # Estatísticas do cache
    print(f"\n{'=' * 70}")
    print("📊 ESTATÍSTICAS DO CACHE")
    print("=" * 70)
    
    stats = manager.get_cache_stats()
    print(f"  Total de entradas: {stats['total_entries']}")
    print(f"  Entradas válidas: {stats['valid_entries']}")
    print(f"  Entradas expiradas: {stats['expired_entries']}")
    print(f"  TTL (segundos): {stats['ttl_seconds']}")
    
    print(f"\n{'=' * 70}")
    print("✅ TESTES CONCLUÍDOS")
    print("=" * 70)


if __name__ == "__main__":
    test_client_manager()
