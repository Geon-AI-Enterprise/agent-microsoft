# 📝 Guia de Configuração do Agente

Este guia explica **todas** as configurações disponíveis no `agent_config.json`.

## 📄 Estrutura do arquivo

```json
{
  "model": "gpt-realtime",
  "voice": "en-US-Andrew:DragonHDLatestNeural",
  "temperature": 0.7,
  "max_tokens": 800,
  "speech_rate": 1.0,
  "top_p": 0.9,
  "frequency_penalty": 0.0,
  "presence_penalty": 0.0,
  "turn_detection": { ... },
  "audio": { ... },
  "modalities": ["TEXT", "AUDIO"],
  "instructions": "..."
}
```

---

## 🤖 Configurações do Modelo LLM

### `model` (string)
Modelo de IA a ser usado.

**Valores aceitos:**
- `"gpt-realtime"` - Modelo padrão Azure VoiceLive
- `"gpt-4o-realtime-preview"` - GPT-4o Realtime (se disponível)

**Padrão:** `"gpt-realtime"`

---

### `temperature` (número: 0.0 - 2.0)
Controla a **criatividade** e **aleatoriedade** das respostas.

**Valores:**
- `0.0` - Muito determinístico, sempre respostas similares
- `0.5` - Moderadamente consistente
- `0.7` - **Recomendado** - Balanceado entre criatividade e consistência
- `1.0` - Mais criativo, respostas variadas
- `1.5-2.0` - Muito criativo, pode ser imprevisível

**Recomendação para atendimento:** `0.6 - 0.8`

---

### `max_tokens` (número inteiro)
Número máximo de tokens (palavras aproximadas) na resposta.

**Valores:**
- `400-600` - Respostas curtas e diretas
- `800` - **Padrão** - Respostas médias
- `1000-1500` - Respostas mais elaboradas

**Nota:** 1 token ≈ 0.75 palavras (em português)

---

### `top_p` (número: 0.0 - 1.0)
Nucleus sampling - controla a diversidade considerando os tokens mais prováveis.

**Valores:**
- `0.9` - **Padrão** - Bom equilíbrio
- `1.0` - Considera todos os tokens possíveis
- `0.5` - Mais focado nos tokens mais prováveis

**Dica:** Use com `temperature`. Se `temperature` é baixo, `top_p` pode ser mais alto.

---

### `frequency_penalty` (número: -2.0 a 2.0)
Penaliza palavras que aparecem com frequência na conversa.

**Valores:**
- `0.0` - **Padrão** - Sem penalização
- `0.3 - 0.6` - Reduz repetições levemente
- `0.8 - 1.0` - Reduz bastante repetições
- Valores negativos: Incentiva repetições (raramente útil)

**Recomendação:** `0.0 - 0.3` para agentes de atendimento

---

### `presence_penalty` (número: -2.0 a 2.0)
Incentiva o modelo a falar sobre novos tópicos.

**Valores:**
- `0.0` - **Padrão** - Sem incentivo
- `0.3 - 0.6` - Incentiva moderadamente novos tópicos
- `0.8 - 1.0` - Forte incentivo a diversificar tópicos

**Recomendação:** `0.0 - 0.2` para manter foco no atendimento

---

## 🎤 Configurações de Voz

### `voice` (string)
Modelo de voz neural do Azure.

**Formatos aceitos:**
```
pt-BR-FranciscaNeural          # Voz brasileira feminina
pt-BR-AntonioNeural            # Voz brasileira masculina
en-US-Andrew:DragonHDLatestNeural  # Voz inglesa HD de alta qualidade
```

**Vozes brasileiras recomendadas:**
- `pt-BR-FranciscaNeural` - Feminina, clara e profissional
- `pt-BR-BrendaNeural` - Feminina, jovem e amigável
- `pt-BR-AntonioNeural` - Masculina, séria e confiável
- `pt-BR-DonatoNeural` - Masculina, madura e experiente

