# Guia de Desenvolvimento

Bem-vindo ao guia de desenvolvimento do Azure VoiceLive Agent! Este guia vai te ajudar a começar a desenvolver e customizar o sistema.

## 🛠️ Setup do Ambiente de Desenvolvimento

### Requisitos

- Python 3.8+
- Git
- Editor de código (VS Code recomendado)
- Azure Account com acesso ao VoiceLive API

### Instalação

1. **Clone e Configure**
   ```bash
   git clone <repository-url>
   cd agent-microsoft
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configuração**
   ```bash
   copy .env.example .env
   # Configure suas credenciais
   ```

3. **VS Code (Opcional)**
   ```bash
   code .
   ```

   Extensões recomendadas:
   - Python
   - Pylance
   - Python Docstring Generator

---

## 📁 Estrutura do Código

### Arquivos Principais

```
agent-microsoft/
├── main.py                    # ⭐ Aplicação principal
│   ├── AudioProcessor         # Processamento de áudio
│   ├── VoiceAssistantWorker   # Core do assistente
│   └── FastAPI app            # Servidor web
│
├── settings.py                # ⚙️ Configurações
│   └── Settings               # Validação e helpers
│
├── agent_config_loader.py     # 📝 Config do agente
│   └── AgentConfig            # Carregamento de config
│
└── logger_config.py           # 📊 Sistema de logs
    ├── CustomFormatter        # Formatação de logs
    ├── AzureLogFilter         # Filtro Azure SDK
    └── setup_logging()        # Setup principal
```

### Fluxo de Execução

```
main.py inicializa
    ↓
Settings carregados e validados
    ↓
Logger configurado
    ↓
VoiceAssistantWorker criado
    ↓
FastAPI app inicia (lifespan)
    ↓
Worker conecta ao Azure
    ↓
Session configurada
    ↓
Event loop processa eventos
```

---

## 🔧 Principais Classes e Métodos

### VoiceAssistantWorker

**Propósito**: Gerencia a conexão e interação com Azure VoiceLive

**Métodos Principais**:

```python
async def connect(self)
    """Conecta ao Azure VoiceLive"""
    # 1. Cria credenciais
    # 2. Estabelece conexão WebSocket
    # 3. Inicia AudioProcessor (se development)
    # 4. Configura sessão
    # 5. Inicia event loop

async def _setup_session(self)
    """Configura sessão do agente"""
    # 1. Carrega configurações do JSON
    # 2. Cria ServerVAD com turn_detection
    # 3. Configura RequestSession
    # 4. Envia para Azure

async def _process_events(self)
    """Loop principal de eventos"""
    # 1. Escuta eventos do Azure
    # 2. Processa cada tipo de evento
    # 3. Atualiza AudioProcessor
    # 4. Trata erros
```

### AudioProcessor

**Propósito**: Captura e reprodução de áudio (development only)

**Métodos Principais**:

```python
def start_capture(self)
    """Inicia captura do microfone"""
    # 1. Cria stream PyAudio
    # 2. Callback processa áudio
    # 3. Filtro de eco
    # 4. Filtro de ruído
    # 5. Envia para Azure

def start_playback(self)
    """Inicia reprodução de áudio"""
    # 1. Cria stream de output
    # 2. Consome playback_queue
    # 3. Reproduz nos alto-falantes

def queue_audio(self, data: bytes)
    """Adiciona áudio à fila de reprodução"""
```

---

## 🐛 Debugging

### Logs Detalhados

Em development, ative logs DEBUG:

```python
# Já ativo por padrão em development
# settings.py
def get_log_level(self) -> str:
    if self.is_development():
        return "DEBUG"  # ← Muito detalhado
```

### Breakpoints

Use breakpoints nos pontos críticos:

```python
# main.py
async def connect(self):
    breakpoint()  # ← Para aqui
    credential = AzureKeyCredential(self.settings.AZURE_VOICELIVE_API_KEY)
```

### Debug com VS Code

`.vscode/launch.json`:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "main:app",
        "--reload"
      ],
      "jinja": true,
      "justMyCode": true
    }
  ]
}
```

---

## 🧪 Testes

### Teste Manual

```bash
# Development
python main.py

# Staging
set APP_ENV=staging
python main.py

# Production
set APP_ENV=production
python main.py
```

### Teste Automatizado

```bash
# Testa todos os ambientes
python test_environments.py
```

### Health Check

```bash
curl http://localhost:8000/health
```

---

## 📝 Boas Práticas

### 1. Sempre Use Ambientes

```bash
# ✅ BOM
set APP_ENV=development
python main.py

# ❌ RUIM
# Modificar código para mudar comportamento
```

### 2. Validação de Entrada

```python
# ✅ BOM
@field_validator('APP_ENV')
def validate_environment(cls, v: str) -> str:
    valid_envs = ['development', 'staging', 'production']
    if v not in valid_envs:
        raise ValueError(...)
    return v

# ❌ RUIM
# Aceitar qualquer valor sem validação
```

### 3. Tratamento de Erros

```python
# ✅ BOM
try:
    result = risky_operation()
except SpecificException as e:
    logger.error(f"Operação falhou: {e}")
    # Trate o erro apropriadamente

# ❌ RUIM
try:
    result = risky_operation()
except:  # Não use except genérico
    pass  # Não ignore erros silenciosamente
```

### 4. Logging Informativo

```python
# ✅ BOM
logger.info(f"Conectando ao modelo: {model_name}")
logger.error(f"Falha ao conectar: {error_msg}")

# ❌ RUIM
logger.info("Conectando")  # Pouca informação
print("Erro")  # Use logger, não print
```

---

## 🔄 Workflow de Desenvolvimento

### 1. Feature Nova

```bash
# 1. Crie branch
git checkout -b feature/nova-feature

# 2. Desenvolva
# ... código ...

# 3. Teste localmente
python main.py
python test_environments.py

# 4. Commit
git add .
git commit -m "feat: adiciona nova feature"

# 5. Push e PR
git push origin feature/nova-feature
```

### 2. Bug Fix

```bash
# 1. Crie branch
git checkout -b fix/corrige-bug

# 2. Corrija
# ... código ...

# 3. Teste
python main.py

# 4. Commit
git commit -m "fix: corrige bug X"

# 5. Push e PR
git push origin fix/corrige-bug
```

---

## 📚 Recursos

- [Pontos de Customização](customization.md) - Onde modificar
- **Arquitetura** - Como funciona
- **API Reference** - Referência completa
- **Troubleshooting** - Resolução de problemas

---

## 🎓 Próximos Passos

1. Explore [Pontos de Customização](customization.md)
2. Leia **Arquitetura**
3. Faça sua primeira customização
4. Teste em todos os ambientes
5. Faça deploy!
