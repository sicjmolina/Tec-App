@echo off
title Mantenimientos Preventivos v2 - Sicolsa (Web)

echo.
echo  =====================================================
echo   Mantenimientos Preventivos v2 - Sicolsa  (Web App)
echo  =====================================================
echo.

python --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado.
    echo Descargalo en: https://www.python.org/downloads/
    echo Marca "Add Python to PATH" al instalar.
    pause
    exit /b 1
)

echo [OK] Python encontrado
echo.
echo Instalando dependencias...
pip install -r requirements.txt --quiet --disable-pip-version-check
echo [OK] Dependencias listas
echo.
echo Iniciando servidor en http://localhost:8000
echo Presiona Ctrl+C para detener.
echo.

start "" http://localhost:8000
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

if errorlevel 1 (
    echo.
    echo [ERROR] El servidor cerro con un error.
    pause
)
