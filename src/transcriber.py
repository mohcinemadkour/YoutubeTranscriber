"""Audio transcription module using faster-whisper."""

import getpass
import logging
import os
import shutil
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from typing import Optional

# Module-level model cache so the model is loaded once and reused across requests.
_model_cache: dict = {}
_model_lock = threading.Lock()


def _add_nvidia_to_path() -> None:
    """Prepend NVIDIA pip-installed CUDA DLL directories to PATH (Windows)."""
    try:
        import site
        for sp in site.getsitepackages():
            nvidia_dir = Path(sp) / "nvidia"
            if nvidia_dir.exists():
                for sub in nvidia_dir.iterdir():
                    bin_dir = sub / "bin"
                    if bin_dir.exists():
                        current = os.environ.get("PATH", "")
                        if str(bin_dir) not in current:
                            os.environ["PATH"] = str(bin_dir) + os.pathsep + current
    except Exception:
        pass


if sys.platform == "win32":
    _add_nvidia_to_path()

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


def _load_model(model_name: str) -> WhisperModel:
    """Return a cached WhisperModel, loading it on first use.

    Detects CUDA via ctranslate2; falls back to CPU/int8 if CUDA libs are
    unavailable.
    """
    with _model_lock:
        if model_name not in _model_cache:
            try:
                import ctranslate2
                device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                device = "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            logger.info(f"Loading faster-whisper '{model_name}' on {device}/{compute_type}")
            try:
                _model_cache[model_name] = WhisperModel(
                    model_name, device=device, compute_type=compute_type
                )
            except RuntimeError as e:
                if "cublas" in str(e).lower() or "cuda" in str(e).lower():
                    logger.warning("CUDA libraries unavailable — falling back to CPU/int8")
                    _model_cache[model_name] = WhisperModel(
                        model_name, device="cpu", compute_type="int8"
                    )
                else:
                    raise
            logger.info(f"Model '{model_name}' ready")
        return _model_cache[model_name]


