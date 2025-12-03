# Geon AI - Voice Agent

Bem-vindo à documentação oficial do **Geon AI - Voice Agent** - um backend profissional e robusto para agentes de voz utilizando Azure OpenAI Realtime API.

## 🎯 Visão Geral

O Geon AI - Voice Agent é uma solução completa e production-ready para implementar assistentes de voz inteligentes com suporte a múltiplos ambientes, logging amigável e configuração flexível.

### Principais Características

- ✅ **Multi-Ambiente**: Suporte completo para Development, Staging e Production
- 🎤 **Áudio em Tempo Real**: Captura de voz e reprodução via PyAudio (development)
- 🔊 **Modo API**: Servidor otimizado para staging/production
- 📝 **Logs Amigáveis**: Sistema de logging limpo e fácil de ler
- ⚙️ **Configuração Flexível**: Arquivos `.env` e `agent_config.json` por ambiente
- 🚀 **Hot-reload**: Desenvolvimento ágil com reinicialização automática
- ✅ **Validação Automática**: Validação de configurações por ambiente


## 📦 Tecnologias Utilizadas

| Tecnologia | Versão | Uso |
|------------|--------|-----|
| **Python** | 3.8+ | Linguagem principal |
| **FastAPI** | Latest | Framework web assíncrono |
| **Azure AI VoiceLive** | Latest | SDK do Azure para voz |
| **Pydantic** | Latest | Validação e settings |
| **PyAudio** | Latest | Áudio local (opcional) |
| **Uvicorn** | Latest | Servidor ASGI |

## 🚀 Início Rápido

### Instalação

```bash
# Clone o repositório
git clone <repository-url>
cd agent-microsoft

# Crie ambiente virtual
python -m venv .venv

# Ative o ambiente virtual
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# Instale dependências
pip install -r requirements.txt
```

### Configuração

```bash
# Copie o template de configuração
copy .env.example .env

# Edite o .env com suas credenciais Azure
notepad .env
```

### Executar

```bash
# Modo development (padrão)
python main.py

# Modo staging
set APP_ENV=staging
python main.py

# Modo production
set APP_ENV=production
python main.py
```

## 📚 Estrutura do Projeto

```
agent-microsoft/
├── docs/                       # Documentação (MkDocs)
├── logs/                       # Arquivos de log
├── .venv/                      # Ambiente virtual Python
│
├── main.py                     # Aplicação principal
├── settings.py                 # Configurações e validações
├── agent_config_loader.py      # Carregador de config do agente
├── logger_config.py            # Sistema de logging amigável
│
├── .env                        # Config development (gitignored)
├── .env.example                # Template de configuração
├── .env.staging                # Config staging (gitignored)
├── .env.production             # Config production (gitignored)
│
├── agent_config.json           # Config agente (development)
├── agent_config.staging.json   # Config agente (staging)
├── agent_config.production.json# Config agente (production)
│
├── requirements.txt            # Dependências Python
├── mkdocs.yml                  # Configuração da documentação
├── README.md                   # Readme principal
├── DEPLOYMENT.md               # Guia de deploy
└── TESTING.md                  # Guia de testes
```

## 🎨 Ambientes Suportados

### Development
- 🎤 Áudio local habilitado
- 🔄 Hot-reload ativo
- 📊 Logs DEBUG (muito detalhados)
- 🎨 Logs coloridos com emojis

### Staging
- 🔌 Modo API (sem áudio local)
- 📊 Logs INFO (moderados)
- ⚠️  Stacktraces resumidos
- ✅ Para homologação e testes

### Production
- 🔌 Modo API otimizado
- 📊 Logs WARNING (essenciais)
- ❌ Sem stacktraces
- 🚀 Performance otimizada

## 📖 Próximos Passos

- 📝 [Início Rápido](quick-start.md) - Comece a usar em minutos
- 🎯 [Principais Features](features.md) - Conheça todas as funcionalidades
- ⚙️  Configuração - Configure seu ambiente
- 👨‍💻 [Guia de Desenvolvimento](development/guide.md) - Comece a desenvolver
- 🚀 Deploy - Faça deploy em produção

## 🤝 Contribuindo

Contribuições são bem-vindas! Por favor, leia o guia de desenvolvimento antes de enviar PRs.