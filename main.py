"""FastAPI backend for YouTube transcriber application."""

import json
import logging
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.downloader import download_audio, cleanup_audio_file, validate_youtube_url
from src.transcriber import (
    transcribe_audio,
    save_transcript,
)
from src.utils import (
    setup_logger,
    build_output_filename,
    get_output_directory,
    get_temp_path,
    get_whisper_model,
    file_exists,
)

# Setup logging
logger = setup_logger(__name__)

# FastAPI app
app = FastAPI(
    title="YouTube Transcriber API",
    description="Transcribe YouTube videos to text",
    version="1.0.0",
)

# Add CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Job tracking dictionary
jobs: Dict[str, Dict] = {}
jobs_lock = threading.Lock()
JOBS_FILE = Path("jobs.json")


def load_jobs() -> None:
    """Load jobs from persistent storage."""
    global jobs
    if JOBS_FILE.exists():
        try:
            with open(JOBS_FILE, 'r') as f:
                jobs = json.load(f)
            logger.info(f"Loaded {len(jobs)} jobs from disk")
        except Exception as e:
            logger.error(f"Error loading jobs: {str(e)}")
            jobs = {}
    else:
        jobs = {}


def save_jobs() -> None:
    """Save jobs to persistent storage."""
    try:
        with open(JOBS_FILE, 'w') as f:
            json.dump(jobs, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error saving jobs: {str(e)}")


# Pydantic models
class TranscribeRequest(BaseModel):
    """Request model for transcription."""

    youtube_url: str = Field(..., description="YouTube video URL")
    include_metadata: bool = Field(
        default=True, description="Include metadata in output"
    )


class TranscribeResponse(BaseModel):
    """Response model for transcription request."""

    job_id: str = Field(..., description="Unique job ID for tracking")
    status: str = Field(
        ..., description="Job status: queued, processing, completed, failed"
    )
    message: str = Field(..., description="Status message")


class FileUploadResponse(BaseModel):
    """Response model for file upload request."""

    job_id: str = Field(..., description="Unique job ID for tracking")
    status: str = Field(
        ..., description="Job status: queued, processing, completed, failed"
    )
    message: str = Field(..., description="Status message")
    filename: str = Field(..., description="Uploaded filename")


class JobStatusResponse(BaseModel):
    """Response model for job status."""

    job_id: str
    status: str
    message: str
    progress: int = Field(default=0, description="Progress percentage (0-100)")
    output_file: Optional[str] = None
    error: Optional[str] = None
    segments: List[Dict[str, Any]] = Field(default_factory=list, description="List of transcribed segments with timestamps")


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize on server startup."""
    logger.info("Starting FastAPI server")
    load_jobs()


@app.get("/", tags=["UI"])
async def root() -> FileResponse:
    """
    Serve the main UI HTML page.

    Returns:
        FileResponse: The index.html file.
    """
    logger.info("UI request received")
    return FileResponse("static/index.html", media_type="text/html")


@app.get("/ui", tags=["UI"])
async def serve_ui() -> FileResponse:
    """
    Serve the main UI HTML page (alternate endpoint).

    Returns:
        FileResponse: The index.html file.
    """
    logger.info("UI request received (via /ui)")
    return FileResponse("static/index.html", media_type="text/html")


@app.get("/health", tags=["Health"])
async def health_check() -> JSONResponse:
    """
    Health check endpoint for monitoring.

    Returns:
        JSONResponse: API status information.
    """
    logger.info("Health check request received")
    return JSONResponse({"status": "ok", "message": "API is running"})


@app.post("/transcribe", response_model=TranscribeResponse, tags=["Transcription"])
async def transcribe(
    request: TranscribeRequest, background_tasks: BackgroundTasks
) -> TranscribeResponse:
    """
    Start a new transcription job.

    Args:
        request: TranscribeRequest containing YouTube URL.
        background_tasks: FastAPI background tasks.

    Returns:
        TranscribeResponse: Job information including job_id.

    Raises:
        HTTPException: If URL is invalid or job creation fails.
    """
    logger.info(f"Transcription request received for URL: {request.youtube_url}")

    # Validate URL
    if not validate_youtube_url(request.youtube_url):
        logger.error(f"Invalid YouTube URL: {request.youtube_url}")
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    # Create job ID
    job_id = str(uuid.uuid4())

    # Initialize job status
    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "message": "Job queued for processing",
            "progress": 0,
            "output_file": None,
            "error": None,
            "segments": [],
            "youtube_url": request.youtube_url,
            "include_metadata": request.include_metadata,
            "started_at": datetime.now().isoformat(),
        }

    logger.info(f"New transcription job created: {job_id}")

    # Start background task
    background_tasks.add_task(
        _process_transcription_job,
        job_id,
        request.youtube_url,
        request.include_metadata,
    )

    return TranscribeResponse(
        job_id=job_id,
        status="queued",
        message="Transcription job has been queued",
    )


@app.post("/transcribe/file", response_model=FileUploadResponse, tags=["Transcription"])
async def transcribe_file(
    file: UploadFile = File(...), background_tasks: BackgroundTasks = BackgroundTasks()
) -> FileUploadResponse:
    """
    Start a new transcription job from an uploaded audio/video file.

    Supported formats: mp3, mp4, wav, m4a, ogg, webm, flac
    Max file size: 500MB

    Args:
        file: Audio or video file to transcribe.
        background_tasks: FastAPI background tasks.

    Returns:
        FileUploadResponse: Job information including job_id.

    Raises:
        HTTPException: If file type is unsupported or file is too large.
    """
    logger.info(f"File upload request: {file.filename}")

    # Validate filename is provided
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Validate file extension
    supported_formats = {".mp3", ".mp4", ".wav", ".m4a", ".ogg", ".webm", ".flac"}
    file_ext = Path(file.filename).suffix.lower()

    if file_ext not in supported_formats:
        logger.error(f"Unsupported file type: {file_ext}")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {file_ext}. "
            f"Supported: {', '.join(supported_formats)}",
        )

    # Validate file size (500MB max)
    max_size_bytes = 500 * 1024 * 1024  # 500MB
    file_size = 0

    # Create job ID and temp file path
    job_id = str(uuid.uuid4())
    temp_file_path = get_temp_path(f"{job_id}_{file.filename}")

    try:
        # Save uploaded file to temp directory
        with open(temp_file_path, "wb") as buffer:
            while True:
                chunk = await file.read(8192)  # 8KB chunks
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > max_size_bytes:
                    # Clean up partial file
                    temp_file_path.unlink()
                    logger.error(f"File too large: {file.filename}")
                    raise HTTPException(
                        status_code=413,
                        detail="File too large. Maximum size is 500MB.",
                    )
                buffer.write(chunk)

        logger.info(f"File saved to temp: {temp_file_path}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {str(e)}")
        if temp_file_path.exists():
            temp_file_path.unlink()
        raise HTTPException(status_code=500, detail="Failed to save file")

    # Initialize job status
    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "message": "Job queued for processing",
            "progress": 0,
            "output_file": None,
            "error": None,
            "traceback": None,
            "segments": [],
            "temp_file_path": str(temp_file_path),
            "original_filename": file.filename,
            "include_metadata": True,
            "started_at": datetime.now().isoformat(),
            "segment_count": 0,
        }
        save_jobs()

    logger.info(f"New file transcription job created: {job_id}")
    logger.info(f"Job stored in jobs dict. Total jobs: {len(jobs)}")

    # Start background task
    background_tasks.add_task(_process_file_transcription_job, job_id)

    logger.info(f"Background task queued for job: {job_id}")
    logger.info(f"Jobs dict now contains: {list(jobs.keys())}")

    return FileUploadResponse(
        job_id=job_id,
        status="queued",
        message="File transcription job has been queued",
        filename=file.filename or "unknown",
    )


@app.get("/status/{job_id}", response_model=JobStatusResponse, tags=["Status"])
async def get_job_status(job_id: str) -> JobStatusResponse:
    """
    Get the status of a transcription job.

    Args:
        job_id: The job ID to check.

    Returns:
        JobStatusResponse: Current job status.

    Raises:
        HTTPException: If job_id is not found.
    """
    logger.info(f"Status check for job: {job_id}")
    logger.info(f"Current jobs in memory: {list(jobs.keys())}")

    with jobs_lock:
        if job_id not in jobs:
            logger.warning(f"Job not found: {job_id}")
            logger.warning(f"Available jobs: {list(jobs.keys())}")
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

        job = jobs[job_id]
        
        # Check for timeout (30 minutes)
        if job["status"] == "processing":
            try:
                started_at = datetime.fromisoformat(job.get("started_at", datetime.now().isoformat()))
                elapsed_seconds = (datetime.now() - started_at).total_seconds()
                if elapsed_seconds > 1800:  # 30 minutes
                    job["status"] = "failed"
                    job["error"] = "Transcription timed out after 30 minutes. Try a smaller file or use the 'base' model instead of 'medium'."
                    job["message"] = "❌ Timeout"
                    save_jobs()
            except Exception as e:
                logger.warning(f"Error checking timeout: {str(e)}")

    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        message=job["message"],
        progress=job["progress"],
        output_file=job.get("output_file"),
        error=job.get("error"),
        segments=job.get("segments", []),
    )


@app.get("/progress/{job_id}", tags=["Status"])
async def get_job_progress(job_id: str) -> Dict[str, Any]:
    """
    Get rich progress information for a job.

    Args:
        job_id: The job ID to check.

    Returns:
        dict: Rich progress details including segment count and elapsed time.

    Raises:
        HTTPException: If job_id is not found.
    """
    with jobs_lock:
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

        job = jobs[job_id]
        
        # Calculate elapsed time
        elapsed_seconds = 0
        try:
            started_at = datetime.fromisoformat(job.get("started_at", datetime.now().isoformat()))
            elapsed_seconds = int((datetime.now() - started_at).total_seconds())
        except Exception:
            pass
        
        # Get latest segment
        latest_segment = None
        if job.get("segments"):
            latest_segment = job["segments"][-1]

    return {
        "job_id": job_id,
        "status": job["status"],
        "segments_count": job.get("segment_count", len(job.get("segments", []))),
        "latest_segment": latest_segment,
        "progress": job["progress"],
        "elapsed_seconds": elapsed_seconds,
        "message": job["message"],
    }


@app.get("/outputs/{filename}", tags=["Downloads"])
async def download_transcript(filename: str) -> FileResponse:
    """
    Download a transcript file.

    Args:
        filename: The transcript filename to download.

    Returns:
        FileResponse: The transcript file.

    Raises:
        HTTPException: If file is not found.
    """
    logger.info(f"Download request for file: {filename}")

    output_dir = get_output_directory()
    file_path = output_dir / filename

    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        raise HTTPException(status_code=404, detail="Transcript file not found")

    logger.info(f"Serving file: {file_path}")
    return FileResponse(path=file_path, filename=filename, media_type="text/plain")


@app.get("/outputs", tags=["Downloads"])
async def list_outputs() -> JSONResponse:
    """
    List all available transcript files.

    Returns:
        JSONResponse: List of transcript files in the outputs directory.
    """
    logger.info("Listing available outputs")

    try:
        output_dir = get_output_directory()
        files = [
            {
                "name": f.name,
                "size": f.stat().st_size,
                "modified": f.stat().st_mtime,
            }
            for f in output_dir.glob("*.txt")
        ]

        logger.info(f"Found {len(files)} transcript files")
        return JSONResponse({"files": files})

    except Exception as e:
        logger.error(f"Failed to list outputs: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list outputs")


def _process_transcription_job(
    job_id: str, youtube_url: str, include_metadata: bool
) -> None:
    """
    Process a transcription job in the background.

    Args:
        job_id: Unique job identifier.
        youtube_url: YouTube video URL to process.
        include_metadata: Whether to include metadata in output.
    """
    audio_file_path: Optional[str] = None

    try:
        logger.info(f"Starting transcription job: {job_id}")

        with jobs_lock:
            jobs[job_id]["status"] = "processing"
            jobs[job_id]["message"] = "Downloading audio..."
            jobs[job_id]["progress"] = 10
            save_jobs()
        # Download audio
        output_dir = get_output_directory()
        audio_file_path, video_title = download_audio(youtube_url, str(output_dir))

        with jobs_lock:
            jobs[job_id]["message"] = "Transcribing audio..."
            jobs[job_id]["progress"] = 50

        logger.info(f"Audio downloaded: {audio_file_path}")

        # Transcribe audio
        whisper_model = get_whisper_model()
        result = transcribe_audio(audio_file_path, model_name=whisper_model)

        with jobs_lock:
            jobs[job_id]["message"] = "Saving transcript..."
            jobs[job_id]["progress"] = 90

        # Build output filename
        output_filename = build_output_filename(video_title)
        output_file_path = output_dir / output_filename

        # Save plain-text transcript
        metadata = (
            {
                "Title": video_title,
                "Language": result["language"],
                "Model": result["model"],
                "URL": youtube_url,
            }
            if include_metadata
            else None
        )

        save_transcript(
            result["text"],
            str(output_file_path),
            include_metadata=include_metadata,
            metadata=metadata,
        )

        logger.info(f"Transcript saved to: {output_file_path}")

        with jobs_lock:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["message"] = "Transcription completed successfully"
            jobs[job_id]["progress"] = 100
            jobs[job_id]["output_file"] = output_filename

    except Exception as e:
        logger.error(f"Transcription job failed: {str(e)}")
        with jobs_lock:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["message"] = "Transcription failed"
            jobs[job_id]["error"] = str(e)
            jobs[job_id]["progress"] = 0

    finally:
        # Cleanup audio file
        if audio_file_path and file_exists(audio_file_path):
            try:
                cleanup_audio_file(audio_file_path)
            except Exception as e:
                logger.error(f"Failed to cleanup audio file: {str(e)}")


def _process_file_transcription_job(job_id: str) -> None:
    """
    Process a file transcription job in the background.

    Args:
        job_id: Unique job identifier.
    """
    temp_file_path: Optional[str] = None

    try:
        logger.info(f"Starting file transcription job: {job_id}")

        with jobs_lock:
            temp_file_path = jobs[job_id]["temp_file_path"]
            original_filename = jobs[job_id]["original_filename"]
            jobs[job_id]["status"] = "processing"
            jobs[job_id]["message"] = "Validating audio file..."
            jobs[job_id]["progress"] = 10

        # Validate temp file exists
        temp_path = Path(temp_file_path)
        if not temp_path.exists():
            raise RuntimeError(f"Temp file not found: {temp_file_path}")

        logger.info("Temp file validation successful")
        logger.info(f"Temp file absolute path: {temp_path.resolve()}")
        logger.info(f"Temp file size: {temp_path.stat().st_size} bytes")

        # Ensure file is fully flushed to disk (Windows compatibility)
        time.sleep(0.5)

        # Double-check file still exists after sleep
        if not temp_path.exists():
            raise RuntimeError(f"Temp file disappeared: {temp_file_path}")

        logger.info(f"Processing temp file: {temp_file_path}")

        with jobs_lock:
            jobs[job_id]["message"] = "Transcribing audio..."
            jobs[job_id]["progress"] = 50

        # Transcribe audio
        whisper_model = get_whisper_model()
        logger.info(f"About to transcribe file: {str(temp_path.resolve())}")
        result = transcribe_audio(str(temp_path.resolve()), model_name=whisper_model)

        # Append segments to job for live preview streaming
        duration = result.get("duration", 0)
        segments = result.get("segments", [])

        with jobs_lock:
            jobs[job_id]["message"] = "Processing transcript..."
            jobs[job_id]["progress"] = 60
            jobs[job_id]["segments"] = [
                {
                    "start": round(s.get("start", 0), 2),
                    "end": round(s.get("end", 0), 2),
                    "text": s.get("text", "").strip(),
                }
                for s in segments
            ]
            jobs[job_id]["segment_count"] = len(segments)
            jobs[job_id]["progress"] = 90
            save_jobs()

        # Build output filename from original filename
        filename_without_ext = Path(original_filename).stem
        output_filename = build_output_filename(filename_without_ext)
        output_dir = get_output_directory()
        output_file_path = output_dir / output_filename

        # Save plain-text transcript with metadata
        metadata = {
            "Title": filename_without_ext,
            "Language": result["language"],
            "Model": result["model"],
            "Source File": original_filename,
        }

        save_transcript(
            result["text"],
            str(output_file_path),
            include_metadata=True,
            metadata=metadata,
        )

        logger.info(f"Transcript saved to: {output_file_path}")

        with jobs_lock:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["message"] = "✅ Transcription complete!"
            jobs[job_id]["progress"] = 100
            jobs[job_id]["output_file"] = output_filename
            save_jobs()

    except Exception as e:
        error_message = str(e)
        traceback_str = traceback.format_exc()
        logger.error(f"File transcription job failed: {error_message}")
        logger.error(f"Full traceback:\n{traceback_str}")
        with jobs_lock:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["message"] = f"Transcription failed: {error_message}"
            jobs[job_id]["error"] = error_message
            jobs[job_id]["traceback"] = traceback_str
            jobs[job_id]["progress"] = 0
            save_jobs()

    finally:
        # Cleanup temp file
        if temp_file_path:
            try:
                temp_path = Path(temp_file_path)
                if temp_path.exists():
                    temp_path.unlink()
                    logger.info(f"Cleaned up temp file: {temp_file_path}")
            except Exception as e:
                logger.error(f"Failed to cleanup temp file: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting FastAPI server")
    uvicorn.run(app, host="0.0.0.0", port=8000)
