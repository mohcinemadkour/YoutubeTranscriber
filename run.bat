@echo off
REM YouTube to Article - Windows Startup Script
REM Activates venv and starts both FastAPI backend and Streamlit frontend

call venv\Scripts\activate
start "YouTube Transcriber Backend" python main.py
timeout /t 3
streamlit run frontend\app.py
