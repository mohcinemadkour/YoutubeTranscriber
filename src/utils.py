"""Utility functions for the YouTube transcriber application."""

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def setup_logger(name: str, log_level: Optional[str] = None) -> logging.Logger:
    """
    Set up and configure a logger instance.

    Args:
        name: Logger name (typically __name__).
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                  If None, uses LOG_LEVEL from .env or defaults to INFO.

    Returns:
        logging.Logger: Configured logger instance.
    """
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Validate log level
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if log_level not in valid_levels:
        log_level = "INFO"

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level))

    # Check if logger already has handlers to avoid duplicates
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """
    Sanitize a filename by removing/replacing invalid characters.

    Args:
        filename: The original filename or title.
        max_length: Maximum length for the filename (default: 200).

    Returns:
        str: Sanitized filename safe for use on all filesystems.

    Raises:
        ValueError: If filename is empty after sanitization.
    """
    if not filename or not isinstance(filename, str):
        raise ValueError("Filename must be a non-empty string")

    # Remove invalid characters (Windows and Unix incompatible)
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized = re.sub(invalid_chars, "", filename).strip()

    # Replace multiple spaces with single space
    sanitized = re.sub(r"\s+", " ", sanitized)

    # Remove leading/trailing dots and spaces (Windows compatibility)
    sanitized = sanitized.rstrip(". ")

    # Truncate to max_length - hard cap at the specified length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip(". ")

    if not sanitized:
        raise ValueError(f"Filename '{filename}' is invalid after sanitization")

    return sanitized


def generate_timestamp() -> str:
    """
    Generate a timestamp string in ISO 8601 format.

    Returns:
        str: Timestamp in format YYYY-MM-DD_HH-MM-SS
    """
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def get_output_directory() -> Path:
    """
    Get the output directory path from environment or use default.

    Returns:
        Path: Output directory path.

    Raises:
        RuntimeError: If output directory cannot be created.
    """
    output_dir = os.getenv("OUTPUT_DIR", "./outputs")
    output_path = Path(output_dir).resolve()

    try:
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path
    except Exception as e:
        raise RuntimeError(f"Failed to create output directory: {str(e)}") from e


def get_whisper_model() -> str:
    """
    Get the Whisper model name from environment.

    Returns:
        str: Whisper model name (tiny, base, small, medium, large).

    Raises:
        ValueError: If model name is invalid.
    """
    model = os.getenv("WHISPER_MODEL", "medium").lower()
    valid_models = ["tiny", "base", "small", "medium", "large"]

    if model not in valid_models:
        raise ValueError(
            f"Invalid Whisper model '{model}'. "
            f"Must be one of: {', '.join(valid_models)}"
        )

    return model


def build_output_filename(
    video_title: str,
    include_timestamp: bool = True,
    extension: str = "txt",
) -> str:
    """
    Build the output filename for a transcript.

    Args:
        video_title: The original YouTube video title.
        include_timestamp: If True, append timestamp to filename.
        extension: File extension (default: txt).

    Returns:
        str: Sanitized output filename, never exceeding 100 characters.

    Raises:
        ValueError: If video_title is invalid.
    """
    if not video_title or not isinstance(video_title, str):
        raise ValueError("Video title must be a non-empty string")

    # Sanitize title and hard cap at 60 chars for the stem
    sanitized_title = sanitize_filename(video_title, max_length=60)

    if include_timestamp:
        timestamp = generate_timestamp()
        # Format: {title_60chars}_{timestamp}.{ext}
        # Total: 60 + 1 + 19 + 1 + 3 = 84 chars max
        filename = f"{sanitized_title}_{timestamp}.{extension}"
    else:
        filename = f"{sanitized_title}.{extension}"

    # Ensure we never exceed 100 chars (Windows safety margin)
    if len(filename) > 100:
        # If timestamp is included, truncate title further
        if include_timestamp:
            timestamp = generate_timestamp()
            # Calculate how much space we have: 100 - len(timestamp) - len("_.txt")
            available = 100 - len(timestamp) - 5
            sanitized_title = sanitize_filename(video_title, max_length=available)
            filename = f"{sanitized_title}_{timestamp}.{extension}"
        else:
            # If no timestamp, just hard truncate to 100
            filename = filename[:100]

    return filename


def file_exists(file_path: str) -> bool:
    """
    Check if a file exists.

    Args:
        file_path: Path to the file.

    Returns:
        bool: True if file exists, False otherwise.
    """
    return Path(file_path).exists()


def get_file_size_mb(file_path: str) -> float:
    """
    Get the size of a file in megabytes.

    Args:
        file_path: Path to the file.

    Returns:
        float: File size in MB.

    Raises:
        FileNotFoundError: If file does not exist.
    """
    file_obj = Path(file_path)

    if not file_obj.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    return file_obj.stat().st_size / (1024 * 1024)
