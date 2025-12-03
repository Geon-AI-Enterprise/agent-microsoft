@echo off
REM ==========================================
REM Script para rodar aplicação em diferentes ambientes
REM ==========================================

IF "%1"=="" (
    echo Uso: run_env.bat [development^|staging^|production]
    echo.
    echo Exemplos:
    echo   run_env.bat development
    echo   run_env.bat staging
    echo   run_env.bat production
    exit /b 1
)

SET ENV=%1

IF "%ENV%"=="development" (
    echo Rodando em DEVELOPMENT...
    copy /Y .env.development .env
    python -m src.main
) ELSE IF "%ENV%"=="staging" (
    echo Rodando em STAGING...
    copy /Y .env.staging .env
    python -m src.main
) ELSE IF "%ENV%"=="production" (
    echo Rodando em PRODUCTION...
    copy /Y .env.production .env
    python -m src.main
) ELSE (
    echo Ambiente invalido: %ENV%
    echo Use: development, staging ou production
    exit /b 1
)
