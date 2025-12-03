# 🚀 Guia de Deploy no Easy Panel

Este guia completo mostra como fazer deploy do **Azure VoiceLive Agent** no Easy Panel.

---

## 📋 Pré-requisitos

Antes de começar, certifique-se de ter:

- ✅ Conta no [Easy Panel](https://easypanel.io/)
- ✅ Servidor configurado no Easy Panel
- ✅ Credenciais da Azure (OpenAI + VoiceLive)
- ✅ Credenciais do Supabase
- ✅ Repositório Git (GitHub, GitLab, Bitbucket)

---

## 🎯 Opções de Deploy

O Easy Panel oferece 3 formas de deploy. Escolha a que melhor se adapta ao seu workflow:

### Opção 1: Deploy via GitHub/GitLab (Recomendado)
- ✅ Deploy automático a cada push
- ✅ Mais fácil para rollback
- ✅ Melhor para trabalho em equipe

### Opção 2: Deploy via Docker Registry
- ✅ Controle total sobre a imagem
- ✅ Ideal para múltiplos ambientes

### Opção 3: Deploy Manual via Dockerfile
- ✅ Bom para testes iniciais
- ⚠️ Menos automatizado

---

## 🔧 Método 1: Deploy via Git (Recomendado)

### Passo 1: Preparar o Repositório

1. **Envie seu código para GitHub/GitLab**:
```bash
# Se ainda não tem repositório Git
git init
git add .
git commit -m "Initial commit - Azure VoiceLive Agent"

# Adicione remote (substitua com seu repositório)
git remote add origin https://github.com/seu-usuario/agent-microsoft.git
git branch -M main
git push -u origin main
```

### Passo 2: Criar Aplicação no Easy Panel

1. **Acesse seu servidor no Easy Panel**
2. **Clique em "Create" → "App"**
3. **Configure os campos**:
   - **Name**: `voicelive-agent` (ou nome de sua preferência)
   - **Source**: Selecione "Git"
   - **Repository URL**: `https://github.com/seu-usuario/agent-microsoft.git`
   - **Branch**: `main` (ou a branch desejada)

### Passo 3: Configurar Build

No Easy Panel, configure:

**Tipo de Build**: `Dockerfile`
- O Easy Panel detectará automaticamente o `Dockerfile` na raiz

**Build Context**: `.` (pasta raiz)

**Dockerfile**: `Dockerfile`

### Passo 4: Configurar Variáveis de Ambiente

Na seção **Environment Variables** do Easy Panel, adicione:

#### Variáveis Obrigatórias:

```bash
# Ambiente
APP_ENV=production
PORT=8000

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://seu-recurso.openai.azure.com/
AZURE_OPENAI_API_KEY=sua-chave-aqui

# Azure VoiceLive
AZURE_VOICELIVE_ENDPOINT=https://seu-recurso.voicelive.azure.com/
AZURE_VOICELIVE_API_KEY=sua-chave-voicelive

# Supabase
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sua-service-role-key
```

> [!IMPORTANT]
> **Nunca commite as chaves no repositório!** Use apenas as variáveis de ambiente do Easy Panel.

### Passo 5: Configurar Porta e Domínio

1. **Porta**: Configure para `8000` (ou a porta definida em `PORT`)
2. **Domínio**: 
   - Easy Panel fornecerá um subdomínio automático (ex: `voicelive-agent.easypanel.host`)
   - Ou configure um domínio customizado

### Passo 6: Deploy

1. **Clique em "Deploy"**
2. Aguarde o build (pode levar 2-5 minutos)
3. Monitore os logs em tempo real

### Passo 7: Verificar

Acesse o endpoint de health check:
```
https://seu-dominio.easypanel.host/health
```

Se retornar status `200 OK`, o deploy foi bem-sucedido! 🎉

---

## 🐳 Método 2: Deploy via Docker Registry

### Passo 1: Build Local da Imagem

```bash
# Build da imagem
docker build -t voicelive-agent:latest .

# Tag para seu registry
docker tag voicelive-agent:latest seu-usuario/voicelive-agent:latest

# Push para Docker Hub (ou outro registry)
docker push seu-usuario/voicelive-agent:latest
```

### Passo 2: Configurar no Easy Panel

1. **Create** → **App**
2. **Source**: Selecione "Docker Image"
3. **Image**: `seu-usuario/voicelive-agent:latest`
4. Configure variáveis de ambiente (igual ao Método 1)
5. **Deploy**

---

## 📦 Método 3: Deploy com Docker Compose

Se quiser usar o `docker-compose.yml` existente:

### Passo 1: Criar Stack no Easy Panel

1. **Create** → **Stack**
2. Cole o conteúdo do `docker-compose.yml` (apenas o serviço production)

### Arquivo Simplificado para Easy Panel:

```yaml
version: '3.8'

services:
  voicelive-prod:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - APP_ENV=production
      - PORT=${PORT}
      - AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}
      - AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}
      - AZURE_VOICELIVE_ENDPOINT=${AZURE_VOICELIVE_ENDPOINT}
      - AZURE_VOICELIVE_API_KEY=${AZURE_VOICELIVE_API_KEY}
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_SERVICE_ROLE_KEY=${SUPABASE_SERVICE_ROLE_KEY}
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

### Passo 2: Configurar Variáveis

Configure as mesmas variáveis de ambiente na seção de Environment do Stack.

---

## 🔒 Segurança e Boas Práticas

### Variáveis de Ambiente Secretas

> [!CAUTION]
> **NUNCA** commite arquivos `.env` para o Git!

Certifique-se que o `.gitignore` contém:
```
.env
.env.*
!.env.example
```

### Limitar Recursos

No Easy Panel, configure limites de recursos:

- **CPU**: 1-2 cores
- **Memória**: 1-2 GB
- Ajuste conforme a carga esperada

### Backup e Rollback

O Easy Panel permite:
- **Rollback automático** para versões anteriores
- **Deploys via Git** facilitam reverter commits problemáticos

---

## 📊 Monitoramento

### Logs no Easy Panel

1. Acesse a aplicação no painel
2. Clique em **"Logs"**
3. Monitore logs em tempo real

### Health Checks

O Easy Panel executará automaticamente o health check definido no `Dockerfile`:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1
```

### Métricas

Monitor via painel:
- CPU usage
- Memória
- Network I/O
- Uptime

---

## 🔄 Deploy Contínuo (CI/CD)

### Auto-Deploy com Git

Se escolheu deploy via Git, configure **Auto Deploy**:

1. No Easy Panel, vá em configurações da app
2. Ative **"Auto Deploy"**
3. Escolha a branch (ex: `main`)

Agora, a cada push na branch escolhida, o Easy Panel fará deploy automático! 🚀

### Webhook Manual

Alternativamente, use webhooks do GitHub/GitLab para controle fino:

1. Easy Panel fornece uma **Webhook URL**
2. Configure no GitHub:
   - **Settings** → **Webhooks** → **Add webhook**
   - Cole a URL do Easy Panel
   - Events: `push` ou `release`

---

## 🧪 Ambientes Múltiplos

Para ter Development, Staging e Production no Easy Panel:

### Estratégia 1: Apps Separadas

Crie 3 apps diferentes:
- `voicelive-dev` (branch: `develop`)
- `voicelive-staging` (branch: `staging`)
- `voicelive-prod` (branch: `main`)

Cada uma com suas próprias variáveis de ambiente.

### Estratégia 2: Uma App, Múltiplas Versões

Use **tags Git** para versionar:
```bash
git tag -a v1.0.0 -m "Release 1.0.0"
git push origin v1.0.0
```

No Easy Panel, faça deploy da tag específica.

---

## 🐛 Troubleshooting

### Build Falha

**Erro**: `Failed to build Docker image`

**Solução**: 
1. Verifique logs de build
2. Teste build localmente: `docker build -t test .`
3. Certifique-se que `requirements.txt` está correto

### App não Inicia

**Erro**: Container sai imediatamente

**Solução**:
1. Verifique variáveis de ambiente estão todas configuradas
2. Veja logs do container no Easy Panel
3. Teste localmente com Docker:
```bash
docker run -e APP_ENV=production -p 8000:8000 voicelive-agent
```

### Health Check Falha

**Erro**: Health check retorna unhealthy

**Solução**:
1. Teste endpoint manualmente: `curl http://localhost:8000/health`
2. Verifique se o `PORT` está correto
3. Ajuste timeout do health check se necessário

### Porta Incorreta

**Erro**: Cannot bind to port

**Solução**:
1. Certifique-se que `PORT` no Easy Panel = porta no código
2. Padrão é `8000`, mas pode variar

---

## 📚 Recursos Adicionais

### Documentação Oficial

- [Easy Panel Docs](https://easypanel.io/docs)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Azure OpenAI](https://learn.microsoft.com/azure/ai-services/openai/)

### Comandos Úteis

```bash
# Ver logs da aplicação
docker logs -f container-id

# Entrar no container
docker exec -it container-id /bin/bash

# Verificar variáveis de ambiente
docker exec container-id env

# Health check manual
curl -v http://seu-dominio.easypanel.host/health
```

---

## ✅ Checklist de Deploy

Use este checklist antes de cada deploy:

- [ ] Código commitado e pushed para Git
- [ ] Variáveis de ambiente configuradas no Easy Panel
- [ ] `.env` **NÃO** está no repositório
- [ ] `Dockerfile` está funcional (testado localmente)
- [ ] Health check endpoint funciona
- [ ] Credenciais Azure estão válidas
- [ ] Supabase está acessível
- [ ] Porta configurada corretamente (8000)
- [ ] Logs estão sendo gerados corretamente

---

## 🎉 Conclusão

Após seguir este guia, sua aplicação estará:

✅ Deployada no Easy Panel  
✅ Com deploy automático via Git  
✅ Monitorada com health checks  
✅ Escalável e pronta para produção  

**Próximos Passos:**

1. Configure domínio personalizado
2. Adicione SSL/TLS (Easy Panel faz automático via Let's Encrypt)
3. Configure alertas de uptime
4. Implemente monitoring avançado (ex: Sentry, DataDog)

---

## 🤝 Precisa de Ajuda?

Se encontrar problemas:

1. Verifique os logs no Easy Panel
2. Teste localmente com Docker primeiro
3. Revise este guia
4. Consulte documentação oficial do Easy Panel

**Boa sorte com seu deploy! 🚀**
