# Azure VoiceLive Agent - Multi-Tenant

Backend profissional para agentes de voz utilizando Azure OpenAI Realtime API com suporte **multi-tenant via WebSocket**.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Azure](https://img.shields.io/badge/Azure-0078D4?logo=microsoft-azure&logoColor=white)](https://azure.microsoft.com/)
[![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?logo=supabase&logoColor=white)](https://supabase.com/)

---

## 🚀 Quick Start

```bash
# 1. Clone e instale
git clone <repository-url>
cd agent-microsoft
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure variáveis de ambiente
copy .env.example .env
# Edite .env com suas credenciais Azure + Supabase

# 3. Execute
python -m src.main
```

Acesse: `http://localhost:8000/health`

---

## ✨ Features

- 🌍 **Multi-Tenant**: Suporte a múltiplos clientes simultâneos via WebSocket
- 🔌 **WebSocket Audio Streaming**: Comunicação em tempo real bidirecional
- 🗄️ **Configuração Dinâmica**: Configurações por cliente no Supabase
- 🎤 **Áudio em Tempo Real**: Captura e reprodução (dev only)
- 📝 **Logs Amigáveis**: Formatação limpa e colorida
- ⚙️ **Configuração Flexível**: Arquivo local (dev) ou Supabase (prod)
- 🚀 **Hot-reload**: Desenvolvimento ágil
- ✅ **Validação Automática**: Pydantic settings
- 🎯 **Barge-in**: Interrupção natural do agente
- 🔒 **Isolamento por Sessão**: Worker dedicado por conexão WebSocket

---

## 🏗️ Arquitetura Multi-Tenant

```
┌─────────────────┐
│  Cliente 1      │──┐
│  (+5511990001)  │  │
└─────────────────┘  │
                     │    ┌──────────────────────────┐
┌─────────────────┐  │    │   FastAPI WebSocket      │
│  Cliente 2      │──┼───▶│   /ws/audio/{sip}        │
│  (+5511990002)  │  │    └──────────────────────────┘
└─────────────────┘  │              │
                     │              │ Busca Config
┌─────────────────┐  │              ▼
│  Cliente N      │──┘    ┌──────────────────────────┐
│  (+5511990XXX)  │       │      Supabase            │
└─────────────────┘       │   (Configurações)        │
                          └──────────────────────────┘
                                    │
                          ┌─────────┴─────────┐
                          │                   │
                   ┌──────▼─────┐      ┌─────▼──────┐
                   │  Worker 1  │      │  Worker 2  │
                   │  (Config1) │      │  (Config2) │
                   └──────┬─────┘      └─────┬──────┘
                          │                   │
                          └─────────┬─────────┘
                                    ▼
                          ┌──────────────────────────┐
                          │   Azure VoiceLive API    │
                          └──────────────────────────┘
```

Cada cliente tem sua própria configuração no Supabase (prompt, voz, parâmetros) e worker dedicado.

---

## 📂 Estrutura do Projeto

```
agent-microsoft/
├── src/                          # 📦 Código-fonte da aplicação
│   ├── __init__.py
│   ├── main.py                   # Entry point principal
│   │
│   ├── core/                     # 🎯 Infraestrutura e configuração
│   │   ├── __init__.py
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   ├── settings.py       # Configurações de ambiente
│   │   │   └── agent_config_loader.py
│   │   ├── logging/
│   │   │   ├── __init__.py
│   │   │   └── logger.py         # Sistema de logs
│   │   └── models/
│   │       └── __init__.py
│   │
│   ├── services/                 # 🔧 Lógica de negócio
│   │   ├── __init__.py
│   │   ├── voice_assistant.py    # Worker principal (com DI)
│   │   ├── audio_processor.py    # Processamento de áudio
│   │   └── client_manager.py     # Gerenciamento multi-tenant (Supabase)
│   │
│   └── api/                      # 🌐 Endpoints HTTP/WebSocket
│       ├── __init__.py
│       └── routes.py             # FastAPI routes + WebSocket
│
├── config/                       # ⚙️ Arquivos de configuração (dev local)
│   ├── agent_config.json         # Config development
│   ├── agent_config.staging.json
│   └── agent_config.production.json
│
├── tests/                        # 🧪 Testes automatizados
│   ├── __init__.py
│   ├── test_environments.py
│   ├── test_all_environments.py
│   └── test_client_manager.py
│
├── scripts/                      # 🔨 Utilitários e scripts
│   ├── verify_deploy.py          # Verificação pré-deploy
│   └── run_env.bat
│
├── docs/                         # 📚 Documentação completa
├── logs/                         # 📝 Logs gerados
│
├── .env.example                  # Template de variáveis
├── Dockerfile                    # Build Docker
├── docker-compose.yml            # Orquestração multi-ambiente
├── requirements.txt              # Dependências Python
└── README.md
```

**Nota:** Estrutura organizada seguindo Clean Architecture com injeção de dependência.

---

## 🔌 WebSocket API

### Endpoint Multi-Tenant

```
ws://localhost:8000/ws/audio/{sip_number}
```

**Parâmetros:**
- `sip_number`: Número SIP do cliente (ex: `+5511999990001`)

### Fluxo de Conexão

1. Cliente conecta em `/ws/audio/+5511999990001`
2. Sistema busca configuração do cliente no Supabase
3. Cria Worker dedicado com configuração específica
4. Estabelece ponte bidirecional de áudio
5. Streaming em tempo real (entrada e saída)

### Exemplo de Cliente JavaScript

```javascript
// Conectar ao WebSocket
const ws = new WebSocket('ws://localhost:8000/ws/audio/+5511999990001');

ws.onopen = () => {
  console.log('✅ Conectado ao servidor');
  
  // Enviar áudio (PCM16 base64-encoded, 24kHz, mono)
  const audioBuffer = new Uint8Array(960); // 40ms de áudio
  const encoded = btoa(String.fromCharCode(...audioBuffer));
  ws.send(encoded);
};

// Receber respostas de áudio
ws.onmessage = (event) => {
  const audioData = atob(event.data); // Decodifica base64
  // Reproduzir áudio...
};

ws.onerror = (error) => console.error('❌ Erro:', error);
ws.onclose = (event) => console.log('🔌 Desconectado:', event.code);
```

### Códigos de Erro WebSocket

| Código | Significado |
|--------|-------------|
| 4004 | Cliente não encontrado no Supabase |
| 1011 | Erro ao conectar com Azure VoiceLive |
| 1000 | Desconexão normal |

---

## 🔧 Configuração

### Variáveis de Ambiente (.env)

```bash
# Azure VoiceLive
AZURE_VOICELIVE_ENDPOINT=https://xxx.openai.azure.com
AZURE_VOICELIVE_API_KEY=xxx
AZURE_VOICELIVE_MODEL=gpt-realtime

# Supabase (Multi-tenant)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...

# Aplicação
APP_ENV=development  # development, staging, production
PORT=8000
LOG_LEVEL=INFO
```

### Estrutura do Supabase

O sistema requer as seguintes tabelas:

#### `client_sip_numbers`
```sql
CREATE TABLE client_sip_numbers (
  sip_number TEXT PRIMARY KEY,
  client_id UUID REFERENCES clients(client_id),
  active BOOLEAN DEFAULT true
);
```

#### `clients`
```sql
CREATE TABLE clients (
  client_id UUID PRIMARY KEY,
  client_name TEXT NOT NULL,
  active BOOLEAN DEFAULT true
);
```

#### `client_configurations`
```sql
CREATE TABLE client_configurations (
  client_id UUID PRIMARY KEY REFERENCES clients(client_id),
  voice TEXT,
  temperature FLOAT,
  max_tokens INT,
  instructions TEXT,
  -- outros parâmetros...
);
```

---

## 🔧 Ambientes

### Development (Local)
```bash
python -m src.main
# Worker local com áudio, config do arquivo, hot-reload, logs DEBUG
```

### Staging (API Mode)
```bash
set APP_ENV=staging
python -m src.main
# WebSocket ativo, config do Supabase, logs INFO
```

### Production
```bash
set APP_ENV=production
python -m src.main
# Otimizado, WebSocket, Supabase, logs WARNING
```

---

## ⚙️ Configuração do Agente

### Desenvolvimento Local (Arquivo)

Edite `config/agent_config.json`:

```json
{
  "voice": "pt-BR-FranciscaNeural",
  "temperature": 0.7,
  "max_tokens": 800,
  "speech_rate": 1.0,
  "instructions": "Você é um assistente útil...",
  "turn_detection": {
    "threshold": 0.5,
    "silence_duration_ms": 500
  },
  "audio": {
    "input_format": "PCM16",
    "output_format": "PCM16",
    "echo_cancellation": true,
    "noise_reduction": "azure_deep_noise_suppression"
  }
}
```

### Produção (Supabase)

Configurações armazenadas na tabela `client_configurations`, carregadas dinamicamente por número SIP.

**Vozes Brasileiras Disponíveis:**
- `pt-BR-FranciscaNeural` - Feminina clara e profissional
- `pt-BR-BrendaNeural` - Feminina jovem e amigável
- `pt-BR-AntonioNeural` - Masculina séria e confiável
- `pt-BR-DonatoNeural` - Masculina madura e experiente

[Lista completa de vozes Azure →](https://learn.microsoft.com/azure/ai-services/speech-service/language-support?tabs=tts)

---

## 🧪 Testes

### Health Check
```bash
curl http://localhost:8000/health
```

**Resposta:**
```json
{
  "status": "ok",
  "env": "development",
  "worker_status": "connected",
  "voice_model": "pt-BR-FabioNeural"
}
```

### Teste WebSocket (Python)
```python
import asyncio
import websockets
import base64

async def test_websocket():
    uri = "ws://localhost:8000/ws/audio/+5511999990001"
    async with websockets.connect(uri) as websocket:
        # Envia áudio de teste
        audio_data = bytes(960)  # 40ms silêncio
        encoded = base64.b64encode(audio_data).decode('utf-8')
        await websocket.send(encoded)
        
        # Recebe resposta
        response = await websocket.recv()
        print(f"Recebido: {len(response)} bytes")

asyncio.run(test_websocket())
```

---

## 🚀 Deploy

### Easy Panel (Recomendado) 🎯

```bash
# 1. Configure variáveis de ambiente no Easy Panel
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
AZURE_VOICELIVE_ENDPOINT=...
AZURE_VOICELIVE_API_KEY=...
APP_ENV=production

# 2. Push para GitHub
git push origin main

# 3. Easy Panel fará deploy automático via Dockerfile
```

📖 **Guias Completos:**
- [Quick Start (5 minutos)](./QUICK_DEPLOY.md)
- [Guia Detalhado Easy Panel](./DEPLOY_EASYPANEL.md)

### Docker Local

```bash
# Build da imagem
docker build -t voicelive-agent .

# Run com variáveis de ambiente
docker run -p 8000:8000 \
  -e SUPABASE_URL=xxx \
  -e SUPABASE_SERVICE_ROLE_KEY=xxx \
  -e AZURE_VOICELIVE_ENDPOINT=xxx \
  -e AZURE_VOICELIVE_API_KEY=xxx \
  -e APP_ENV=production \
  voicelive-agent
```

### Docker Compose

```bash
# Development
docker-compose up voicelive-dev

# Staging (com Supabase)
docker-compose up voicelive-staging

# Production
docker-compose up voicelive-prod
```

---

## 📚 Documentação Completa

Para documentação detalhada, use MkDocs:

```bash
pip install mkdocs mkdocs-material
mkdocs serve
```

Acesse: **http://localhost:8000**

Ou leia: [DOCUMENTATION.md](DOCUMENTATION.md)

### Principais Seções

- 📖 [Visão Geral](docs/index.md)
- ⚡ [Início Rápido](docs/quick-start.md)
- 🎯 [Features Completas](docs/features.md)
- 🔌 [WebSocket API](docs/websocket-api.md) ⭐ **Novo**
- ⚙️ [Configuração Multi-Tenant](docs/multi-tenant.md) ⭐ **Novo**
- 👨‍💻 [Guia de Desenvolvimento](docs/development/guide.md)
- 🚀 [Deploy](docs/deployment.md)
- 🧪 [Testes](docs/testing.md)

---

## 🔍 Troubleshooting

### WebSocket não conecta
- ✅ Verifique se o número SIP existe no Supabase
- ✅ Confirme credenciais `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`
- ✅ Veja logs do servidor para mensagens de erro

### Cliente não encontrado (4004)
- ✅ Verifique se o SIP number está cadastrado na tabela `client_sip_numbers`
- ✅ Confirme que `active = true` para o cliente
- ✅ Teste com `ClientManager.get_client_config(sip_number)`

### Worker não conecta ao Azure
- ✅ Verifique credenciais `AZURE_VOICELIVE_ENDPOINT` e `API_KEY`
- ✅ Confirme que o modelo `gpt-realtime` está disponível
- ✅ Teste em development primeiro

### Áudio não funciona (Dev)
- ✅ Instale PyAudio: `pip install pyaudio`
- ✅ Verifique dispositivos de áudio no sistema
- ✅ Use `APP_ENV=development` para áudio local

---

## 🆕 Changelog

### v2.0.0 - Multi-Tenant Refactoring
- ✅ **WebSocket Endpoint**: `/ws/audio/{sip_number}` para streaming em tempo real
- ✅ **Integração Supabase**: Configurações dinâmicas por cliente
- ✅ **Injeção de Dependência**: `VoiceAssistantWorker` aceita configuração injetada
- ✅ **Worker por Sessão**: Isolamento completo entre clientes
- ✅ **Entry Point Único**: Removido `main.py` legado da raiz
- ✅ **Arquitetura Escalável**: Suporte a centenas de clientes simultâneos

---

## 🤝 Contribuindo

1. Faça fork do projeto
2. Crie uma feature branch: `git checkout -b minha-feature`
3. Teste em todos os ambientes
4. Atualize a documentação
5. Commit suas mudanças: `git commit -am 'Adiciona nova feature'`
6. Push para a branch: `git push origin minha-feature`
7. Abra um Pull Request

---

**Sistema pronto para produção com suporte multi-tenant escalável!** 🚀

Para mais informações: `mkdocs serve` 📚
