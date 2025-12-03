"""
Script de Testes - Multi-Environment Setup
Valida se a implementação está funcionando corretamente em todos os ambientes
"""

import sys
import os

# Cores para output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")

def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")

def print_error(text):
    print(f"{Colors.RED}❌ {text}{Colors.END}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.END}")

def test_environment(env_name):
    """Testa um ambiente específico"""
    print_header(f"TESTANDO AMBIENTE: {env_name.upper()}")
    
    # Define o ambiente
    os.environ['APP_ENV'] = env_name
    
    try:
        # Teste 1: Import e validação do Settings
        print_info("Teste 1: Validando Settings...")
        from src.core.config import get_settings
        settings = get_settings()
        
        assert settings.APP_ENV == env_name, f"APP_ENV incorreto: {settings.APP_ENV}"
        print_success(f"APP_ENV: {settings.APP_ENV}")
        print_success(f"PORT: {settings.PORT}")
        print_success(f"Log Level: {settings.get_log_level()}")
        
        # Teste 2: Métodos helpers
        print_info("\nTeste 2: Validando métodos helpers...")
        is_dev = settings.is_development()
        is_stg = settings.is_staging()
        is_prod = settings.is_production()
        
        print_success(f"is_development(): {is_dev}")
        print_success(f"is_staging(): {is_stg}")
        print_success(f"is_production(): {is_prod}")
        
        # Valida que apenas um é True
        true_count = sum([is_dev, is_stg, is_prod])
        assert true_count == 1, f"Esperado 1 ambiente True, encontrado {true_count}"
        print_success("✓ Apenas um ambiente está ativo (correto)")
        
        # Teste 3: AgentConfig
        print_info("\nTeste 3: Validando AgentConfig...")
        from src.core.config import AgentConfig
        config = AgentConfig("config/agent_config.json", env=env_name)
        
        print_success(f"Arquivo carregado: {config.config_path}")
        print_success(f"Voz: {config.voice}")
        print_success(f"Temperature: {config.temperature}")
        print_success(f"Max Tokens: {config.max_tokens}")
        
        # Teste 4: Valida arquivo específico (staging/production)
        if env_name in ['staging', 'production']:
            expected_file = f"agent_config.{env_name}.json"
            if expected_file in str(config.config_path):
                print_success(f"✓ Usando arquivo específico: {expected_file}")
            else:
                print_warning(f"Usando fallback: agent_config.json (arquivo {expected_file} não existe)")
        
        # Teste 5: Log level esperado
        print_info("\nTeste 4: Validando log level...")
        expected_levels = {
            'development': 'DEBUG',
            'staging': 'INFO',
            'production': 'WARNING'
        }
        expected = expected_levels[env_name]
        actual = settings.get_log_level()
        assert actual == expected, f"Esperado {expected}, encontrado {actual}"
        print_success(f"✓ Log level correto: {actual}")
        
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 TODOS OS TESTES PASSARAM PARA {env_name.upper()}!{Colors.END}\n")
        return True
        
    except Exception as e:
        print_error(f"FALHA no ambiente {env_name}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_all_environments():
    """Executa testes em todos os ambientes"""
    print_header("INICIANDO TESTES DE MULTI-AMBIENTE")
    
    environments = ['development', 'staging', 'production']
    results = {}
    
    for env in environments:
        # Limpa imports anteriores para evitar cache
        if 'src.core.config.settings' in sys.modules:
            del sys.modules['src.core.config.settings']
        if 'src.core.config.agent_config_loader' in sys.modules:
            del sys.modules['src.core.config.agent_config_loader']
        
        results[env] = test_environment(env)
    
    # Resumo final
    print_header("RESUMO DOS TESTES")
    
    all_passed = True
    for env, passed in results.items():
        if passed:
            print_success(f"{env.upper()}: PASSOU")
        else:
            print_error(f"{env.upper()}: FALHOU")
            all_passed = False
    
    print("\n" + "="*60)
    
    if all_passed:
        print(f"{Colors.GREEN}{Colors.BOLD}")
        print("  ╔═══════════════════════════════════════════════════╗")
        print("  ║                                                   ║")
        print("  ║    ✅ TODOS OS TESTES PASSARAM COM SUCESSO!      ║")
        print("  ║                                                   ║")
        print("  ║    Sua implementação está funcionando            ║")
        print("  ║    perfeitamente em todos os ambientes!          ║")
        print("  ║                                                   ║")
        print("  ╚═══════════════════════════════════════════════════╝")
        print(f"{Colors.END}\n")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}")
        print("  ╔═══════════════════════════════════════════════════╗")
        print("  ║                                                   ║")
        print("  ║    ❌ ALGUNS TESTES FALHARAM                     ║")
        print("  ║                                                   ║")
        print("  ║    Revise os erros acima                         ║")
        print("  ║                                                   ║")
        print("  ╚═══════════════════════════════════════════════════╝")
        print(f"{Colors.END}\n")
        return 1

if __name__ == "__main__":
    sys.exit(test_all_environments())
