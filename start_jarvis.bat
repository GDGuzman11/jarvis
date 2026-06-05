@echo off
title Jarvis Launcher
echo Starting Jarvis Backend...
start "Jarvis Backend" cmd /k "cd /d C:\Users\User\appsbyG\Jarvis && .venv\Scripts\activate.bat && python -m backend.main"

echo Waiting 3 seconds for backend to initialise...
timeout /t 3 /nobreak > nul

echo Starting Jarvis Frontend...
start "Jarvis Frontend" cmd /k "cd /d C:\Users\User\appsbyG\Jarvis\frontend && pnpm tauri dev"
