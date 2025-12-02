# Configuração do Agente VoiceLive

Este projeto agora separa as configurações do agente das credenciais de infraestrutura Azure.

## 📁 Estrutura de Arquivos

- **`.env`** - Apenas credenciais e endpoints da Azure (NUNCA commitar!)
- **`agent_config.json`** - Todas as características do agente (voz, personalidade, instruções)
- **`agent_config_loader.py`** - Classe Python para carregar e gerenciar configurações

## 🎯 Arquivo `.env`

Contém **apenas** credenciais sensíveis:
- Azure OpenAI endpoint e API keys
- VoiceLive endpoint e configurações
- Project IDs
- Porta do servidor

⚠️ **Nunca** adicione instruções ou prompts no `.env`

## 🤖 Arquivo `agent_config.json`

Este é o arquivo **principal** para configurar o comportamento do agente. Ele contém:

### Configurações de Voz
```json
"voice": {
  "model": "en-US-Andrew:DragonHDLatestNeural",
  "temperature": 0.7,
  "speed": 0.9,
  "pitch": 1.0
}
```

**Parâmetros:**
- `model`: Modelo de voz do Azure (formato: `locale-Name:StyleNeural`)
- `temperature`: Variação na fala (0.0 = monotônico, 1.0 = muito variado)
- `speed`: Velocidade da fala (0.5 = lento, 1.5 = rápido)
- `pitch`: Tom da voz (0.5 = grave, 1.5 = agudo)

### Configurações do Modelo
```json
"model_settings": {
  "temperature": 0.7,
  "max_tokens": 800,
  "top_p": 0.9,
  "frequency_penalty": 0.3,
  "presence_penalty": 0.3
}
```

**Parâmetros:**
- `temperature`: Criatividade do modelo (0.0 = determinístico, 1.0 = criativo)
- `max_tokens`: Tamanho máximo da resposta
- `top_p`: Nucleus sampling (0.0-1.0)
- `frequency_penalty`: Penaliza repetições (-2.0 a 2.0)
- `presence_penalty`: Incentiva novos tópicos (-2.0 a 2.0)

### Personalidade e Comportamento
```json
"personality": {
  "tone": "Calma, pausada e didática",
  "style": "Amigável e empática",
  "approach": "Reflexiva e precisa"
}
```

### Instruções Completas
O arquivo contém todas as instruções detalhadas:
- Identidade do agente (quem é a Lia)
- Resumo da empresa (Grupo RCR)
- Regras de comunicação
- Fluxo de conversa (etapas 1-4)
- Tratamento de objeções
- Frases-chave

## 💻 Como Usar no Código

### Método 1: Carregar com a Classe (Recomendado)

```python
from agent_config_loader import AgentConfig

# Carregar configuração
config = AgentConfig("agent_config.json")

# Acessar informações
print(f"Nome: {config.agent_name}")
print(f"Voz: {config.voice_model}")
print(f"Temperatura: {config.temperature}")

# Obter instruções completas formatadas
instructions = config.get_full_instructions()

# Obter etapa específica da conversa
greeting = config.get_conversation_step('step_1_greeting')
print(greeting['example'])

# Obter resposta para objeção
response = config.get_objection_response('already_have_supplier')
```

### Método 2: Atualizar Configurações Programaticamente

```python
# Atualizar configurações de voz
config.update_voice(
    speed=0.95,
    pitch=1.1
)

# Atualizar configurações do modelo
config.update_model_settings(
    temperature=0.8,
    max_tokens=1000,
    top_p=0.95
)

# As alterações são salvas automaticamente no agent_config.json
```

### Método 3: Carregar Diretamente com JSON

```python
import json

with open('agent_config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

voice_model = config['agent']['voice']['model']
instructions = config['agent']['instructions']['identity']
```

## 🎨 Personalizando o Agente

### Alterar a Voz

