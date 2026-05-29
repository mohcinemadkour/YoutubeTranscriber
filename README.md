# YouTube Transcriber

Convert YouTube videos (or any local audio/video file) into plain-text transcripts using locally-running AI. No API keys, no cloud services — everything runs on your machine.

## Launch

```bash
python main.py
```

Then open **http://localhost:8000** in your browser.

> **Windows one-click launcher** — double-click `run.bat` to start the server and open the browser automatically.  
> **Linux/Mac** — `bash run.sh`

---

## Features

- **YouTube URL** — paste a URL, the app downloads the audio and transcribes it
- **File upload** — upload an MP3/MP4/WAV/M4A/OGG/WebM/FLAC file directly (up to 500 MB)
- **GPU-accelerated** — automatically uses CUDA (float16) when an NVIDIA GPU is available; falls back to CPU (int8)
- **Model caching** — Whisper loads once and stays in memory for instant subsequent transcriptions
- **Plain-text output** — transcripts saved as `.txt` files in `outputs/`
- **Real-time preview** — text streams into the UI as each segment is transcribed
- **Job history** — past transcripts listed and downloadable from the History tab

---

## Requirements

| Requirement | Notes |
|---|---|
| Python 3.11+ | |
| [FFmpeg](https://ffmpeg.org/download.html) | Must be on system `PATH` |
| NVIDIA GPU (optional) | CUDA-compatible driver; CPU fallback works without one |

### Install FFmpeg

**Windows** (Chocolatey):
```bash
choco install ffmpeg
```

**macOS** (Homebrew):
```bash
brew install ffmpeg
```

**Linux**:
```bash
sudo apt-get install ffmpeg
```

---

## Installation

```bash
# 1. Clone
git clone https://github.com/mohcinemadkour/YoutubeTranscriber.git
cd YoutubeTranscriber

# 2. Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

The Whisper model (~1.5 GB for `medium`) downloads automatically on first transcription.

---

## Configuration

Copy `.env.example` to `.env` and edit as needed:

```env
# Whisper model: tiny | base | small | medium (default) | large
WHISPER_MODEL=medium

# Output directory for saved transcripts
OUTPUT_DIR=./outputs

# Logging level: DEBUG | INFO | WARNING | ERROR
LOG_LEVEL=INFO

# Optional: explicit path to ffmpeg binary
# FFMPEG_PATH=C:/ffmpeg/bin/ffmpeg.exe
```

### Model sizes

| Model | Size | Speed (GPU) | Accuracy |
|---|---|---|---|
| tiny | 39 MB | ~10x | Lower |
| base | 140 MB | ~7x | Good |
| small | 244 MB | ~6x | Very good |
| **medium** | **1.5 GB** | **~3x** | **Excellent** ← default |
| large | 2.9 GB | ~2x | Best |

---

## How to use

### Method 1 — YouTube URL

1. Open http://localhost:8000
2. Paste any YouTube URL (video, short, or playlist link)
3. Click **Transcribe URL**
4. Watch the transcript stream in real time
5. Download the `.txt` file when complete

> **If YouTube blocks the download**: YouTube aggressively rate-limits automated requests.  
> Use Method 2 as a reliable fallback.

### Method 2 — Upload a file (always works)

1. Download the audio from YouTube using **[cobalt.tools](https://cobalt.tools)** (free, no account needed)
2. Switch to the **Upload Audio File** tab
3. Drag-and-drop or browse for the file
4. Click **Transcribe File**

---

## API endpoints

The FastAPI backend is directly usable from the command line:

```bash
# Transcribe a YouTube URL
curl -X POST http://localhost:8000/transcribe \
  -H "Content-Type: application/json" \
  -d '{"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'

# Upload a local file
curl -X POST http://localhost:8000/transcribe/file \
  -F "file=@audio.mp3"

# Check job status
curl http://localhost:8000/status/<job_id>

# List all saved transcripts
curl http://localhost:8000/outputs

# Download a transcript
curl http://localhost:8000/outputs/<filename>
```

---

## Project structure

```
YoutubeToArticle/
├── main.py                # FastAPI entry point — run this
├── src/
│   ├── transcriber.py     # faster-whisper integration, model caching
│   ├── downloader.py      # yt-dlp YouTube audio download
│   └── utils.py           # shared utilities (paths, filenames, logging)
├── static/
│   └── index.html         # frontend UI (vanilla JS, served by FastAPI)
├── outputs/               # saved transcript .txt files
├── temp/                  # temporary upload storage (auto-cleaned)
├── tests/                 # pytest test suite
├── run.bat                # Windows one-click launcher
├── run.sh                 # Linux/Mac launcher
└── requirements.txt
```

---

## Tech stack

| Component | Technology |
|---|---|
| Backend | FastAPI 0.104.1 + Uvicorn |
| Frontend | Vanilla JS/HTML (served by FastAPI) |
| Transcription | faster-whisper 1.2.1 (CTranslate2 backend) |
| Video download | yt-dlp |
| Audio processing | FFmpeg |
| GPU acceleration | CUDA via ctranslate2 (auto-detected) |

---

## Troubleshooting

**Port 8000 already in use**
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <pid> /F
```

**FFmpeg not found**
```bash
ffmpeg -version   # should print version info
# Install FFmpeg and ensure it is on PATH
```

**YouTube download blocked (403/400)**  
Use the file upload tab. Download audio first from [cobalt.tools](https://cobalt.tools), then upload.

**CUDA not detected / running on CPU**  
Install the NVIDIA pip packages so ctranslate2 can find the CUDA DLLs:
```bash
pip install nvidia-cublas-cu12 nvidia-cuda-runtime-cu12 nvidia-cudnn-cu12 nvidia-cuda-nvrtc-cu12
```
The app auto-detects GPU on the next start.

**Out of memory / slow transcription**  
Switch to a smaller model in `.env`:
```env
WHISPER_MODEL=small   # or base, or tiny
```
