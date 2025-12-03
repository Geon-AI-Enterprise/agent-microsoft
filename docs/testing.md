# Guia de Testes - Multi-Environment Setup

## 🧪 Como Testar a Implementação

### Teste Automático (RECOMENDADO)

Execute o script de testes automatizado:

```bash
python test_environments.py
```

Este script vai testar automaticamente:
- ✅ Validação do APP_ENV em cada ambiente
- ✅ Métodos helpers (is_development, is_staging, is_production)
- ✅ Carregamento correto do AgentConfig por ambiente
- ✅ Níveis de log apropriados
- ✅ Porta correta por ambiente

---

### Testes Manuais por Ambiente

#### 1️⃣ Teste Development

```bash
# Configurar ambiente
set APP_ENV=development

# Testar settings
python -c "from settings import get_settings; s = get_settings(); print(f'Env: {s.APP_ENV}, Port: {s.PORT}, Log: {s.get_log_level()}, IsDev: {s.is_development()}')"

# Resultado esperado:
# Env: development, Port: 8000, Log: DEBUG, IsDev: True

# Testar AgentConfig
python -c "from agent_config_loader import AgentConfig; c = AgentConfig('agent_config.json', env='development'); print(f'Config: {c.config_path}')"

# Resultado esperado:
# Config: agent_config.json

# Iniciar aplicação
python main.py
```

**Validações Development**:
- [ ] Log mostra: "🚀 Iniciando aplicação em modo: DEVELOPMENT"
- [ ] Logs muito detalhados (DEBUG level)
- [ ] Hot-reload está ativo
- [ ] PyAudio iniciado (se instalado): "🎤 Captura iniciada"
- [ ] Health check: `http://localhost:8000/health` retorna `{"status":"ok","env":"development"}`

---

#### 2️⃣ Teste Staging

```bash
# Configurar ambiente
set APP_ENV=staging

# Testar settings
python -c "from settings import get_settings; s = get_settings(); print(f'Env: {s.APP_ENV}, Port: {s.PORT}, Log: {s.get_log_level()}, IsStg: {s.is_staging()}')"

# Resultado esperado:
# Env: staging, Port: 8001, Log: INFO, IsStg: True

# Testar AgentConfig
python -c "from agent_config_loader import AgentConfig; c = AgentConfig('agent_config.json', env='staging'); print(f'Config: {c.config_path}')"

# Resultado esperado:
# Config: agent_config.staging.json (ou agent_config.json se staging.json não existir)

# Iniciar aplicação
python main.py
```

**Validações Staging**:
- [ ] Log mostra: "🚀 Iniciando aplicação em modo: STAGING"
- [ ] Logs moderados (INFO level)
- [ ] Hot-reload está DESATIVADO
- [ ] Log mostra: "ℹ️ Áudio local desabilitado (modo API)"
- [ ] Worker conecta normalmente: "🔌 Conectando ao modelo..."
- [ ] Health check: `http://localhost:8001/health` retorna `{"status":"ok","env":"staging"}`

---

#### 3️⃣ Teste Production

```bash
# Configurar ambiente
set APP_ENV=production

# Testar settings
python -c "from settings import get_settings; s = get_settings(); print(f'Env: {s.APP_ENV}, Port: {s.PORT}, Log: {s.get_log_level()}, IsProd: {s.is_production()}')"

# Resultado esperado:
# Env: production, Port: 8000, Log: WARNING, IsProd: True

# Testar AgentConfig
python -c "from agent_config_loader import AgentConfig; c = AgentConfig('agent_config.json', env='production'); print(f'Config: {c.config_path}')"

# Resultado esperado:
# Config: agent_config.production.json (ou agent_config.json se production.json não existir)

# Iniciar aplicação
python main.py
```

**Validações Production**:
- [ ] Log mostra: "🚀 Iniciando aplicação em modo: PRODUCTION"
- [ ] Apenas logs essenciais (WARNING level ou superior)
- [ ] Hot-reload está DESATIVADO
- [ ] Log mostra: "ℹ️ Áudio local desabilitado (modo API)"
- [ ] Worker conecta normalmente: "🔌 Conectando ao modelo..."
- [ ] Health check: `http://localhost:8000/health` retorna `{"status":"ok","env":"production"}`

---

## 🔍 Testes Específicos

### Teste de Validação de APP_ENV

```bash
# Tentar valor inválido (deve dar erro)
set APP_ENV=invalid
python -c "from settings import get_settings; get_settings()"

# Resultado esperado: ValidationError
```

### Teste de Carregamento de Config

```bash
# Verificar qual arquivo é carregado em cada ambiente
python -c "
from agent_config_loader import AgentConfig
for env in ['development', 'staging', 'production']:
    c = AgentConfig('agent_config.json', env=env)
    print(f'{env}: {c.config_path}')
"
```

### Teste de Worker em Todos os Ambientes

```bash
# Este é o teste CRÍTICO que prova o bug foi corrigido
# O worker DEVE conectar em TODOS os ambientes agora

# Development
set APP_ENV=development
python main.py
# Espere ver: "🔌 Conectando ao modelo..."

# Staging
set APP_ENV=staging
python main.py
# Espere ver: "🔌 Conectando ao modelo..." ✅ (antes não conectava!)

# Production
set APP_ENV=production
python main.py
# Espere ver: "🔌 Conectando ao modelo..." ✅ (antes não conectava!)
```

---

## 📊 Checklist Final de Validação

### Funcionalidades Gerais
- [ ] Aplicação inicia sem erros em todos os 3 ambientes
- [ ] Health check funciona em todos os ambientes
- [ ] Logs aparecem nos níveis corretos (DEBUG/INFO/WARNING)
- [ ] Worker conecta em TODOS os ambientes (não só development)

### Development
- [ ] PyAudio funciona (se instalado)
- [ ] Hot-reload está ativo
- [ ] Porta 8000
- [ ] Logs detalhados

### Staging
- [ ] Áudio local desabilitado
- [ ] Hot-reload desabilitado
- [ ] Porta 8001
- [ ] Logs moderados
- [ ] Usa agent_config.staging.json (se existir)

### Production
- [ ] Áudio local desabilitado
- [ ] Hot-reload desabilitado
- [ ] Porta 8000
- [ ] Apenas logs essenciais
- [ ] Usa agent_config.production.json (se existir)

---

## 🐛 Troubleshooting

### Erro: "ValidationError for Settings"
**Solução**: Verifique que o arquivo `.env` tem todas as variáveis obrigatórias

### Erro: "ModuleNotFoundError"
**Solução**: Execute `pip install -r requirements.txt`

### Worker não conecta
**Solução**: Verifique as credenciais Azure no `.env`

### Configuração antiga sendo usada
**Solução**: Limpe o cache do Python:
```bash
python -c "import sys; [sys.modules.pop(m) for m in list(sys.modules.keys()) if m.startswith('settings') or m.startswith('agent')]"
```

---

## ✅ Resultado Esperado

Se tudo estiver funcionando corretamente:

1. **Script automático** deve mostrar: "✅ TODOS OS TESTES PASSARAM!"
2. **Aplicação inicia** em todos os 3 ambientes sem erros
3. **Worker conecta** em todos os ambientes
4. **Logs** aparecem nos níveis corretos
5. **Health checks** retornam status correto

---

**Boa sorte com os testes! 🚀**
