# YouTube-to-Transcript App - Development Notes

## Project Overview
A production-ready local YouTube-to-transcript application that downloads audio from YouTube videos and transcribes them using OpenAI Whisper. ✅ **57 tests passing** (1 skipped), all quality checks passing.

## Quick Start

### One-Command Launch
**Windows:**
```bash
run.bat
```

**Linux/Mac:**
```bash
bash run.sh
```

This will:
1. Activate the virtual environment
2. Start FastAPI backend on http://localhost:8000
3. Start Streamlit frontend on http://localhost:8501

### Manual Launch
```bash
# Backend (Terminal 1)
python main.py

# Frontend (Terminal 2)
streamlit run frontend/app.py
```

## Testing
```bash
# Run all tests (57 passing, 1 skipped)
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=src
```

## Code Quality

### Type Checking
```bash
mypy src/ main.py frontend/app.py
```

### Linting
```bash
flake8 src/ main.py frontend/app.py tests/
```

### Code Formatting
```bash
black src/ main.py frontend/app.py tests/
isort src/ main.py frontend/app.py tests/
```

## Architecture

### Backend (FastAPI)
- **Entry point**: `main.py`
- **Core modules**:
  - `src/downloader.py`: yt-dlp integration with anti-bot protection
  - `src/transcriber.py`: Whisper integration for transcription
  - `src/utils.py`: Shared utilities (logging, file sanitization, path handling)
- **API endpoints**:
  - `POST /transcribe`: Accept YouTube URL, trigger transcription
  - `POST /transcribe/file`: Accept audio/video file upload, trigger transcription
  - `GET /status/{job_id}`: Check transcription status
  - `GET /outputs/{filename}`: Download transcript
  - `GET /outputs`: List available transcripts
  - `GET /`: Health check

