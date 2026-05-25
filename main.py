"""FastAPI backend for YouTube transcriber application."""

import threading
import uuid
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
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


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting FastAPI server")
    uvicorn.run(app, host="0.0.0.0", port=8000)
