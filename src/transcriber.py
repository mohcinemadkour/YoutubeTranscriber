"""Audio transcription module using OpenAI Whisper."""

import logging
import os
from pathlib import Path
from typing import Optional

import whisper

logger = logging.getLogger(__name__)


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

    # Validate audio file
    if not validate_audio_file(audio_file_path):
        logger.error(f"Invalid audio file: {audio_file_path}")
        raise ValueError(f"Invalid or missing audio file: {audio_file_path}")

    try:
        logger.info(f"Loading Whisper model: {model_name}")
        model = whisper.load_model(model_name)
        logger.info(f"Model loaded successfully: {model_name}")

        # Prepare transcription options
        transcribe_opts = {"language": language} if language else {}

        logger.info("Starting audio transcription...")
        result = model.transcribe(audio_file_path, **transcribe_opts)

        logger.info(
            f"Transcription completed successfully. "
            f"Language: {result.get('language', 'unknown')}, "
            f"Duration: {result.get('duration', 'unknown')}s"
        )

        return {
            "text": result.get("text", ""),
            "segments": result.get("segments", []),
            "language": result.get("language", "unknown"),
            "model": model_name,
        }

    except RuntimeError as e:
        logger.error(f"Whisper model loading failed: {str(e)}")
        raise RuntimeError(f"Failed to load Whisper model: {str(e)}") from e
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        raise RuntimeError(f"Transcription failed: {str(e)}") from e


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