[Lista completa de vozes Azure](https://learn.microsoft.com/azure/ai-services/speech-service/language-support?tabs=tts)

---

### `speech_rate` (número: 0.5 - 2.0)
Velocidade da fala.

**Valores:**
- `0.75` - Bem devagar (para explicações complexas)
- `0.9` - Devagar
- `1.0` - **Padrão** - Velocidade normal
- `1.1` - Levemente mais rápido
- `1.3` - Rápido (para conversas dinâmicas)
- `1.5+` - Muito rápido (pode dificultar compreensão)

**Recomendação para consultoria:** `0.9 - 1.1`

---

## 🔊 Configurações de Áudio

### `audio.input_format` (string)
Formato do áudio de entrada.

**Valores aceitos:**
- `"PCM16"` - **Padrão** - 16-bit PCM (melhor qualidade)
- `"PCM8"` - 8-bit PCM (menor qualidade, economiza banda)

---

### `audio.output_format` (string)
Formato do áudio de saída.

**Valores aceitos:**
- `"PCM16"` - **Padrão** - 16-bit PCM
- `"PCM8"` - 8-bit PCM

---

### `audio.echo_cancellation` (boolean)
Ativa cancelamento de eco.

**Valores:**
- `true` - **Recomendado** - Cancela eco do microfone
- `false` - Desativa cancelamento

---

### `audio.noise_reduction` (string)
Tipo de redução de ruído.

**Valores:**
- `"azure_deep_noise_suppression"` - **Recomendado** - Redução avançada
- `"basic"` - Redução básica
- `null` - Sem redução de ruído

---

## 🎯 Detecção de Turno (Turn Detection)

Controla quando o agente detecta que o usuário terminou de falar.

### `turn_detection.threshold` (número: 0.0 - 1.0)
Sensibilidade para detectar quando o usuário está falando.

**Valores:**
- `0.3` - Muito sensível (detecta até sussurros)
- `0.5` - **Padrão** - Sensibilidade balanceada
- `0.7` - Menos sensível (ignora sons baixos)

---

### `turn_detection.prefix_padding_ms` (número em ms)
Tempo de áudio **antes** da fala detectada a ser incluído.

**Valores:**
- `100` - Mínimo
- `300` - **Padrão** - Recomendado
- `500` - Captura mais contexto antes da fala

---

### `turn_detection.silence_duration_ms` (número em ms)
Tempo de **silêncio** para considerar que o usuário terminou de falar.

**Valores:**
- `300` - Agente responde rapidamente (pode cortar usuário)
- `500` - **Padrão** - Bom equilíbrio
- `800` - Espera mais (conversas mais pausadas)
- `1000+` - Muito paciente (pode parecer lento)

**Recomendação:** `400-600ms` para atendimento profissional

---

## 📡 Modalidades

### `modalities` (array)
Tipos de entrada/saída que o agente suporta.

**Valores aceitos:**
- `["TEXT"]` - Apenas texto
- `["AUDIO"]` - Apenas áudio
- `["TEXT", "AUDIO"]` - **Padrão** - Ambos

---

## 📋 Instruções (Prompt)

### `instructions` (string longa)
O **prompt completo** do agente. Este é um campo de texto livre onde você define:

- Identidade do agente
- Personalidade e tom de voz
- Regras de comportamento
- Fluxo de conversa
- Conhecimento sobre produtos/serviços
- Como lidar com objeções

**Dicas:**
- Seja claro e específico
- Use exemplos de diálogo
- Defina regras explícitas (ex: "NUNCA invente informações")
- Estruture em seções numeradas para clareza

---

## 🎨 Exemplos de Configuração

### Agente Consultivo (Atual - Lia)
```json
{
  "model": "gpt-realtime",
  "voice": "pt-BR-FranciscaNeural",
  "temperature": 0.7,
  "speech_rate": 0.95,
  "max_tokens": 800,
  "turn_detection": {
    "threshold": 0.5,
    "silence_duration_ms": 600
  }
}
```

### Agente Dinâmico (Vendas Ativas)
```json
{
  "model": "gpt-realtime",
  "voice": "pt-BR-BrendaNeural",
  "temperature": 0.8,
  "speech_rate": 1.1,
  "max_tokens": 600,
  "turn_detection": {
    "threshold": 0.5,
    "silence_duration_ms": 400
  }
}
```

### Agente Técnico (Suporte)
```json
{
  "model": "gpt-realtime",
  "voice": "pt-BR-AntonioNeural",
  "temperature": 0.5,
  "speech_rate": 0.9,
  "max_tokens": 1000,
  "frequency_penalty": 0.3,
  "turn_detection": {
    "threshold": 0.5,
    "silence_duration_ms": 700
  }
}
```

---

## ⚡ Dicas Rápidas

1. **Para agente mais natural:** Aumente `temperature` para 0.8
2. **Para respostas mais consistentes:** Diminua `temperature` para 0.5
3. **Para falar mais devagar:** Ajuste `speech_rate` para 0.85-0.95
4. **Para evitar cortar usuário:** Aumente `silence_duration_ms` para 600-800
5. **Para agente mais dinâmico:** Diminua `silence_duration_ms` para 300-400
6. **Para respostas mais curtas:** Reduza `max_tokens` para 400-600
7. **Para trocar a voz:** Mude `voice` para outra voz Azure (veja lista completa)

---

## 🔄 Como Recarregar Configurações

Após editar `agent_config.json`, **reinicie** o aplicativo:

```bash
# Pare o programa atual (Ctrl+C)
# Execute novamente
python main.py
```

As novas configurações serão carregadas automaticamente!
