@echo off
REM YouTube Transcriber - Windows Startup Script
REM Starts FastAPI backend with integrated HTML/JS frontend

call venv\Scripts\activate
echo Starting YouTube Transcriber on http://localhost:8000
start "YouTube Transcriber" python main.py
timeout /t 2
start http://localhost:8000
