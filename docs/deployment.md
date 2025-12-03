# 🚀 Guia de Deployment - Azure VoiceLive Agent

Este guia fornece instruções detalhadas para fazer deploy da aplicação em ambientes de **Staging** e **Production**.

---

## 📋 Índice

- [Pré-requisitos](#-pré-requisitos)
- [Deploy em Staging](#-deploy-em-staging)
- [Deploy em Production](#-deploy-em-production)
- [Checklist Pré-Deploy](#-checklist-pré-deploy)
- [Variáveis de Ambiente](#-variáveis-de-ambiente)
- [Monitoramento](#-monitoramento)
- [Rollback](#-rollback)
- [Boas Práticas](#-boas-práticas)

---

## ✅ Pré-requisitos

- [ ] Credenciais Azure para o ambiente específico (staging ou production)
- [ ] Servidor ou plataforma de deploy configurado
- [ ] Python 3.8+ instalado
- [ ] Acesso SSH/RDP ao servidor (se aplicável)
- [ ] Configuração de firewall/networking para porta da aplicação

---

## 🧪 Deploy em Staging

### 1. Preparação

```bash
# Conecte ao servidor de staging
ssh user@staging-server

# Clone o repositório
git clone <repository-url> /opt/agent-microsoft
cd /opt/agent-microsoft

# Checkout da branch de staging
git checkout staging  # ou main/develop, conforme seu workflow
```

### 2. Configuração do Ambiente

```bash
# Crie ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# Instale dependências
pip install -r requirements.txt
```

### 3. Configure Variáveis de Ambiente

**Opção A: Arquivo `.env` (menos seguro)**
```bash
cp .env.staging .env
nano .env
```

Configure:
```env
APP_ENV=staging
PORT=8001
AZURE_VOICELIVE_ENDPOINT=https://staging-resource.voicelive.azure.com/
AZURE_VOICELIVE_API_KEY=<staging-api-key>
AZURE_VOICELIVE_MODEL=gpt-realtime
```

**Opção B: Variáveis do Sistema (RECOMENDADO)**
```bash
export APP_ENV=staging
export PORT=8001
export AZURE_VOICELIVE_ENDPOINT="https://staging-resource.voicelive.azure.com/"
export AZURE_VOICELIVE_API_KEY="<staging-api-key>"
export AZURE_VOICELIVE_MODEL="gpt-realtime"
```

### 4. Teste Local

```bash
# Teste se a aplicação inicia
python main.py

# Em outro terminal, teste o health check
curl http://localhost:8001/health
# Resposta esperada: {"status":"ok","env":"staging"}
```

### 5. Configure como Serviço (Systemd)

Crie `/etc/systemd/system/voicelive-agent-staging.service`:

```ini
[Unit]
Description=Azure VoiceLive Agent - Staging
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/agent-microsoft
Environment="APP_ENV=staging"
Environment="PORT=8001"
Environment="AZURE_VOICELIVE_ENDPOINT=https://staging-resource.voicelive.azure.com/"
Environment="AZURE_VOICELIVE_API_KEY=<staging-api-key>"
ExecStart=/opt/agent-microsoft/.venv/bin/python /opt/agent-microsoft/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Ative e inicie o serviço
sudo systemctl daemon-reload
sudo systemctl enable voicelive-agent-staging
sudo systemctl start voicelive-agent-staging

# Verifique o status
sudo systemctl status voicelive-agent-staging

# Veja os logs
sudo journalctl -u voicelive-agent-staging -f
```

---

## 🏭 Deploy em Production

### 1. Preparação

```bash
# Conecte ao servidor de production
ssh user@production-server

# Clone o repositório
git clone <repository-url> /opt/agent-microsoft-prod
cd /opt/agent-microsoft-prod

# Checkout da branch de production
git checkout main  # ou production
```

### 2. Configuração do Ambiente

```bash
# Crie ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# Instale dependências
pip install -r requirements.txt
```

### 3. Configure Variáveis de Ambiente

**IMPORTANTE**: Em production, **SEMPRE** use variáveis de ambiente do sistema, **NUNCA** arquivos `.env`.

```bash
# Adicione ao /etc/environment ou use secrets manager
export APP_ENV=production
export PORT=8000
export AZURE_VOICELIVE_ENDPOINT="https://production-resource.voicelive.azure.com/"
export AZURE_VOICELIVE_API_KEY="<production-api-key>"
export AZURE_VOICELIVE_MODEL="gpt-realtime"
```

### 4. Teste de Validação

```bash
# Teste se a aplicação inicia
python main.py

# Teste health check
curl http://localhost:8000/health
# Resposta esperada: {"status":"ok","env":"production"}
```

### 5. Configure como Serviço (Systemd)

Crie `/etc/systemd/system/voicelive-agent.service`:

```ini
[Unit]
Description=Azure VoiceLive Agent - Production
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/agent-microsoft-prod
Environment="APP_ENV=production"
Environment="PORT=8000"
Environment="AZURE_VOICELIVE_ENDPOINT=https://production-resource.voicelive.azure.com/"
Environment="AZURE_VOICELIVE_API_KEY=<production-api-key>"
ExecStart=/opt/agent-microsoft-prod/.venv/bin/python /opt/agent-microsoft-prod/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
# Ative e inicie o serviço
sudo systemctl daemon-reload
sudo systemctl enable voicelive-agent
sudo systemctl start voicelive-agent

# Verifique o status
sudo systemctl status voicelive-agent

# Monitore logs
sudo journalctl -u voicelive-agent -f
```

### 6. Configure Reverse Proxy (Nginx - Opcional)

Se precisar expor via HTTPS ou domínio custom:

```nginx
server {
    listen 80;
    server_name voicelive.example.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

---

## ✅ Checklist Pré-Deploy

Antes de fazer deploy em production, verifique:

- [ ] **Testado em staging** e funcionando corretamente
- [ ] **Credenciais corretas** para o ambiente
- [ ] **Configurações do agent_config** revisadas
- [ ] **Logs monitorados** após o deploy
- [ ] **Health check** funcionando
- [ ] **Backup** da versão anterior disponível
- [ ] **Plano de rollback** definido
- [ ] **Firewall/Security Groups** configurados
- [ ] **Monitoring/Alerting** configurado
- [ ] **Documentação** atualizada

---

## 🔧 Variáveis de Ambiente

### Obrigatórias

| Variável | Descrição | Exemplo |
|-----------|-----------|---------|
| `APP_ENV` | Ambiente (`development`, `staging`, `production`) | `production` |
| `AZURE_VOICELIVE_ENDPOINT` | Endpoint do Azure VoiceLive | `https://resource.voicelive.azure.com/` |
| `AZURE_VOICELIVE_API_KEY` | Chave de API do Azure | `abc123...` |

### Opcionais

| Variável | Descrição | Padrão |
|-----------|-----------|--------|
| `PORT` | Porta do servidor | `8000` |
| `AZURE_VOICELIVE_MODEL` | Modelo a usar | `gpt-realtime` |
| `AZURE_VOICELIVE_VOICE` | Voz padrão | `en-US-Andrew:DragonHDLatestNeural` |

---

## 📊 Monitoramento

### Logs

```bash
# Ver logs em tempo real
sudo journalctl -u voicelive-agent -f

# Ver últimas 100 linhas
sudo journalctl -u voicelive-agent -n 100

# Filtrar por período
sudo journalctl -u voicelive-agent --since "1 hour ago"
```

### Health Check

Configure monitoramento externo (Pingdom, UptimeRobot, etc.) para:
- URL: `http://your-server:8000/health`
- Intervalo: 1-5 minutos
- Alerta se status != 200

### Métricas Importantes

- Taxa de requisições
- Latência de resposta
- Erros 5xx
- Uso de CPU/Memória
- Conexões Azure VoiceLive

---

## ⏮️ Rollback

### Rollback Rápido

```bash
# Pare o serviço
sudo systemctl stop voicelive-agent

# Volte para versão anterior
cd /opt/agent-microsoft-prod
git checkout <previous-commit-hash>

# Reinicie
sudo systemctl start voicelive-agent

# Verifique
sudo systemctl status voicelive-agent
curl http://localhost:8000/health
```

### Rollback com Backup

Se mantém backup da pasta:

```bash
# Pare o serviço
sudo systemctl stop voicelive-agent

# Restaure backup
sudo rm -rf /opt/agent-microsoft-prod
sudo cp -r /opt/backups/agent-microsoft-prod-YYYY-MM-DD /opt/agent-microsoft-prod

# Reinicie
sudo systemctl start voicelive-agent
```

---

## 🎯 Boas Práticas

### Segurança

1. **Nunca commite arquivos `.env` com credenciais reais**
2. **Use secrets managers** (AWS Secrets Manager, Azure Key Vault) em production
3. **Rotacione chaves de API** regularmente
4. **Restrinja acesso SSH** ao servidor

### Deploy

1. **Sempre teste em staging primeiro**
2. **Faça deploy em horários de baixo tráfego**
3. **Monitore logs por pelo menos 30 minutos após deploy**
4. **Mantenha backups antes de cada deploy**
5. **Documente todas as mudanças**

### Configuração

1. **Use `agent_config.production.json`** específico para production
2. **Configure logs de WARNING** apenas em production
3. **Desabilite hot-reload** em production
4. **Use processo supervisor** (systemd, supervisor, PM2)

### Monitoramento

1. **Configure alertas** para erros críticos
2. **Monitore usage da API Azure** para controle de custos
3. ** Faça health checks regulares**
4. **Mantenha logs por pelo menos 30 dias**

---

## 🆘 Suporte

Em caso de problemas:

1. Verifique os logs: `sudo journalctl -u voicelive-agent -f`
2. Teste o health check: `curl http://localhost:8000/health`
3. Valide as variáveis de ambiente
4. Consulte o [README.md](README.md) para troubleshooting
5. Contate a equipe de desenvolvimento

---

**Boa sorte com seu deploy! 🚀**
