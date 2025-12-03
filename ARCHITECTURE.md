# Arquitetura do Projeto - Azure VoiceLive Agent

## Visão Geral

O projeto segue princípios de **Clean Architecture** e **Separation of Concerns**, organizando o código em camadas bem definidas.

---

## Estrutura de Diretórios

```
src/
├── main.py              # Entry point
├── core/                # Infraestrutura
│   ├── config/          # Configurações
│   ├── logging/         # Sistema de logs
│   └── models/          # Modelos de dados
├── services/            # Lógica de negócio
│   ├── voice_assistant.py
│   ├── audio_processor.py
│   └── client_manager.py
└── api/                 # Interface HTTP
    └── routes.py
```

---

## Camadas

### 1. Core (Infraestrutura)

**Responsabilidade:** Componentes de infraestrutura e configuração

**Módulos:**
- `config/settings.py` - Configurações de ambiente (.env)
- `config/agent_config_loader.py` - Carregamento de configs JSON
- `logging/logger.py` - Sistema de logging configurável

**Regra:** Core não depende de nada, apenas bibliotecas externas

---

### 2. Services (Lógica de Negócio)

**Responsabilidade:** Implementação da lógica de negócio

**Módulos:**
- `voice_assistant.py` - Worker principal do assistente
- `audio_processor.py` - Processamento de áudio local
- `client_manager.py` - Gerenciamento multi-tenant com Supabase

**Regra:** Services podem depender de Core, mas não de API

---

### 3. API (Interface HTTP)

**Responsabilidade:** Endpoints HTTP e interface externa

**Módulos:**
- `routes.py` - FastAPI routes e lifespan management

**Regra:** API depende de Services e Core

---

## Fluxo de Dados

```
[Client HTTP Request]
        ↓
    [API Layer]
        ↓
  [Services Layer]
        ↓
    [Core Layer]
        ↓
  [External APIs]
  (Azure, Supabase)
```

---

## Princípios Aplicados

### 1. Separation of Concerns (SoC)
Cada módulo tem uma responsabilidade clara e única.

### 2. Dependency Inversion
Camadas superiores dependem de camadas inferiores, nunca o contrário.

### 3. Single Responsibility Principle (SRP)
Cada classe/módulo tem apenas uma razão para mudar.

### 4. Don't Repeat Yourself (DRY)
Código reutilizável em módulos compartilhados.

---

## Importação de Módulos

### Padrão de Imports

```python
# Biblioteca padrão
import asyncio
import logging

# Bibliotecas externas
from fastapi import FastAPI
from azure.ai.voicelive.aio import connect

# Imports internos (absolutos)
from src.core.config import get_settings, AgentConfig
from src.core.logging import setup_logging
from src.services.voice_assistant import VoiceAssistantWorker
```

### Exports via `__init__.py`

Cada pacote expõe sua interface pública via `__all__`:

```python
# src/core/config/__init__.py
from .settings import get_settings, Settings
from .agent_config_loader import AgentConfig

__all__ = ["get_settings", "Settings", "AgentConfig"]
```

---

## Configuração por Ambiente

### Settings (src/core/config/settings.py)

Variáveis de ambiente (.env):
- `APP_ENV` - Ambiente (development/staging/production)
- Credenciais Azure
- Credenciais Supabase

### Agent Config (config/agent_config*.json)

Configurações do agente por ambiente:
- `config/agent_config.json` - Development
- `config/agent_config.staging.json` - Staging  
- `config/agent_config.production.json` - Production

---

## Entry Point

### src/main.py

1. Inicializa settings
2. Configura logging
3. Importa app FastAPI
4. Inicia servidor uvicorn

**Execução:**
```bash
python -m src.main
```

---

## Docker

### Dockerfile

Multi-stage build:
1. **Base** - Python 3.11 slim
2. **Dependencies** - Instala dependências
3. **Application** - Copia código e configura

**Entry Point:**
```dockerfile
CMD ["python", "-m", "src.main"]
```

### docker-compose.yml

Três ambientes separados:
- `voicelive-dev` - Development (hot-reload)
- `voicelive-staging` - Staging
- `voicelive-prod` - Production (com limites de recursos)

---

## Testes

### Estrutura de Testes

```
tests/
├── __init__.py
├── test_environments.py      # Testa multi-ambiente
├── test_all_environments.py  # Testa todos os ambientes
└── test_client_manager.py    # Testa multi-tenant
```

### Execução

```bash
# Testes unitários
python -m pytest tests/

# Test específico
python tests/test_environments.py
```

---

## Scripts Utilitários

### scripts/verify_deploy.py

Verifica se projeto está pronto para deploy:
- ✓ Dockerfile válido
- ✓ Arquivos principais existem
- ✓ Configurações JSON válidas
- ✓ Segurança (.env não no Git)

```bash
python scripts/verify_deploy.py
```

---

## Benefícios da Arquitetura

### Manutenibilidade
✅ Fácil encontrar e modificar código  
✅ Módulos bem separados

### Testabilidade
✅ Componentes isolados  
✅ Fácil criar mocks

### Escalabilidade
✅ Adicionar novos serviços é trivial  
✅ Estrutura preparada para crescimento

### Profissionalismo
✅ Segue padrões de mercado  
✅ Facilita onboarding de novos desenvolvedores

---

## Extensibilidade

### Adicionar Novo Serviço

1. Criar `src/services/novo_servico.py`
2. Implementar lógica de negócio
3. Exportar em `src/services/__init__.py`
4. Usar em `src/api/routes.py` ou `src/services/voice_assistant.py`

### Adicionar Novo Endpoint

1. Adicionar rota em `src/api/routes.py`
2. Usar serviços existentes
3. Retornar response apropriado

### Adicionar Novo Modelo

1. Criar classe em `src/core/models/`
2. Exportar em `__init__.py`
3. Usar nos serviços

---

## Referências

- [Clean Architecture (Robert C. Martin)](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Python Application Layouts](https://realpython.com/python-application-layouts/)
- [FastAPI Best Practices](https://fastapi.tiangolo.com/tutorial/)
- [Twelve-Factor App](https://12factor.net/)

---

**Última atualização:** 2025-12-03  
**Versão:** 1.0.0
