# Quick Start

Comece a usar o Geon AI - Voice Agent em menos de 5 minutos!

## ⏱️ 5 Minutos para o Primeiro Run

### Passo 1: Instalação (2 min)

```bash
# Clone o repositório
git clone <repository-url>
cd agent-microsoft

# Crie ambiente virtual
python -m venv .venv

# Ative o ambiente
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Instale dependências
pip install -r requirements.txt
```

### Passo 2: Configuração (2 min)

```bash
# Copie o template
copy .env.example .env

# Edite com suas credenciais Azure
notepad .env
```

Preencha as variáveis obrigatórias:

```env
AZURE_VOICELIVE_ENDPOINT=https://your-resource.voicelive.azure.com/
AZURE_VOICELIVE_API_KEY=your-api-key-here
```

### Passo 3: Execute! (1 min)

```bash
python main.py
```

✅ **Pronto!** A aplicação está rodando em `http://localhost:8000`

---

## 🧪 Testando

### Health Check

```bash
curl http://localhost:8000/health
```

Resposta esperada:
```json
{
  "status": "ok",
  "env": "development"
}
```

### Teste de Voz (Development)

Se você tem PyAudio instalado:

1. Fale no microfone
2. O agente responde através dos alto-falantes
3. Verifique os logs coloridos no terminal

---

## 🎯 Próximos Passos

Agora que você tem o sistema rodando:

1. 📝 Configure o Agente - Customize voz, instruções
2. 🎨 [Explore as Features](features.md) - Conheça todas as funcionalidades  
3. 👨‍💻 [Guia de Desenvolvimento](development/guide.md) - Comece a customizar
4. 🚀 Faça Deploy - Leve para produção

---

## ❓ Problemas Comuns

### `ValidationError for Settings`

**Causa**: Variáveis de ambiente faltando  
**Solução**: Verifique se `AZURE_VOICELIVE_ENDPOINT` e `AZURE_VOICELIVE_API_KEY` estão no `.env`

### `PyAudio not found`

**Causa**: PyAudio não instalado  
**Solução**: 
- Development: `pip install pyaudio` para usar áudio local
- Production: Ignore, o sistema funciona em modo API

### Aplicação não inicia

**Causa**: Porta 8000 em uso  
**Solução**: Mude `PORT=8001` no `.env`

---

Para mais ajuda, consulte a documentação
