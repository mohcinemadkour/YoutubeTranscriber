"""FastAPI backend for YouTube transcriber application."""

import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from src.downloader import download_audio, cleanup_audio_file, validate_youtube_url
from src.transcriber import (
    transcribe_audio,
    format_transcript_with_timestamps,
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

# Job tracking dictionary
jobs: Dict[str, Dict] = {}
jobs_lock = threading.Lock()


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


@app.get("/", tags=["Health"])
async def root() -> JSONResponse:
    """
    Health check endpoint.

    Returns:
        JSONResponse: API status information.
    """
    logger.info("Health check request received")
    return JSONResponse(
        {"status": "ok", "message": "YouTube Transcriber API is running"}
    )


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
            "youtube_url": request.youtube_url,
            "include_metadata": request.include_metadata,
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
            "temp_file_path": str(temp_file_path),
            "original_filename": file.filename,
            "include_metadata": True,
        }

    logger.info(f"New file transcription job created: {job_id}")

    # Start background task
    background_tasks.add_task(_process_file_transcription_job, job_id)

    return FileUploadResponse(
        job_id=job_id,
        status="queued",
        message="File transcription job has been queued",
        filename=file.filename,
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

    with jobs_lock:
        if job_id not in jobs:
            logger.warning(f"Job not found: {job_id}")
            raise HTTPException(status_code=404, detail="Job not found")

        job = jobs[job_id]

    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        message=job["message"],
        progress=job["progress"],
        output_file=job["output_file"],
        error=job["error"],
    )


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
                "filename": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
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
            jobs[job_id]["message"] = "Formatting transcript..."
            jobs[job_id]["progress"] = 80

        logger.info("Audio transcribed successfully")

        # Format transcript with timestamps
        formatted_transcript = format_transcript_with_timestamps(result["segments"])

        # Build output filename
        output_filename = build_output_filename(video_title)
        output_file_path = output_dir / output_filename

        # Save transcript
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
            formatted_transcript,
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

        logger.info(f"Temp file validation successful")
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

        with jobs_lock:
            jobs[job_id]["message"] = "Formatting transcript..."
            jobs[job_id]["progress"] = 80

        logger.info("Audio transcribed successfully")

        # Format transcript with timestamps
        formatted_transcript = format_transcript_with_timestamps(result["segments"])

        # Build output filename from original filename
        filename_without_ext = Path(original_filename).stem
        output_filename = build_output_filename(filename_without_ext)
        output_dir = get_output_directory()
        output_file_path = output_dir / output_filename

        # Save transcript with metadata
        metadata = {
            "Title": filename_without_ext,
            "Language": result["language"],
            "Model": result["model"],
            "Source File": original_filename,
        }

        save_transcript(
            formatted_transcript,
            str(output_file_path),
            include_metadata=True,
            metadata=metadata,
        )

        logger.info(f"Transcript saved to: {output_file_path}")

        with jobs_lock:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["message"] = "Transcription completed successfully"
            jobs[job_id]["progress"] = 100
            jobs[job_id]["output_file"] = output_filename

    except Exception as e:
        logger.error(f"File transcription job failed: {str(e)}")
        with jobs_lock:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["message"] = "Transcription failed"
            jobs[job_id]["error"] = str(e)
            jobs[job_id]["progress"] = 0

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
