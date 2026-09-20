@echo off
chcp 65001 >nul
title Trading Bot - IQ Option AI Sniper & Telegram Hub
color 0A

echo ================================================================
echo    🤖 INICIANDO TRADING BOT (IQ OPTION AI SNIPER ^& TELEGRAM)
echo ================================================================
echo.

cd /d "%~dp0"

echo [1/3] Verificando configuracion (.env)...
if not exist ".env" (
    echo [ERROR] No se encontro el archivo .env.
    pause
    exit /b
)

echo [2/3] Abriendo Dashboard en el navegador (http://localhost:8000)...
start http://localhost:8000

echo [3/3] Iniciando Servidor, Bucle de Trading y Telegram Polling...
echo.
echo ================================================================
echo  Bot activo. Para apagarlo presiona CTRL + C en esta ventana.
echo  Puedes enviar /status o /panic desde tu Telegram.
echo ================================================================
echo.

cd backend
python main.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] El bot se detuvo con un error.
    pause
)