def get_audio_duration(audio_file_path: str) -> float:
    """
    Get the duration of an audio file in seconds using FFprobe.
    
    Args:
        audio_file_path: Path to the audio file.
        
    Returns:
        float: Duration in seconds, or 0 if unable to determine.
        
    Raises:
        RuntimeError: If FFprobe is not available or fails.
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1:nokey=1",
            audio_file_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
            text=True
        )
        
        if result.returncode == 0 and result.stdout.strip():
            duration = float(result.stdout.strip())
            logger.info(f"Audio duration: {duration:.2f} seconds ({duration/60:.1f} minutes)")
            return duration
        else:
            logger.warning(f"Could not determine audio duration for {audio_file_path}")
            return 0.0
            
    except Exception as e:
        logger.warning(f"Error getting audio duration: {str(e)}")
        return 0.0


def find_ffmpeg_path() -> Optional[str]:
    """
    Find FFmpeg executable in PATH or common installation locations.
    
    Returns:
        str: Path to ffmpeg executable, or None if not found.
    """
    # First, try to find in PATH using shutil
    try:
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            logger.info(f"Found FFmpeg in PATH: {ffmpeg_path}")
            return ffmpeg_path
    except Exception as e:
        logger.debug(f"shutil.which failed: {e}")
    
    # On Windows, check WinGet installation location (common)
    if os.name == 'nt':  # Windows
        winget_path = r"C:\Users\{username}\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
        # Replace {username} with actual username
        username = getpass.getuser()
        winget_path = winget_path.replace("{username}", username)
        
        if os.path.exists(winget_path):
            logger.info(f"Found FFmpeg via WinGet: {winget_path}")
            return winget_path
        
        # Try common installation paths
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                logger.info(f"Found FFmpeg at: {path}")
                return path
    
    logger.warning("FFmpeg not found in PATH or common locations")
    return None


def setup_ffmpeg_path() -> None:
    """
    Set up PATH environment variable to include FFmpeg directory.
    
    Raises:
        RuntimeError: If FFmpeg cannot be found.
    """
    # Check if FFmpeg is already in PATH
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
            check=False
        )
        logger.info("FFmpeg is already available in PATH")
        return
    except FileNotFoundError:
        pass
    
    # FFmpeg not in PATH, try to find and add it
    ffmpeg_path = find_ffmpeg_path()
    if not ffmpeg_path:
        raise RuntimeError(
            "FFmpeg not found. Please install it:\n"
            "  Windows: winget install Gyan.FFmpeg\n"
            "  macOS: brew install ffmpeg\n"
            "  Linux: sudo apt-get install ffmpeg"
        )
    
    # Get the directory containing ffmpeg
    ffmpeg_dir = os.path.dirname(ffmpeg_path)
    logger.info(f"Found FFmpeg at: {ffmpeg_path}")
    logger.info(f"FFmpeg directory: {ffmpeg_dir}")
    
    # Add to PATH if not already there
    current_path = os.environ.get("PATH", "")
    if ffmpeg_dir not in current_path:
        os.environ["PATH"] = f"{ffmpeg_dir};{current_path}"
        logger.info(f"Added FFmpeg directory to PATH")
    
    # Verify it works
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
            text=True
        )
        if result.returncode == 0:
            logger.info("FFmpeg verified and working")
        else:
            logger.warning(f"FFmpeg version check returned {result.returncode}")
    except Exception as e:
        logger.error(f"Failed to verify FFmpeg: {str(e)}")
        raise RuntimeError(f"FFmpeg found but failed to execute: {str(e)}")


def check_ffmpeg_available() -> bool:
    """
    Check if FFmpeg is available in PATH or can be located.
    
    Returns:
        bool: True if ffmpeg is found, False otherwise.
    """
    try:
        setup_ffmpeg_path()
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5
        )
        is_available = result.returncode == 0
        if is_available:
            logger.info("FFmpeg check passed: version command successful")
        else:
            logger.warning(f"FFmpeg found but version check failed with code {result.returncode}")
        return is_available
    except RuntimeError as e:
        # FFmpeg path could not be found
        logger.error(f"FFmpeg setup failed: {str(e)}")
        return False
    except FileNotFoundError:
        logger.warning("FFmpeg not found in PATH")
        return False
    except Exception as e:
        logger.warning(f"Error checking FFmpeg: {str(e)}")
        return False


def extract_audio_from_video(video_file_path: str, output_wav_path: str) -> bool:
    """
    Extract audio from video file (MP4, WebM, etc.) to WAV format using FFmpeg.
    
    Args:
        video_file_path: Path to video file
        output_wav_path: Path where WAV audio will be saved
        
    Returns:
        bool: True if extraction successful, False otherwise.
        
    Raises:
        RuntimeError: If FFmpeg is not available or extraction fails.
    """
    if not check_ffmpeg_available():
        raise RuntimeError(
            "FFmpeg is required to process video files but is not installed. "
            "Please install FFmpeg and add it to your PATH, or upload an audio-only file."
        )
    
    try:
        logger.info(f"Extracting audio from video: {video_file_path}")
        cmd = [
            "ffmpeg",
            "-i", video_file_path,
            "-vn",  # No video
            "-acodec", "pcm_s16le",  # PCM audio codec
            "-ar", "16000",  # 16kHz sample rate
            "-ac", "1",  # Mono
            "-y",  # Overwrite output
            output_wav_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=300,  # 5 minute timeout
            text=True
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or "Unknown FFmpeg error"
            logger.error(f"FFmpeg extraction failed: {error_msg}")
            raise RuntimeError(f"Failed to extract audio from video: {error_msg}")
        
        logger.info(f"Audio extracted successfully to: {output_wav_path}")
        return True
        
    except subprocess.TimeoutExpired:
        raise RuntimeError("FFmpeg audio extraction timed out (>5 minutes)")
    except Exception as e:
        logger.error(f"Audio extraction error: {str(e)}")
        raise RuntimeError(f"Failed to extract audio: {str(e)}") from e


def validate_audio_file(file_path: str) -> bool:
    """
    Validate if the audio file exists and is readable.

    Args:
        file_path: Path to the audio file.

    Returns:
        bool: True if file exists and is readable, False otherwise.

    Raises:
        ValueError: If file_path is empty or None.
    """
    if not file_path or not isinstance(file_path, str):
        logger.error(f"Invalid file path type: {type(file_path)}")
        raise ValueError("File path must be a non-empty string")

    file_obj = Path(file_path)
    logger.info(f"Validating file: {file_obj}")
    logger.info(f"File exists: {file_obj.exists()}")
    logger.info(f"Absolute path: {file_obj.resolve()}")

    if not file_obj.exists():
        logger.warning(f"Audio file not found: {file_path}")
        return False

    if not file_obj.is_file():
        logger.warning(f"Path is not a file: {file_path}")
        return False

    # Check if file is readable
    if not os.access(file_obj, os.R_OK):
        logger.warning(f"Audio file is not readable: {file_path}")
        return False

    logger.info(f"File validation passed: {file_path}")
    return True


def transcribe_audio(
    audio_file_path: str,
    model_name: str = "medium",
    language: Optional[str] = None,
) -> dict:
    """
    Transcribe an audio file using OpenAI Whisper model.

    Args:
        audio_file_path: Path to the audio file to transcribe.
        model_name: Whisper model size (tiny, base, small, medium, large).
                   Default: "medium".
        language: Optional ISO 639-1 language code (e.g., "en", "es").
                 If None, language is auto-detected.

    Returns:
        dict: Transcription result containing:
            - "text": Full transcription text
            - "segments": List of segments with timestamps
            - "language": Detected language
            - "model": Model used

    Raises:
        ValueError: If audio file is invalid.
        RuntimeError: If transcription fails.
    """
    logger.info(f"Starting transcription for: {audio_file_path} (model: {model_name})")

    # Set up FFmpeg path before any processing
    try:
        setup_ffmpeg_path()
    except RuntimeError as e:
        logger.error(f"FFmpeg setup failed: {str(e)}")
        raise

    # Validate audio file
    if not validate_audio_file(audio_file_path):
        logger.error(f"Invalid audio file: {audio_file_path}")
        raise ValueError(f"Invalid or missing audio file: {audio_file_path}")

    file_path_obj = Path(audio_file_path)
    file_ext = file_path_obj.suffix.lower()
    audio_to_transcribe = audio_file_path
    temp_wav_file = None

    try:
        # Check if this is a video file that needs audio extraction
        video_formats = {".mp4", ".webm", ".avi", ".mov", ".mkv", ".flv"}
        if file_ext in video_formats:
            logger.info(f"Video file detected ({file_ext}), extracting audio to WAV...")
            # Create temp WAV file in same directory as input
            temp_wav_file = str(file_path_obj.parent / f"temp_audio_{file_path_obj.stem}.wav")
            extract_audio_from_video(audio_file_path, temp_wav_file)
            audio_to_transcribe = temp_wav_file
            logger.info(f"Audio extracted, will transcribe: {audio_to_transcribe}")

        # Get audio duration for progress tracking
        logger.info("Getting audio duration...")
        duration = get_audio_duration(audio_to_transcribe)
        logger.info(f"Audio duration determined: {duration:.1f}s")

        model = _load_model(model_name)

        transcribe_kwargs: dict = {"beam_size": 5}
        if language:
            transcribe_kwargs["language"] = language

        logger.info(f"Transcribing: {audio_to_transcribe}")
        segments_gen, info = model.transcribe(audio_to_transcribe, **transcribe_kwargs)
        segments = [{"start": s.start, "end": s.end, "text": s.text} for s in segments_gen]
        full_text = " ".join(s["text"].strip() for s in segments)

        logger.info(f"Transcription done — language: {info.language}, segments: {len(segments)}")
        return {
            "text": full_text,
            "segments": segments,
            "language": info.language,
            "model": model_name,
            "duration": duration,
        }

    except Exception as e:
        logger.error(f"Transcription failed:\n{traceback.format_exc()}")
        raise RuntimeError(f"Transcription error: {e}") from e
    finally:
        # Clean up temporary WAV file if created
        if temp_wav_file and Path(temp_wav_file).exists():
            try:
                Path(temp_wav_file).unlink()
                logger.info(f"Cleaned up temporary WAV file: {temp_wav_file}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp WAV: {str(e)}")


def format_transcript_with_timestamps(segments: list) -> str:
    """
    Format transcription segments into a readable transcript with timestamps.

    Args:
        segments: List of segment dictionaries from Whisper output.
                 Each segment should have: start, end, text

    Returns:
        str: Formatted transcript with timestamps.

    Raises:
        ValueError: If segments format is invalid.
    """
    logger.info("Formatting transcript with timestamps")

    if not segments or not isinstance(segments, list):
        logger.error(f"Invalid segments format: {type(segments)}")
        raise ValueError("Segments must be a non-empty list")

    try:
        formatted_lines = []

        for segment in segments:
            start = segment.get("start", 0)
            end = segment.get("end", 0)
            text = segment.get("text", "").strip()

            if not text:
                continue

            # Format timestamps as HH:MM:SS
            start_time = _format_timestamp(start)
            end_time = _format_timestamp(end)

            formatted_lines.append(f"[{start_time} - {end_time}] {text}")

        formatted_transcript = "\n".join(formatted_lines)
        logger.info(f"Transcript formatted: {len(formatted_lines)} segments")
        return formatted_transcript

    except Exception as e:
        logger.error(f"Failed to format transcript: {str(e)}")
        raise ValueError(f"Could not format transcript: {str(e)}") from e


def _format_timestamp(seconds: float) -> str:
    """
    Convert seconds to HH:MM:SS format.

    Args:
        seconds: Time in seconds.

    Returns:
        str: Formatted timestamp string.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def save_transcript(
    transcript_text: str,
    output_file_path: str,
    include_metadata: bool = False,
    metadata: Optional[dict] = None,
) -> bool:
    """
    Save transcript to a file.

    Args:
        transcript_text: The transcript text to save.
        output_file_path: Path where the transcript file will be saved.
        include_metadata: If True, prepend metadata to the file.
        metadata: Dictionary containing metadata (title, duration, etc.).

    Returns:
        bool: True if file was saved successfully.

    Raises:
        RuntimeError: If file saving fails.
    """
    logger.info(f"Saving transcript to: {output_file_path}")

    try:
        output_path = Path(output_file_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        content = transcript_text

        if include_metadata and metadata:
            metadata_section = _format_metadata(metadata)
            content = f"{metadata_section}\n\n{transcript_text}"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Transcript saved successfully: {output_file_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to save transcript: {str(e)}")
        raise RuntimeError(f"Could not save transcript: {str(e)}") from e


def _format_metadata(metadata: dict) -> str:
    """
    Format metadata as a header section.

    Args:
        metadata: Dictionary containing metadata.

    Returns:
        str: Formatted metadata string.
    """
    lines = ["=" * 60]
    lines.append("TRANSCRIPT METADATA")
    lines.append("=" * 60)

    for key, value in metadata.items():
        lines.append(f"{key}: {value}")

    lines.append("=" * 60)
    return "\n".join(lines)
