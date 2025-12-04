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

# ===== STAGE 2: Dependencies (CORRIGIDO) =====
FROM base as dependencies

# Instala TODAS as dependências do sistema necessárias para compilar pacotes nativos (PyAudio)
# Inclui portaudio19-dev, gcc, python3-dev, libasound2-dev e curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    gcc \
    python3-dev \
    libasound2-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia apenas requirements primeiro (cache do Docker)
COPY requirements.txt .

# Instala dependências Python (agora com as libs de compilação instaladas)
RUN pip install --no-cache-dir -r requirements.txt


# ===== STAGE 3: Application =====
FROM base as application

# Copia dependências instaladas
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin
COPY --from=dependencies /usr/bin/curl /usr/bin/curl

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
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Comando padrão
CMD ["python", "-m", "src.main"]