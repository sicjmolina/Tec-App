@echo off
title Mantenimientos Preventivos v2 - Web

echo.
echo  ==========================================
echo  Mantenimientos Preventivos v2 - Web
echo  ==========================================
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
if not exist "web\run.bat" (
    echo [ERROR] No se encontro web\run.bat
    pause
    exit /b 1
)

echo Iniciando version web...
echo.

call web\run.bat

if errorlevel 1 (
    echo.
    echo [ERROR] La aplicacion cerro con un error.
    pause
)
