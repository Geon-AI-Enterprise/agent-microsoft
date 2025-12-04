# src/healthcheck.py
import urllib.request
import os
import sys

# Pega a porta do ambiente ou usa 8000 como fallback
port = os.getenv('PORT', '8000')
url = f"http://127.0.0.1:{port}/health"

try:
    # Tenta conectar. Se retornar 200, sai com sucesso (0)
    with urllib.request.urlopen(url) as response:
        if response.status == 200:
            print(f"✅ Healthcheck OK: {url}")
            sys.exit(0)
        else:
            print(f"⚠️ Healthcheck FALHOU: Status {response.status}")
            sys.exit(1)
except Exception as e:
    # Se der erro de conexão, escreve no stderr e sai com erro (1)
    print(f"❌ Healthcheck ERRO: {e}", file=sys.stderr)
    sys.exit(1)