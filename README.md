# YouTube-to-Transcript App

Convert YouTube videos into timestamped transcripts using local machine learning. No API keys required - all processing happens on your machine.

## Features

✨ **Key Capabilities**
- 🎥 Download audio from YouTube videos (or playlists)
- 🎤 Extract and process audio automatically
- 📝 Transcribe with precise timestamps
- ⏱️ Real-time progress tracking
- 💾 Save transcripts as `.txt` files
- 🌐 Simple web UI for easy access
- 🔍 Browse and download transcript history

## Tech Stack

- **Python 3.12** - Core language
- **FastAPI** - REST API backend
- **Streamlit** - Web UI frontend
- **yt-dlp** - YouTube audio download
- **OpenAI Whisper** - Local transcription (medium model by default)
- **FFmpeg** - Audio processing (system dependency)

## Project Structure

```
youtube-transcriber/
├── CLAUDE.md                    # Development notes
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment template
├── .gitignore                   # Git ignore rules
├── main.py                      # FastAPI server entry point
├── src/
│   ├── __init__.py
│   ├── downloader.py            # YouTube audio download (yt-dlp)
│   ├── transcriber.py           # Whisper transcription
│   └── utils.py                 # Shared utilities
├── frontend/
│   └── app.py                   # Streamlit web UI
├── outputs/                     # Transcript files saved here
│   └── .gitkeep
└── tests/
    ├── __init__.py
    ├── test_downloader.py       # Downloader unit tests
    └── test_transcriber.py      # Transcriber unit tests
```

## System Requirements

- **Python**: 3.12 or higher
- **FFmpeg**: System package (for audio conversion)
- **RAM**: 4GB+ recommended (Whisper medium model)
- **Disk Space**: ~2GB for Whisper model + output files

### Install FFmpeg

**Windows** (using Chocolatey):
```bash
choco install ffmpeg
```

Or download from https://ffmpeg.org/download.html

**macOS** (using Homebrew):
```bash
brew install ffmpeg
```

**Linux** (Ubuntu/Debian):
```bash
sudo apt-get install ffmpeg
```

## Installation

### 1. Clone or Download the Project

```bash
cd youtube-transcriber
```

### 2. Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

**Note**: Whisper will download the medium model (~1.5GB) on first run.

### 4. Configure Environment

```bash
# Copy template
cp .env.example .env

# Edit .env if needed (optional, defaults are fine)
```

## Running the Application

### Start Backend (FastAPI)

```bash
python main.py
```

The API will be available at `http://localhost:8000`

**API Endpoints:**
- `GET /` - Health check
- `POST /transcribe` - Start transcription job
- `GET /status/{job_id}` - Check job status
- `GET /outputs` - List all transcripts
- `GET /outputs/{filename}` - Download transcript

### Start Frontend (Streamlit)

In a new terminal (keep backend running):

```bash
streamlit run frontend/app.py
```

The UI will open at `http://localhost:8501`

## Configuration

Edit `.env` file to customize:

```env
# Whisper model size: tiny, base, small, medium (default), large
WHISPER_MODEL=medium

# Output directory for transcripts
OUTPUT_DIR=./outputs

# Logging level: DEBUG, INFO (default), WARNING, ERROR
LOG_LEVEL=INFO

# FFmpeg path (optional, auto-detect if not set)
# FFMPEG_PATH=/path/to/ffmpeg
```

### Model Sizes and Performance

| Model | Size | Speed | Accuracy | Recommended |
|-------|------|-------|----------|---|
| tiny | 39M | Fastest | Lower | Quick testing |
| base | 140M | Fast | Good | Balanced |
| small | 244M | Medium | Very good | Default-like |
| **medium** | **1.5G** | Slower | Excellent | **Recommended** |
| large | 2.9G | Slowest | Best | GPU only |

## Usage Examples

### Web UI (Recommended)

1. Open `http://localhost:8501` in your browser
2. Enter a YouTube URL:
   - Single video: `https://www.youtube.com/watch?v=...`
   - Playlist: `https://www.youtube.com/playlist?list=...`
   - Short URL: `https://youtu.be/...`
3. Click "Transcribe"
4. Monitor progress in real-time
5. Download transcript when complete

### Programmatic API

```bash
# Start transcription
curl -X POST http://localhost:8000/transcribe \
  -H "Content-Type: application/json" \
  -d '{"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'

# Response:
# {
#   "job_id": "a1b2c3d4-e5f6...",
#   "status": "queued",
#   "message": "Transcription job has been queued"
# }

# Check status
curl http://localhost:8000/status/a1b2c3d4-e5f6...

# Download transcript
curl http://localhost:8000/outputs/Video_Title_2024-01-15_10-30-45.txt
```

