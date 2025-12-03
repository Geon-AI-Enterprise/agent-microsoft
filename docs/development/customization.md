# Pontos de Customização

Este guia documenta todos os pontos principais onde você pode customizar e adaptar o Azure VoiceLive Agent para suas necessidades.

## 🎯 Visão Geral

O sistema foi projetado para ser altamente customizável sem necessidade de modificar a arquitetura core. Aqui estão os principais pontos de extensão.

---

## 1. Configuração do Agente

**Arquivo**: `agent_config.json` (e variantes por ambiente)  
**Dificuldade**: ⭐ Fácil

### O Que Pode Ser Customizado

```json
{
  "model": "gpt-realtime",              // Modelo a usar
  "voice": "en-US-Andrew:...",           // Voz do assistente
  "temperature": 0.7,                    // Criatividade (0.0-1.0)
  "max_tokens": 800,                     // Máximo de tokens
  "turn_detection": {                   // Detecção de turnos
    "threshold": 0.4,                    // Sensibilidade (0.0-1.0)
    "silence_duration_ms": 250          // Tempo de silêncio
  },
  "instructions": "Você é..."          // Prompt do sistema
}
```

### Como Customizar

1. Edite `agent_config.json` para development
2. Crie `agent_config.staging.json` para staging
3. Crie `agent_config.production.json` para production

### Principais Parâmetros

#### Voice

```json
// Vozes disponíveis em português
"voice": "pt-BR-FranciscaNeural"        // Voz feminina PT-BR
"voice": "pt-BR-AntonioNeural"          // Voz masculina PT-BR

// Inglês
"voice": "en-US-Andrew:DragonHDLatestNeural"
"voice": "en-US-Jenny:DragonHDLatestNeural"
```

#### Temperature

| Valor | Comportamento |
|-------|---------------|
| 0.0-0.3 | Muito conservador, respostas previsíveis |
| 0.4-0.7 | **Balanceado** (recomendado) |
| 0.8-1.0 | Criativo, mais variação |

#### Turn Detection

```json
{
  "threshold": 0.4,              // Menor = mais sensível
  "prefix_padding_ms": 300,      // Buffer antes da fala
  "silence_duration_ms": 250     // Tempo para considerar fim
}
```

!!! tip "Ajuste Fino"
    - Se o agente **interrompe muito**: aumente `silence_duration_ms`
    - Se demora para **responder**: diminua `silence_duration_ms`
    - Se não **detecta** sua voz: diminua `threshold`

---

## 2. Instruções do Sistema (Prompt)

**Arquivo**: `agent_config.json` → `instructions`  
**Dificuldade**: ⭐⭐ Médio

### Como Customizar

Edite o campo `instructions` no agent_config:

```json
{
  "instructions": "Você é a Lia, uma consultora especialista..."
}
```

### Estrutura Recomendada

```
1. Identidade
   - Quem é o agente
   - Qual sua função
   - Tom de voz

2. Conhecimento Base
   - Fontes de informação
   - Limitações
   - O que pode/não pode fazer

3. Fluxo de Conversa
   - Como iniciar
   - Como conduzir
   - Como encerrar

4. Regras de Comportamento
   - Uma pergunta por vez
   - Ser empático
   - Confirmar entendimento
```

### Exemplo Customizado

```json
{
  "instructions": "Você é o Alex, um assistente técnico especializado em suporte IT.\n\n**Identidade**:\n- Nome: Alex\n- Função: Suporte técnico de TI\n- Tom: Profissional mas amigável\n\n**Como atender**:\n1. Cumprimente o usuário\n2. Pergunte qual o problema\n3. Diagnóstico passo a passo\n4. Resolva ou escalone\n\n**Regras**:\n- Sempre confirme  se resolveu\n- Uma pergunta por vez\n- Explique termos técnicos\n- Seja paciente"
}
```

---

## 3. Configurações de Áudio

**Arquivo**: `main.py` → `AudioProcessor.__init__`  
**Dificuldade**: ⭐⭐ Médio

### Parâmetros Customizáveis

```python
class AudioProcessor:
    def __init__(self, connection):
        # Taxa de amostragem
        self.rate = 24000  # 24kHz (padrão Azure)
        
        # Tamanho do chunk (latência)
        self.chunk_size = 960  # 40ms
        
        # Limiar de ruído (noise gate)
        self.mic_threshold = 200  # Ajuste conforme ambiente
```

### Como Ajustar

#### Latência mais Baixa
```python
self.chunk_size = 480  # 20ms - menor latência, mais CPU
```

#### Latência mais Alta (mais estável)
```python
self.chunk_size = 1920  # 80ms - mais estável, maior latência
```

#### Filtro de Ruído
```python
# Ambiente silencioso
self.mic_threshold = 150

# Ambiente barulhento
self.mic_threshold = 400
```

---

## 4. Sistema de Logging

**Arquivo**: `logger_config.py`  
**Dificuldade**: ⭐⭐⭐ Avançado

### Customizar Formatação

```python
class CustomFormatter(logging.Formatter):
    # Modificar emojis
    EMOJI_MAP = {
        'DEBUG': '🐛',     # Altere aqui
        'INFO': '✅',      # Altere aqui
        'WARNING': '⚠️',   # Altere aqui
        'ERROR': '🔥',     # Altere aqui
    }
    
    # Modificar cores
    COLOR_MAP = {
        'DEBUG': Colors.MAGENTA,  # Nova cor
        'INFO': Colors.GREEN,     # Nova cor
        ...
    }
```

### Adicionar Novo Formato

```python
# Formato JSON para produção
class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            'timestamp': record.created,
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.module
        })
```