### Frontend (Streamlit)
- **Entry point**: `frontend/app.py`
- **Two ways to transcribe**:
  1. **YouTube URL tab**: Paste YouTube URL directly → downloads via yt-dlp (may be blocked)
  2. **Upload Audio File tab**: Upload mp3/mp4/wav/m4a/ogg/webm/flac files → transcribe locally
     - Tip: If YouTube blocks download, use [cobalt.tools](https://cobalt.tools) to download audio, then upload
- Features:
  - YouTube URL input validation
  - File upload with format validation (max 500MB)
  - Real-time transcription progress monitoring
  - Transcript download
  - Job status polling (2-second intervals)

## Tech Stack
- **Python**: 3.11.7
- **Framework**: FastAPI 0.104.1 (backend), Streamlit 1.28.1 (frontend)
- **Audio Download**: yt-dlp 2023.12.30 with anti-bot measures
- **Transcription**: openai-whisper 20250625 (medium model, local, GPU-compatible)
- **Dependencies**: Uvicorn 0.24.0, Pydantic 2.5.0, Starlette 0.27.0
- **Testing**: pytest 7.4.3, pytest-asyncio 0.21.1, pytest-cov 4.1.0
- **Code Quality**: mypy 2.1.0, flake8 7.3.0, black 26.5.1, isort 8.0.1
- **System deps**: ffmpeg

## Known Limitations & Solutions

### YouTube 403/400 Blocking
**Symptom**: HTTP 403 "Forbidden" or HTTP 400 "Bad Request" errors from YouTube

**Root Cause**: YouTube's aggressive anti-bot detection against headless automated requests

**Mitigation (Implemented)**:
- ✅ Realistic Chrome User-Agent header
- ✅ Exponential backoff: 3-5 retries per request type
- ✅ Sleep intervals (1-3 seconds) between requests
- ✅ Cookie extraction from browser (gracefully falls back)
- ✅ Clear user-friendly error messages

**Status**: Code is correct. YouTube blocking is a platform-level limitation. For production with high volume, consider:
- Proxy rotation services
- Browser automation (Selenium/Playwright)
- Alternative video sources
- Pre-transcribed content library

### Windows 260-Character Path Limit
**Symptom**: File creation failures when video titles exceed length limits on Windows

**Solution (Implemented)**:
- ✅ `sanitize_filename()` enforces hard max_length cap with safe `.rstrip()`
- ✅ `build_output_filename()` hard caps title stem at 60 characters
- ✅ Timestamp format: `YYYY-MM-DD_HH-MM-SS`
- ✅ Total filename never exceeds 100 characters (Windows safety margin)
- ✅ Example: "Rick Astley - Never Gonna Give You Up (Official Video) (4K R_2026-05-24_19-28-43.txt" = 84 chars

**Tests**: 6 new unit tests validate all edge cases (105 char → 84 char filename, special char removal, size limits)

## Configuration
Environment variables (.env):
- `WHISPER_MODEL`: Whisper model size (default: "medium", options: tiny, base, small, medium, large)
- `OUTPUT_DIR`: Output directory for transcripts (default: "./outputs")
- `LOG_LEVEL`: Logging level (default: "INFO", options: DEBUG, INFO, WARNING, ERROR)
- `FFMPEG_PATH`: Path to ffmpeg executable (optional, uses system PATH by default)

## Project Structure
```
YoutubeToArticle/
├── CLAUDE.md                    # This file
├── README.md                    # User documentation
├── requirements.txt             # Python dependencies (24 packages)
├── .gitignore                   # Git ignore rules
├── .env.example                 # Environment template
├── run.bat                       # Windows startup script
├── run.sh                        # Linux/Mac startup script
├── main.py                       # FastAPI entry point
├── src/
│   ├── __init__.py
│   ├── downloader.py            # YouTube audio download (anti-bot)
│   ├── transcriber.py           # Whisper transcription
│   └── utils.py                 # Shared utilities
├── frontend/
│   └── app.py                   # Streamlit UI (YouTube URL + Upload File tabs)
├── outputs/                     # Transcript outputs
│   └── .gitkeep
├── temp/                        # Temp directory for uploaded files
│   └── .gitkeep
└── tests/
    ├── __init__.py
    ├── test_downloader.py       # 21 tests (URL validation, download, cleanup, filename)
    ├── test_transcriber.py      # 20 tests (audio validation, transcription, formatting, saving)
    └── test_main.py             # 17 tests (file upload, job status, output endpoints)
```

## Build Order (Completed)
- [x] Step 1: Project structure and CLAUDE.md
- [x] Step 2: requirements.txt (24 dependencies, pinned versions)
- [x] Step 3: src/downloader.py (with anti-bot protection)
- [x] Step 4: src/transcriber.py (with timestamp formatting)
- [x] Step 5: src/utils.py (with filename truncation for Windows)
- [x] Step 6: main.py (async job processing, thread-safe state)
- [x] Step 7: frontend/app.py (Streamlit UI with polling)
- [x] Step 8: Tests (41 total, all passing)
- [x] Step 9: README.md (user documentation)
- [x] Step 10: Startup scripts (run.bat, run.sh)
- [x] Step 11: CLAUDE.md final state
- [x] Step 12: Local file upload feature (POST /transcribe/file, 17 new tests, 57 total)

## Test Results
```
Total: 57 PASSED, 1 SKIPPED in 4.10 seconds
├── test_downloader.py:  21 tests ✓
│   ├── URL validation: 8 tests
│   ├── Audio download: 4 tests
│   ├── Cleanup: 3 tests
│   └── Filename handling: 6 tests
├── test_transcriber.py: 20 tests ✓
│   ├── Audio validation: 6 tests
│   ├── Transcription: 4 tests
│   ├── Formatting: 5 tests
│   └── Saving: 5 tests
└── test_main.py:        17 tests ✓ (16 passed, 1 skipped)
    ├── Health check: 1 test
    ├── File upload: 10 tests (format validation, size limits, concurrent uploads)
    ├── Job status: 2 tests
    ├── Output endpoints: 2 tests
    └── Large file test: 1 skipped (Windows memory constraints)
```

## Two Ways to Transcribe

### Method 1: YouTube URL (Direct)
**Tab**: "YouTube URL"
- Paste any YouTube video/playlist URL
- App downloads audio via yt-dlp with anti-bot protection
- Transcribed with Whisper medium model
- **Limitation**: May be blocked by YouTube's aggressive bot detection
- **Workaround**: Use Method 2 if blocked

### Method 2: Upload Audio File (Fallback)
**Tab**: "Upload Audio File"
- Download audio from YouTube using [cobalt.tools](https://cobalt.tools)
- Upload audio/video file (mp3, mp4, wav, m4a, ogg, webm, flac)
- Max 500MB per file
- Transcribed locally with Whisper
- **Advantage**: No YouTube bot detection, always works

## Development Notes
- All error handling includes logging before raising exceptions
- File operations are atomic when possible
- Timestamps use `YYYY-MM-DD_HH-MM-SS` format for consistency and Windows compatibility
- URL validation happens immediately on input
- Job processing is async with thread-safe state management using `threading.Lock()`
- Filename sanitization removes: `"`, `<`, `>`, `|`, `:` and other invalid Windows characters
- Type hints on all functions, comprehensive docstrings on all public functions
- Temp files automatically cleaned up after processing
- File size validation with clear 413 error for oversized uploads
