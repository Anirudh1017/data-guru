@echo off
REM DATA GURU V2 - start backend and frontend in two windows
cd /d "%~dp0"

start "DATA GURU API" cmd /k "cd backend && python -m uvicorn main:app --port 8000"
timeout /t 3 >nul
start "DATA GURU WEB" cmd /k "cd frontend && npm run dev -- --host 127.0.0.1 --port 5173"
timeout /t 4 >nul
start "" http://127.0.0.1:5173