### Customizar Mensagens de Erro

```python
# logger_config.py - get_user_friendly_error()
friendly_messages = {
    'CustomError': '💡 Sua mensagem customizada aqui',
    'AnotherError': '🔧 Outra mensagem amigável',
}
```

---

## 5. Processamento de Eventos

**Arquivo**: `main.py` → `VoiceAssistantWorker._process_events`  
**Dificuldade**: ⭐⭐⭐ Avançado

### Adicionar Novo Tipo de Evento

```python
async def _process_events(self):
    try:
        async for event in self.connection:
            # Eventos existentes...
            
            # ADICIONE SEU EVENTO CUSTOMIZADO AQUI
            elif event.type == ServerEventType.CUSTOM_EVENT:
                self.handle_custom_event(event)
```

### Exemplo: Logging de Transcrição

```python
elif event.type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE:
    transcript = event.transcript
    logger.info(f"🗣️  Transcrição: {transcript}")
    # Salva em banco de dados
    # self.save_transcript(transcript)
```

### Exemplo: Detecção de Intenção

```python
elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
    # Detecta intenção do usuário
    intent = self.detect_intent(event)
    if intent == 'agendar':
        self.show_calendar_ui()
```

---

## 6. Variáveis de Ambiente

**Arquivo**: `.env` (por ambiente)  
**Dificuldade**: ⭐ Fácil

### Adicionar Nova Variável

1. **Defina em `settings.py`**:
   ```python
   class Settings(BaseSettings):
       # Nova variável
       CUSTOM_API_URL: str = "https://default.url"
       CUSTOM_TIMEOUT: int = 30
   ```

2. **Adicione ao `.env.example`**:
   ```env
   # Custom API Configuration
   CUSTOM_API_URL=https://your-api.com
   CUSTOM_TIMEOUT=60
   ```

3. **Use no código**:
   ```python
   from settings import get_settings
   settings = get_settings()
   
   response = requests.get(
       settings.CUSTOM_API_URL,
       timeout=settings.CUSTOM_TIMEOUT
   )
   ```

---

## 7. Endpoints da API

**Arquivo**: `main.py` (após linha 287)  
**Dificuldade**: ⭐⭐ Médio

### Adicionar Novo Endpoint

```python
# Após @app.get("/health")

@app.get("/status")
def status():
    """Endpoint customizado de status"""
    return {
        "status": "running",
        "version": "1.0.0",
        "environment": settings.APP_ENV,
        "connections": worker.connection is not None
    }

@app.post("/send-message")
async def send_message(message: str):
    """Enviar mensagem para o agente"""
    # Implementar lógica aqui
    return {"received": message}
```

---

## 8. Configurações por Ambiente

**Arquivo**: `settings.py`  
**Dificuldade**: ⭐⭐ Médio

### Adicionar Comportamento Específico

```python
class Settings(BaseSettings):
    def get_max_connections(self) -> int:
        """Retorna número máximo de conexões por ambiente"""
        if self.is_development():
            return 5
        elif self.is_staging():
            return 50
        else:  # production
            return 500
    
    def get_cache_ttl(self) -> int:
        """TTL do cache por ambiente"""
        if self.is_development():
            return 60  # 1 minuto
        elif self.is_staging():
            return 300  # 5 minutos
        else:  # production
            return 3600  # 1 hora
```

---

## 9. Tratamento de Erros Customizado

**Arquivo**: `main.py` → métodos com `try/except`  
**Dificuldade**: ⭐⭐⭐ Avançado

### Adicionar Lógica de Retry

```python
async def connect(self):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Código de conexão...
            break
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Tentativa {attempt + 1} falhou, tentando novamente...")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                # Última tentativa falhou
                error_msg = get_user_friendly_error(e, self.settings.APP_ENV)
                logger.error(error_msg)
                raise
```

### Adicionar Métricas de Erro

```python
from collections import Counter

class VoiceAssistantWorker:
    def __init__(self):
        ...
        self.error_counts = Counter()
    
    async def _process_events(self):
        try:
            ...
        except Exception as e:
            # Incrementa contador
            error_type = type(e).__name__
            self.error_counts[error_type] += 1
            
            # Log se muitos erros
            if self.error_counts[error_type] > 10:
                logger.critical(f"Muitos erros do tipo {error_type}!")
```

---

## 10. Integração com Serviços Externos

**Arquivo**: Novo módulo (ex: `integrations.py`)  
**Dificuldade**: ⭐⭐⭐⭐ Expert

### Criar Integração com CRM

```python
# integrations.py
import requests

class CRMIntegration:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://your-crm.com/api"
    
    def create_lead(self, name: str, phone: str):
        """Cria lead no CRM"""
        response = requests.post(
            f"{self.base_url}/leads",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"name": name, "phone": phone}
        )
        return response.json()

# main.py - usar a integração
class VoiceAssistantWorker:
    def __init__(self):
        ...
        self.crm = CRMIntegration(settings.CRM_API_KEY)
    
    async def _process_events(self):
        # Quando detectar intenção de agendamento
        if intent == 'schedule':
            self.crm.create_lead(customer_name, customer_phone)
```

---

## 📚 Recursos Adicionais

- **Variáveis de Ambiente**
- **Agent Config**
- [Guia de Desenvolvimento](guide.md)
- **Arquitetura**

---

!!! warning "Importante"
    Ao fazer customizações, sempre:
    
    1. Teste em `development` primeiro
    2. Valide em `staging`
    3. Faça backup antes de deploy em `production`
    4. Documente suas mudanças
    5. Use controle de versão (Git)
