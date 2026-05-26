#!/bin/bash
# YouTube Transcriber - Linux/Mac Startup Script
# Starts FastAPI backend with integrated HTML/JS frontend

source venv/bin/activate
echo "Starting YouTube Transcriber on http://localhost:8000"
python main.py &
PYTHON_PID=$!
sleep 2

# Open browser (macOS uses 'open', Linux uses 'xdg-open')
if [[ "$OSTYPE" == "darwin"* ]]; then
    open http://localhost:8000
else
    xdg-open http://localhost:8000
fi

wait $PYTHON_PID
