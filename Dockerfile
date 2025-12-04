# ================================================================
# Dockerfile - Azure VoiceLive Agent Multi-Tenant (OTIMIZADO)
# ================================================================

# ===== STAGE 1: Base =====
FROM python:3.11-slim as base

LABEL maintainer="Grupo RCR"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# ===== STAGE 2: Dependencies =====
FROM base as dependencies

# Instala dependências de sistema necessárias para compilar pacotes (PyAudio)
RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    gcc \
    python3-dev \
    libasound2-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ===== STAGE 3: Application =====
FROM base as application

# Copia dependências Python já compiladas do estágio anterior
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Precisamos das libs de runtime do audio, mesmo que não tenha placa de som,
# para o PyAudio não crashar na importação (opcional, mas seguro)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libasound2 \
    libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

# Copia código da aplicação
COPY src/ ./src/
COPY config/ ./config/

# Cria diretório de logs e ajusta permissões
RUN mkdir -p logs && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# HEALTHCHECK NATIVO EM PYTHON (Mais robusto que curl)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; import os; \
    port = os.getenv('PORT', '8000'); \
    try: \
        urllib.request.urlopen(f'http://localhost:{port}/health').close(); \
    except Exception: exit(1)"

CMD ["python", "-m", "src.main"]