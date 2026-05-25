#!/bin/bash
# YouTube to Article - Linux/Mac Startup Script
# Activates venv and starts both FastAPI backend and Streamlit frontend

source venv/bin/activate
python main.py &
sleep 3
streamlit run frontend/app.py
