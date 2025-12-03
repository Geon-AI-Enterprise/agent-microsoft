# 🚀 Quick Start - Deploy Easy Panel

Guia rápido em 5 minutos para fazer deploy no Easy Panel.

---

## ⚡ Passos Rápidos

### 1️⃣ Prepare o Código

```bash
# Verifique se tudo está pronto
python scripts/verify_deploy.py

# Commit e push para GitHub
git add .
git commit -m "Deploy para Easy Panel"
git push origin main
```

### 2️⃣ Crie App no Easy Panel

1. Acesse **Easy Panel** → seu servidor
2. **Create** → **App**
3. Preencha:
   - **Nome**: `voicelive-agent`
   - **Source**: Git
   - **Repository**: `https://github.com/seu-usuario/agent-microsoft.git`
   - **Branch**: `main`
   - **Dockerfile**: `Dockerfile`

### 3️⃣ Adicione Variáveis de Ambiente

Cole estas variáveis na seção **Environment**:

```bash
APP_ENV=production
PORT=8000
AZURE_OPENAI_ENDPOINT=https://seu-recurso.openai.azure.com/
AZURE_OPENAI_API_KEY=sua-chave-aqui
AZURE_VOICELIVE_ENDPOINT=https://seu-recurso.voicelive.azure.com/
AZURE_VOICELIVE_API_KEY=sua-chave-voicelive
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sua-service-role-key
```

> ⚠️ **Substitua os valores** com suas credenciais reais!

### 4️⃣ Configure Porta

- **Porta**: `8000`

### 5️⃣ Deploy

1. Clique em **Deploy**
2. Aguarde 2-5 minutos
3. Monitore os logs

### 6️⃣ Teste

```bash
curl https://seu-dominio.easypanel.host/health
```

✅ **Resposta esperada**: `{"status": "ok"}`

---

## 📋 Checklist de Deploy

- [ ] Código commitado e pushed para GitHub
- [ ] `verify-deploy.py` executado com sucesso
- [ ] `.env` NÃO está no repositório Git
- [ ] App criada no Easy Panel
- [ ] Repositório Git configurado
- [ ] 8 variáveis de ambiente adicionadas
- [ ] Porta configurada (8000)
- [ ] Deploy iniciado
- [ ] Logs verificados (sem erros)
- [ ] Health check funcionando

---

## 🆘 Problemas Comuns

### Build Falha
```bash
# Teste localmente primeiro
docker build -t test .
```

### Health Check Não Funciona
```bash
# Verifique se a porta está correta
# Veja se todas as variáveis de ambiente estão configuradas
```

### Variáveis de Ambiente
```bash
# Certifique-se que TODAS as 8 variáveis foram adicionadas
# Não use aspas nos valores no Easy Panel
```

---

## 📖 Guia Completo

Para mais detalhes, veja: **[DEPLOY_EASYPANEL.md](./DEPLOY_EASYPANEL.md)**

---

**Pronto! Seu deploy deve estar funcionando! 🎉**
