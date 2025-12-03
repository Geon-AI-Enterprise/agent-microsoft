# Principais Features

O Geon AI - Voice Agent foi desenvolvido com foco em robustez, flexibilidade e facilidade de uso. Conheça todas as features principais do sistema.

## 🌍 Multi-Ambiente

**Descrição**: Suporte completo para três ambientes distintos com configurações específicas e comportamentos otimizados.

### Ambientes Disponíveis

=== "Development"
    **Características**:
    
    - 🎤 Áudio local habilitado (PyAudio)
    - 🔄 Hot-reload automático
    - 📊 Logs DEBUG (muito detalhados)
    - 🎨 Logs coloridos com emojis
    - 📁 Arquivo: `agent_config.json`
    - 🔌 Porta: 8000
    
    **Quando usar**: Desenvolvimento local, debugging, testes com microfone

=== "Staging"
    **Características**:
    
    - 🔌 Modo API (sem áudio local)
    - 📊 Logs INFO (moderados)
    - ⚠️  Stacktraces resumidos
    - 📁 Arquivo: `agent_config.staging.json`
    - 🔌 Porta: 8001
    
    **Quando usar**: Homologação, testes de integração, QA

=== "Production"
    **Características**:
    
    - 🔌 Modo API otimizado
    - 📊 Logs WARNING (apenas essenciais)
    - ❌ Sem stacktraces
    - 🚀 Performance otimizada
    - 📁 Arquivo: `agent_config.production.json`
    - 🔌 Porta: 8000
    
    **Quando usar**: Produção, ambiente final

### Alternando Entre Ambientes

```bash
# Method 1: Arquivo .env
copy .env.staging .env
python main.py

# Method 2: Variável de ambiente (recomendado)
set APP_ENV=staging
python main.py
```

---

## 📝 Sistema de Logs Amigável

**Descrição**: Logging limpo, legível e configurado por ambiente, eliminando ruído de logs verbosos.

### Características

- 🎨 **Cores e Emojis** (development): Logs coloridos para facilitar visualização
- 🔇 **Filtro Azure SDK**: Reduz drasticamente logs verbosos do Azure
- 💬 **Mensagens Amigáveis**: Erros convertidos em mensagens acionáveis
- 📊 **Verbosidade por Ambiente**: DEBUG → INFO → WARNING
- ❌ **Stacktraces Controlados**: Exibidos apenas quando necessário

### Exemplo de Output

**Development**:
```
🔍 2025-12-03 01:00:00 | DEBUG    | __main__ | Detalhes de debug
ℹ️  2025-12-03 01:00:01 | INFO     | __main__ | Iniciando aplicação
⚠️  2025-12-03 01:00:02 | WARNING  | __main__ | Aviso importante
❌ 2025-12-03 01:00:03 | ERROR    | __main__ | Erro encontrado
```

**Production**:
```
[2025-12-03 01:00:00] Iniciando aplicação
[2025-12-03 01:00:05] Erro: verifique suas credenciais
```

### Mensagens de Erro Amigáveis

| Erro Técnico | Mensagem Amigável |
|--------------|-------------------|
| `ConnectionError` | ❌ Não foi possível conectar ao servidor Azure<br>💡 Verifique sua conexão de internet |
| `AuthenticationError` | ❌ Falha na autenticação com Azure<br>💡 Verifique AZURE_VOICELIVE_API_KEY no .env |
| `FileNotFoundError` | ❌ Arquivo não encontrado<br>💡 Verifique se o arquivo existe |

---

## ⚙️ Configuração Flexível

**Descrição**: Sistema de configuração robusto e validado automaticamente.

### Níveis de Configuração

1. **Variáveis de Ambiente** (`.env`)
   - Credenciais Azure
   - Configurações de ambiente
   - Porta do servidor

2. **Agent Config** (`agent_config.json`)
   - Instruções do agente
   - Voz e modelo
   - Parâmetros de detecção de turno
   - Configurações de áudio

3. **Settings Validados** (`settings.py`)
   - Validação automática com Pydantic
   - Valores padrão seguros
   - Métodos helpers por ambiente

### Auto-seleção de Configuração

O sistema seleciona automaticamente o arquivo correto baseado no ambiente:

```python
Development → agent_config.json
Staging     → agent_config.staging.json (fallback: agent_config.json)
Production  → agent_config.production.json (fallback: agent_config.json)
```

---

## 🎤 Processamento de Áudio (Development)

**Descrição**: Captura e reprodução de áudio em tempo real para desenvolvimento local.

### Features de Áudio

