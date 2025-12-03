# ================================================================
# Dockerfile - Azure VoiceLive Agent Multi-Tenant
# ================================================================
# Build otimizado com multi-stage para produção

# ===== STAGE 1: Base =====
FROM python:3.11-slim as base

# Metadados
LABEL maintainer="Grupo RCR"
LABEL description="Azure VoiceLive Agent com Supabase Multi-tenant"

# Variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Diretório de trabalho
WORKDIR /app

# ===== STAGE 2: Dependencies =====
FROM base as dependencies

# Instala dependências do sistema (se necessário para PyAudio em dev)
RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copia apenas requirements primeiro (cache do Docker)
COPY requirements.txt .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    python3-dev \
    gcc \
    libasound2-dev \
    && rm -rf /var/lib/apt/lists/*


# ===== STAGE 3: Application =====
FROM base as application

# Copia dependências instaladas
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Copia código da aplicação
COPY src/ ./src/
COPY config/ ./config/

# Cria diretório de logs
RUN mkdir -p logs

# Usuário non-root para segurança
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Porta padrão
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Comando padrão
CMD ["python", "-m", "src.main"]