#!/usr/bin/env python3
"""
Script de Verificação Pré-Deploy
Verifica se todos os requisitos estão prontos antes de fazer deploy no Easy Panel
"""

import os
import sys
import json
from pathlib import Path
from typing import List, Tuple

class Colors:
    """Cores ANSI para output colorido"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def check_mark(passed: bool) -> str:
    """Retorna checkmark colorido"""
    return f"{Colors.GREEN}✓{Colors.RESET}" if passed else f"{Colors.RED}✗{Colors.RESET}"

def print_header(text: str):
    """Imprime cabeçalho formatado"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")

def check_file_exists(filepath: str) -> Tuple[bool, str]:
    """Verifica se arquivo existe"""
    path = Path(filepath)
    if path.exists():
        return True, f"Arquivo encontrado: {filepath}"
    return False, f"Arquivo não encontrado: {filepath}"

def check_dockerfile() -> Tuple[bool, str]:
    """Verifica Dockerfile"""
    exists, msg = check_file_exists("Dockerfile")
    if not exists:
        return False, msg
    
    # Verifica conteúdo básico
    with open("Dockerfile", "r", encoding="utf-8") as f:
        content = f.read()
        if "FROM python" in content and "CMD" in content:
            return True, "Dockerfile válido"
        return False, "Dockerfile parece incompleto"

def check_requirements() -> Tuple[bool, str]:
    """Verifica requirements.txt"""
    exists, msg = check_file_exists("requirements.txt")
    if not exists:
        return False, msg
    
    with open("requirements.txt", "r", encoding="utf-8") as f:
        deps = f.read().strip()
        if len(deps) > 0:
            return True, "requirements.txt contém dependências"
        return False, "requirements.txt está vazio"

