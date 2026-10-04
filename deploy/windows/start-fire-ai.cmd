@echo off
setlocal
cd /d C:\FireAI\backend
call C:\FireAI\venv\Scripts\activate.bat
uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 2