1. Abra `agent_config.json`
2. Modifique a seção `"voice"`:
   ```json
   "voice": {
     "model": "pt-BR-FranciscaNeural",  // Voz feminina brasileira
     "temperature": 0.8,
     "speed": 1.0,
     "pitch": 1.0
   }
   ```

**Vozes disponíveis Azure:**
- `en-US-Andrew:DragonHDLatestNeural` (masculina, inglês)
- `pt-BR-FranciscaNeural` (feminina, português)
- `pt-BR-AntonioNeural` (masculina, português)
- [Lista completa](https://learn.microsoft.com/azure/ai-services/speech-service/language-support?tabs=tts)

### Alterar o Prompt/Instruções

1. Abra `agent_config.json`
2. Modifique as seções relevantes:
   - `"identity"`: Quem é o agente
   - `"company_summary"`: Informações da empresa
   - `"communication_rules"`: Como se comunicar
   - `"conversation_flow"`: Etapas da conversa

### Ajustar Temperatura e Criatividade

1. Abra `agent_config.json`
2. Modifique `"model_settings"`:
   ```json
   "model_settings": {
     "temperature": 0.5,  // Mais conservador
     "max_tokens": 600,   // Respostas mais curtas
     "frequency_penalty": 0.5  // Evita mais repetições
   }
   ```

**Guia de Temperature:**
- `0.0 - 0.3`: Muito determinístico, sempre dá respostas similares
- `0.4 - 0.7`: Balanceado (recomendado para atendimento)
- `0.8 - 1.0`: Muito criativo, pode ser imprevisível

## 🔄 Integrando com VoiceLive SDK

```python
import os
from dotenv import load_dotenv
from agent_config_loader import AgentConfig

# Carregar credenciais da Azure (.env)
load_dotenv()

# Carregar configurações do agente (agent_config.json)
agent_config = AgentConfig("agent_config.json")

# Configurar cliente VoiceLive
client = VoiceLiveClient(
    endpoint=os.getenv('AZURE_VOICELIVE_ENDPOINT'),
    api_key=os.getenv('AZURE_VOICELIVE_API_KEY'),
    model=os.getenv('AZURE_VOICELIVE_MODEL'),
    
    # Configurações do agente vêm do JSON
    voice=agent_config.voice_model,
    instructions=agent_config.get_full_instructions(),
    temperature=agent_config.temperature,
    max_tokens=agent_config.max_tokens
)
```

## 📝 Exemplo Completo

```python
from dotenv import load_dotenv
from agent_config_loader import AgentConfig
import os

# 1. Carregar variáveis de ambiente (.env)
load_dotenv()

# 2. Carregar configurações do agente (agent_config.json)
config = AgentConfig("agent_config.json")

# 3. Exibir informações
print("=" * 50)
print(f"Agente: {config.agent_name}")
print(f"Função: {config.agent_role}")
print(f"Voz: {config.voice_model}")
print(f"Velocidade: {config.voice_speed}x")
print(f"Temperature: {config.temperature}")
print("=" * 50)

# 4. Obter instruções para enviar à API
full_instructions = config.get_full_instructions()

# 5. Usar em sua aplicação
# ... seu código aqui
```

## ✅ Vantagens desta Abordagem

1. **Separação de Responsabilidades**: Credenciais separadas de configurações
2. **Segurança**: `.env` nunca vai para o Git, `agent_config.json` pode
3. **Facilidade de Edição**: JSON é mais fácil de editar que .env
4. **Versionamento**: Você pode versionar diferentes configurações do agente
5. **Flexibilidade**: Fácil trocar vozes, prompts e parâmetros sem mexer em código

## 🚀 Próximos Passos

1. Adicione `agent_config_loader.py` ao seu `main.py`
2. Teste diferentes configurações de voz
3. Ajuste a temperature conforme o comportamento desejado
4. Crie versões alternativas do `agent_config.json` para diferentes cenários
