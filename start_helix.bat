@echo off
title Helix Launcher
echo Starting Helix Backend...
start "Helix Backend" cmd /k "cd /d C:\Users\User\appsbyG\Jarvis && .venv\Scripts\activate.bat && python -m backend.main"

echo Waiting 3 seconds for backend to initialise...
timeout /t 3 /nobreak > nul

echo Starting Helix Frontend...
start "Helix Frontend" cmd /k "cd /d C:\Users\User\appsbyG\Jarvis\frontend && pnpm tauri dev"