def check_json_valid(filepath: str) -> Tuple[bool, str]:
    """Verifica se arquivo JSON é válido"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            json.load(f)
        return True, f"{filepath} é JSON válido"
    except json.JSONDecodeError as e:
        return False, f"{filepath} tem erro JSON: {e}"
    except FileNotFoundError:
        return False, f"{filepath} não encontrado"

def check_agent_configs() -> List[Tuple[bool, str]]:
    """Verifica configs do agente"""
    configs = [
        "config/agent_config.json",
        "config/agent_config.production.json"
    ]
    
    results = []
    for config in configs:
        results.append(check_json_valid(config))
    
    return results

def check_env_example() -> Tuple[bool, str]:
    """Verifica se .env.example existe"""
    return check_file_exists(".env.example")

def check_no_env_in_git() -> Tuple[bool, str]:
    """Verifica se .env não está no Git"""
    gitignore_path = Path(".gitignore")
    
    if not gitignore_path.exists():
        return False, ".gitignore não encontrado"
    
    with open(".gitignore", "r", encoding="utf-8") as f:
        content = f.read()
        if ".env" in content:
            # Verifica se .env está staged no git
            git_status = os.popen("git ls-files .env").read().strip()
            if git_status:
                return False, ".env está no repositório Git! REMOVA IMEDIATAMENTE"
            return True, ".env está no .gitignore (seguro)"
        return False, ".env não está listado no .gitignore"

def check_main_files() -> List[Tuple[bool, str]]:
    """Verifica arquivos principais"""
    files = [
        "src/main.py",
        "src/core/config/settings.py",
        "src/core/config/agent_config_loader.py",
        "src/services/client_manager.py",
        "src/core/logging/logger.py"
    ]
    
    return [check_file_exists(f) for f in files]

def check_docker_build() -> Tuple[bool, str]:
    """Verifica se Docker build funciona (opcional)"""
    print(f"{Colors.YELLOW}Testando Docker build (isso pode levar alguns minutos)...{Colors.RESET}")
    
    result = os.system("docker build -t verify-test . > /dev/null 2>&1")
    
    if result == 0:
        # Limpa imagem de teste
        os.system("docker rmi verify-test > /dev/null 2>&1")
        return True, "Docker build bem-sucedido"
    return False, "Docker build FALHOU - verifique Dockerfile"

def get_env_vars_needed() -> List[str]:
    """Lista variáveis de ambiente necessárias"""
    return [
        "APP_ENV",
        "PORT",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_VOICELIVE_ENDPOINT",
        "AZURE_VOICELIVE_API_KEY",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY"
    ]

def print_env_checklist():
    """Imprime checklist de variáveis de ambiente"""
    print(f"\n{Colors.BOLD}Variáveis de Ambiente Necessárias no Easy Panel:{Colors.RESET}\n")
    
    for var in get_env_vars_needed():
        print(f"  • {var}")
    
    print(f"\n{Colors.YELLOW}Certifique-se de configurar TODAS no Easy Panel!{Colors.RESET}\n")

def main():
    """Execução principal"""
    print_header("Verificação Pré-Deploy - Easy Panel")
    
    all_passed = True
    
    # 1. Dockerfile
    print(f"{Colors.BOLD}1. Verificando Dockerfile...{Colors.RESET}")
    passed, msg = check_dockerfile()
    print(f"   {check_mark(passed)} {msg}")
    all_passed &= passed
    
    # 2. Requirements
    print(f"\n{Colors.BOLD}2. Verificando requirements.txt...{Colors.RESET}")
    passed, msg = check_requirements()
    print(f"   {check_mark(passed)} {msg}")
    all_passed &= passed
    
    # 3. Arquivos principais
    print(f"\n{Colors.BOLD}3. Verificando arquivos principais...{Colors.RESET}")
    results = check_main_files()
    for passed, msg in results:
        print(f"   {check_mark(passed)} {msg}")
        all_passed &= passed
    
    # 4. Agent configs
    print(f"\n{Colors.BOLD}4. Verificando configurações do agente...{Colors.RESET}")
    results = check_agent_configs()
    for passed, msg in results:
        print(f"   {check_mark(passed)} {msg}")
        all_passed &= passed
    
    # 5. .env.example
    print(f"\n{Colors.BOLD}5. Verificando .env.example...{Colors.RESET}")
    passed, msg = check_env_example()
    print(f"   {check_mark(passed)} {msg}")
    all_passed &= passed
    
    # 6. Segurança .env
    print(f"\n{Colors.BOLD}6. Verificando segurança .env...{Colors.RESET}")
    passed, msg = check_no_env_in_git()
    print(f"   {check_mark(passed)} {msg}")
    if not passed:
        print(f"   {Colors.RED}CRÍTICO: Remova .env do Git antes de fazer push!{Colors.RESET}")
    all_passed &= passed
    
    # 7. Docker build (opcional - pode ser lento)
    print(f"\n{Colors.BOLD}7. Teste de Docker Build (opcional)...{Colors.RESET}")
    
    response = input(f"   Deseja testar o build do Docker? (s/N): ").strip().lower()
    
    if response == 's':
        passed, msg = check_docker_build()
        print(f"   {check_mark(passed)} {msg}")
        all_passed &= passed
    else:
        print(f"   {Colors.YELLOW}⊘{Colors.RESET} Pulando teste de Docker build")
    
    # Resumo
    print_header("Resumo da Verificação")
    
    if all_passed:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ TUDO PRONTO PARA DEPLOY!{Colors.RESET}\n")
        print(f"{Colors.GREEN}Você pode prosseguir com o deploy no Easy Panel.{Colors.RESET}\n")
    else:
        print(f"{Colors.RED}{Colors.BOLD}✗ EXISTEM PROBLEMAS A CORRIGIR{Colors.RESET}\n")
        print(f"{Colors.RED}Corrija os erros acima antes de fazer deploy.{Colors.RESET}\n")
    
    # Checklist de env vars
    print_env_checklist()
    
    # Próximos passos
    print(f"{Colors.BOLD}Próximos Passos:{Colors.RESET}\n")
    print(f"  1. Faça push do código para GitHub/GitLab")
    print(f"  2. Acesse Easy Panel → Create → App")
    print(f"  3. Configure repositório Git")
    print(f"  4. Adicione variáveis de ambiente (lista acima)")
    print(f"  5. Clique em Deploy")
    print(f"  6. Aguarde build e verifique logs")
    print(f"  7. Teste: https://seu-dominio.easypanel.host/health\n")
    
    print(f"{Colors.BLUE}Consulte DEPLOY_EASYPANEL.md para guia completo{Colors.RESET}\n")
    
    # Exit code
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Verificação cancelada pelo usuário{Colors.RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Erro inesperado: {e}{Colors.RESET}")
        sys.exit(1)
