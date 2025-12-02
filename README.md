# Azure VoiceLive Basic Voice Assistant

## 1. Criar ambiente

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

## 2. Instalar dependências

```bash
pip install -r requirements.txt
```

## 3. Configurar variáveis

Copie `.env.example` para `.env` e coloque:

- `AZURE_VOICELIVE_API_KEY`
- `AZURE_VOICELIVE_ENDPOINT`
- (opcional) modelo, voz, instruções.

## 4. Rodar

```bash
python main.py
```

Se quiser passar tudo por argumento:

```bash
python main.py --api-key "SUA_CHAVE" --endpoint "SEU_ENDPOINT" --model "gpt-realtime"
```

Depois de iniciar, fale no microfone. A IA responde em voz.