## Output Format

Transcripts are saved as `.txt` files with timestamps:

```
============================================================
TRANSCRIPT METADATA
============================================================
Title: Video Title
Language: en
Model: medium
URL: https://www.youtube.com/watch?v=...
============================================================

[00:00:00 - 00:00:15] Hello everyone, welcome to the channel
[00:00:15 - 00:00:32] Today we're going to talk about transcription
[00:00:32 - 00:01:05] This is really useful for content creators
...
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src tests/

# Run specific test file
pytest tests/test_downloader.py

# Verbose output
pytest -v
```

## Troubleshooting

### API Connection Error in Streamlit

**Problem**: "Cannot connect to the backend API"

**Solution**:
1. Ensure `main.py` is running: `python main.py`
2. Check if port 8000 is in use: `netstat -ano | findstr :8000` (Windows)
3. Try restarting both backend and frontend

### FFmpeg Not Found

**Problem**: "FFmpeg not found" error during download

**Solution**:
1. Verify FFmpeg installation: `ffmpeg -version`
2. Add FFmpeg to system PATH
3. Set `FFMPEG_PATH` in `.env` file

### Out of Memory

**Problem**: Process crashes with memory error

**Solution**:
1. Switch to smaller Whisper model in `.env`: `WHISPER_MODEL=base` or `WHISPER_MODEL=small`
2. Reduce number of concurrent jobs (process one at a time)
3. Increase system RAM or use a machine with more resources

### Transcription is Slow

**Problem**: Processing takes too long

**Solution**:
1. Use smaller model: `WHISPER_MODEL=base` or `WHISPER_MODEL=tiny`
2. For GPU support, install CUDA and try `CUDA_VISIBLE_DEVICES=0` before running
3. Only transcribe necessary videos

### Disk Space Issues

**Problem**: "No space left on device"

**Solution**:
1. Clean up old audio files (in cache)
2. Delete old transcripts from `outputs/` directory
3. Free up disk space on your machine

## Performance Notes

### Expected Processing Times (Whisper medium model)

- **1 minute video**: ~30 seconds
- **10 minute video**: ~3-5 minutes
- **1 hour video**: ~30-45 minutes
- **Playlist (10 videos)**: ~30-50 minutes

*Times vary based on system specs and audio quality*

### Memory Usage

- **Whisper medium model**: ~3-4 GB
- **yt-dlp download buffer**: ~200-500 MB
- **Total recommendation**: 4-8 GB RAM

## API Reference

### POST /transcribe

Submit a new transcription job.

**Request:**
```json
{
  "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "include_metadata": true
}
```

**Response:**
```json
{
  "job_id": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
  "status": "queued",
  "message": "Transcription job has been queued"
}
```

### GET /status/{job_id}

Check the status of a transcription job.

**Response:**
```json
{
  "job_id": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
  "status": "processing",
  "message": "Transcribing audio...",
  "progress": 50,
  "output_file": null,
  "error": null
}
```

**Status values**: `queued`, `processing`, `completed`, `failed`

### GET /outputs

List all available transcript files.

**Response:**
```json
{
  "files": [
    {
      "filename": "Video_Title_2024-01-15_10-30-45.txt",
      "size_mb": 0.15,
      "modified": 1705334445
    }
  ]
}
```

### GET /outputs/{filename}

Download a transcript file.

**Response**: Plain text file

## Development

### Code Standards

- **Type Hints**: All functions have complete type annotations
- **Docstrings**: Google-style docstrings on all functions and classes
- **Error Handling**: Robust error handling with informative messages
- **Logging**: INFO and ERROR level logging throughout
- **Testing**: Unit tests with mocking for external dependencies

### Running Linting

```bash
# Install linting tools
pip install flake8 black isort mypy

# Format code
black src/ tests/ frontend/ main.py

# Check imports
isort src/ tests/ frontend/ main.py

# Type checking
mypy src/ tests/ main.py

# Linting
flake8 src/ tests/ frontend/ main.py --max-line-length=100
```

## License

MIT License - Free to use and modify

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## Support

- 📖 See [CLAUDE.md](CLAUDE.md) for development notes
- 🐛 Check GitHub issues for known problems
- 💬 Create an issue for bug reports or feature requests

## Acknowledgments

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - YouTube downloader
- [OpenAI Whisper](https://github.com/openai/whisper) - Speech-to-text model
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [Streamlit](https://streamlit.io/) - Data app framework
