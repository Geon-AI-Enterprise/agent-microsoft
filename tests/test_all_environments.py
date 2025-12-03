"""
Script otimizado para testar sistema em todos os ambientes

Valida apenas variáveis essenciais e configurações críticas.
"""
import os
import sys
from pathlib import Path


class EnvironmentTester:
    """Testa configurações essenciais em todos os ambientes"""
    
    # Variáveis essenciais por ambiente
    REQUIRED_VARS = {
        'all': [
            'APP_ENV',
            'AZURE_OPENAI_ENDPOINT',
            'AZURE_OPENAI_API_KEY',
            'AZURE_VOICELIVE_ENDPOINT',
            'AZURE_VOICELIVE_API_KEY',
        ],
        'staging': ['SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY'],
        'production': ['SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY']
    }
    
    ENVIRONMENTS = {
        'development': {
            'env_file': '.env.development',
            'port': 8000,
            'description': 'Development (Local)',
            'log_level': 'DEBUG'
        },
        'staging': {
            'env_file': '.env.staging',
            'port': 8001,
            'description': 'Staging (Homologação)',
            'log_level': 'INFO'
        },
        'production': {
            'env_file': '.env.production',
            'port': 8000,
            'description': 'Production (Produção)',
            'log_level': 'WARNING'
        }
    }
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
    
    def load_env_file(self, env_file: str) -> dict:
        """Carrega variáveis de um arquivo .env"""
        env_path = self.project_root / env_file
        
        if not env_path.exists():
            return {}
        
        env_vars = {}
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
        
        return env_vars
    
    def validate_required_vars(self, env_vars: dict, env_name: str) -> tuple[bool, list]:
        """Valida se variáveis essenciais estão presentes"""
        required = self.REQUIRED_VARS['all'].copy()
        
        # Adiciona variáveis específicas do ambiente
        if env_name in self.REQUIRED_VARS:
            required.extend(self.REQUIRED_VARS[env_name])
        
        missing = []
        for var in required:
            value = env_vars.get(var, '')
            # Considera missing se: não existe, vazio, ou placeholder
            if not value or value.startswith('your-'):
                missing.append(var)
        
        return len(missing) == 0, missing
    
    def test_settings_import(self, env_vars: dict) -> tuple[bool, str]:
        """Testa importação do settings.py"""
        try:
            # Injeta variáveis
            os.environ.update(env_vars)
            
            # Força reimport
            if 'settings' in sys.modules:
                del sys.modules['settings']
            
            from src.core.config import get_settings
            get_settings.cache_clear() if hasattr(get_settings, 'cache_clear') else None
            
            settings = get_settings()
            
            # Valida valores básicos
            assert settings.APP_ENV in ['development', 'staging', 'production']
            assert settings.PORT > 0
            assert settings.AZURE_OPENAI_ENDPOINT
            assert settings.AZURE_VOICELIVE_ENDPOINT
            
            return True, f"Settings OK | APP_ENV={settings.APP_ENV} | PORT={settings.PORT}"
            
        except Exception as e:
            return False, f"Erro: {str(e)}"
    
    def test_client_manager(self, env_vars: dict, env_name: str) -> tuple[bool, str]:
        """Testa ClientManager (apenas staging/production)"""
        if env_name == 'development':
            return True, "ClientManager opcional em dev"
        
        try:
            os.environ.update(env_vars)
            
            if 'client_manager' in sys.modules:
                del sys.modules['client_manager']
            
            from client_manager import ClientManager
            
            manager = ClientManager(
                supabase_url=env_vars['SUPABASE_URL'],
                supabase_key=env_vars['SUPABASE_SERVICE_ROLE_KEY'],
                cache_ttl=60
            )
            
            return True, "ClientManager inicializado"
            
        except Exception as e:
            return False, f"Erro: {str(e)}"
    
    def test_environment(self, env_name: str) -> bool:
        """Testa um ambiente específico"""
        env_config = self.ENVIRONMENTS[env_name]
        
        print(f"\n{'=' * 70}")
        print(f"🧪 {env_config['description'].upper()}")
        print(f"{'=' * 70}")
        
        # 1. Carrega .env
        print(f"\n📄 Carregando {env_config['env_file']}...", end=' ')
        env_vars = self.load_env_file(env_config['env_file'])
        
        if not env_vars:
            print("❌ ERRO")
            print(f"   Arquivo não encontrado ou vazio")
            return False
        
        print(f"✅ OK ({len(env_vars)} variáveis)")
        
        # 2. Valida variáveis essenciais
        print(f"\n🔍 Validando variáveis essenciais...", end=' ')
        is_valid, missing = self.validate_required_vars(env_vars, env_name)
        
        if not is_valid:
            print("❌ FALTANDO")
            for var in missing:
                print(f"   ⚠️  {var}")
            print(f"\n   Configure {env_config['env_file']} antes de testar")
            return False
        
        print("✅ OK")
        
        # 3. Testa Settings
        print(f"\n⚙️  Testando Settings...", end=' ')
        success, msg = self.test_settings_import(env_vars)
        
        if not success:
            print("❌ ERRO")
            print(f"   {msg}")
            return False
        
        print(f"✅ OK")
        print(f"   {msg}")
        
        # 4. Testa ClientManager (se aplicável)
        print(f"\n🗄️  Testando ClientManager...", end=' ')
        success, msg = self.test_client_manager(env_vars, env_name)
        
        if not success:
            print("❌ ERRO")
            print(f"   {msg}")
            return False
        
        print(f"✅ OK")
        print(f"   {msg}")
        
        print(f"\n{'✅ ' + env_name.upper() + ' PASSOU':^70}")
        
        return True
    
    def run_all_tests(self) -> bool:
        """Executa testes em todos os ambientes"""
        print("=" * 70)
        print("🧪 TESTE MULTI-AMBIENTE - SISTEMA OTIMIZADO".center(70))
        print("=" * 70)
        
        results = {}
        
        for env_name in ['development', 'staging', 'production']:
            results[env_name] = self.test_environment(env_name)
        
        # Resumo
        print(f"\n{'=' * 70}")
        print("📊 RESUMO".center(70))
        print(f"{'=' * 70}\n")
        
        for env_name, passed in results.items():
            status = "✅ PASSOU" if passed else "❌ FALHOU"
            print(f"  {env_name.ljust(15)} {status}")
        
        all_passed = all(results.values())
        
        print(f"\n{'=' * 70}")
        if all_passed:
            print("🎉 TODOS OS AMBIENTES PASSARAM!".center(70))
        else:
            print("⚠️  ALGUNS AMBIENTES FALHARAM".center(70))
        print(f"{'=' * 70}\n")
        
        return all_passed


def main():
    """Função principal"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Testa configurações essenciais por ambiente'
    )
    parser.add_argument(
        '--env',
        choices=['development', 'staging', 'production', 'all'],
        default='all',
        help='Ambiente a testar (padrão: all)'
    )
    
    args = parser.parse_args()
    
    tester = EnvironmentTester()
    
    if args.env == 'all':
        success = tester.run_all_tests()
    else:
        success = tester.test_environment(args.env)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