- **Captura de Microfone**: Gravação em tempo real com PyAudio
- **Cancelamento de Eco**: Evita feedback durante conversação
- **Filtro de Ruído**: Gate de ruído configurável
- **Playback Otimizado**: Reprodução suave e sincronizada
- **Latência Reduzida**: Chunks de 40ms para baixa latência

### Configurações de Áudio

```python
# main.py - AudioProcessor
chunk_size = 960  # 40ms @ 24kHz
mic_threshold = 200  # Limiar de ruído
rate = 24000  # Taxa de amostragem
```

!!! tip "Dica"
    Ajuste `mic_threshold` se sua voz estiver sendo cortada (diminua) ou se houver muito ruído (aumente).

---

## 🔧 Tratamento de Erros Robusto

**Descrição**: Sistema completo de tratamento de erros com mensagens amigáveis.

### Pontos de Tratamento

1. **Conexão Azure** (`connect()`)
   - Falhas de autenticação
   - Problemas de rede
   - Credenciais inválidas

2. **Configuração de Sessão** (`_setup_session()`)
   - Erros de configuração
   - Parâmetros inválidos
   - Problemas de voice/modelo

3. **Processamento de Eventos** (`_process_events()`)
   - Erros de comunicação
   - Timeout de conexão
   - Problemas de streaming

### Comportamento por Ambiente

=== "Development"
    ```
    ❌ Erro ao configurar sessão
    ❌ Falha na autenticação com Azure
    💡 Verifique AZURE_VOICELIVE_API_KEY no .env
    
    🔍 Detalhes técnicos:
    Traceback (most recent call last):
      File "main.py", line 230, in _setup_session
        ...
    AuthenticationError: Invalid API key
    ```

=== "Production"
    ```
    [2025-12-03 01:00:00] Erro ao configurar sessão
    [2025-12-03 01:00:00] Falha na autenticação com Azure
    [2025-12-03 01:00:00] Verifique AZURE_VOICELIVE_API_KEY no .env
    ```

---

## 🚀 Hot-Reload (Development)

**Descrição**: Reinicialização automática ao modificar código em development.

### Como Funciona

- Detecta mudanças em arquivos `.py`
- Reinicia servidor automaticamente
- Mantém configurações
- Acelera desenvolvimento

### Ativação

Ativo apenas em `APP_ENV=development`:

```python
# main.py
enable_reload = settings.is_development()
uvicorn.run(..., reload=enable_reload)
```

---

## ✅ Validação Automática

**Descrição**: Validações robustas em configurações e entradas.

### Validações Implementadas

1. **APP_ENV Validation**
   ```python
   # Aceita apenas: development, staging, production
   @field_validator('APP_ENV')
   def validate_environment(cls, v: str) -> str:
       valid_envs = ['development', 'staging', 'production']
       if v not in valid_envs:
           raise ValueError(...)
   ```

2. **Variáveis Obrigatórias**
   - `AZURE_VOICELIVE_ENDPOINT`
   - `AZURE_VOICELIVE_API_KEY`

3. **Configurações de Agente**
   - Voz disponível
   - Modelo válido
   - Parâmetros turn_detection

---

## 📊 Health Check API

**Descrição**: Endpoint para monitoramento e verificação de saúde.

### Endpoint

```http
GET /health
```

### Resposta

```json
{
  "status": "ok",
  "env": "production"
}
```

### Uso

```bash
# Verificar status
curl http://localhost:8000/health

# Monitoramento automatizado
while true; do 
  curl http://localhost:8000/health
  sleep 30
done
```

---

## 🔐 Segurança

**Descrição**: Boas práticas de segurança implementadas.

### Medidas de Segurança

- ✅ Credenciais via variáveis de ambiente
- ✅ `.env` files gitignored
- ✅ Validação de entrada
- ✅ Sem logs de credenciais
- ✅ Conexões HTTPS Azure

### Recomendações

!!! warning "Importante"
    - Nunca commite arquivos `.env` com credenciais reais
    - Use secrets managers em production
    - Rotacione chaves regularmente
    - Restrinja acesso SSH/RDP

---

## 📈 Performance

**Descrição**: Otimizações para máxima performance.

### Otimizações Implementadas

- **Assíncrono**: FastAPI + asyncio
- **Chunks Pequenos**: 40ms para baixa latência
- **Logs Filtrados**: Reduz overhead
- **Conexão Persistente**: WebSocket mantido
- **Cache de Settings**: `@lru_cache`

### Métricas Esperadas

| Métrica | Valor |
|---------|-------|
| Latência Áudio | ~40-60ms |
| Tempo Resposta API | < 100ms |
| Uso CPU (Idle) | < 5% |
| Uso RAM | ~100-200MB |

---

Para mais detalhes sobre cada feature, consulte as seções específicas da documentação.
