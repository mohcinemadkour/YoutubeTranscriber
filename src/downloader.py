"""YouTube audio downloader module using yt-dlp."""

import logging
import re
from pathlib import Path

import yt_dlp

logger = logging.getLogger(__name__)

# Path to cookies file for authenticated YouTube access
COOKIES_FILE = Path("cookies.txt")


def get_cookies_file() -> Path | None:
    """
    Check if cookies.txt exists for authenticated YouTube access.

    Returns:
        Path: Path to cookies.txt if it exists, None otherwise.
    """
    if COOKIES_FILE.exists():
        logger.info(f"Using authenticated cookies from: {COOKIES_FILE}")
        return COOKIES_FILE
    return None


def validate_youtube_url(url: str) -> bool:
    """
    Validate if the provided URL is a valid YouTube URL.

    Args:
        url: The URL string to validate.

    Returns:
        bool: True if valid YouTube URL, False otherwise.

    Raises:
        ValueError: If URL is empty or None.
    """
    if not url or not isinstance(url, str):
        logger.error(f"Invalid URL type: {type(url)}")
        raise ValueError("URL must be a non-empty string")

    # YouTube URL patterns
    youtube_patterns = [
        r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+",
        r"(?:https?://)?(?:www\.)?youtu\.be/[\w-]+",
        r"(?:https?://)?(?:www\.)?youtube\.com/playlist\?list=[\w-]+",
    ]

    is_valid = any(re.match(pattern, url) for pattern in youtube_patterns)

    if not is_valid:
        logger.warning(f"Invalid YouTube URL format: {url}")

    return is_valid


def download_audio(
    youtube_url: str,
    output_dir: str = "./outputs",
    audio_format: str = "mp3",
) -> tuple[str, str]:
    """
    Download audio from a YouTube video using yt-dlp.

    Args:
        youtube_url: The YouTube video URL.
        output_dir: Directory to save the downloaded audio file.
        audio_format: Audio format to convert to (default: mp3).

    Returns:
        tuple: (audio_file_path, video_title)

    Raises:
        ValueError: If URL is not a valid YouTube URL.
        FileNotFoundError: If output directory does not exist.
        RuntimeError: If download or conversion fails.
    """
    logger.info(f"Starting audio download from: {youtube_url}")

    # Validate URL
    if not validate_youtube_url(youtube_url):
        logger.error(f"Invalid YouTube URL: {youtube_url}")
        raise ValueError(f"Invalid YouTube URL: {youtube_url}")

    # Check output directory exists
    output_path = Path(output_dir)
    if not output_path.exists():
        logger.error(f"Output directory does not exist: {output_dir}")
        raise FileNotFoundError(f"Output directory not found: {output_dir}")

    try:
        # Realistic Chrome User-Agent to bypass simple bot detection
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Configure yt-dlp options with anti-bot protection
        ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": audio_format,
                    "preferredquality": "192",
                }
            ],
            "outtmpl": str(output_path / "%(title)s.%(ext)s"),
            "quiet": False,
            "no_warnings": False,
            "http_headers": {"User-Agent": user_agent},
            "extractor_retries": 3,
            "retries": 5,
            "fragment_retries": 5,
            "sleep_interval": 1,
            "max_sleep_interval": 3,
        }

        # Check for authenticated cookies to bypass YouTube blocking
        cookies_file = get_cookies_file()
        if cookies_file:
            ydl_opts["cookiefile"] = str(cookies_file)
            logger.info("Enabling authenticated YouTube access with cookies")
        else:
            logger.info(
                "No cookies.txt found. To use authenticated access, "
                "export cookies from your browser (see README.md for instructions)."
            )

        logger.info(
            "Using realistic User-Agent and retry mechanisms to bypass bot detection"
        )

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Downloading audio from: {youtube_url}")
            info = ydl.extract_info(youtube_url, download=True)
            video_title = info.get("title", "unknown")
            audio_filename = f"{video_title}.{audio_format}"
            audio_file_path = output_path / audio_filename

            if not audio_file_path.exists():
                logger.error(f"Audio file not created: {audio_file_path}")
                raise RuntimeError(f"Failed to create audio file: {audio_file_path}")

            logger.info(
                f"Successfully downloaded audio: {audio_file_path} "
                f"(Title: {video_title})"
            )
            return str(audio_file_path), video_title

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"yt-dlp download error: {error_msg}")
        if "403" in error_msg or "Forbidden" in error_msg:
            raise RuntimeError(
                "YouTube blocked the download. Try a different video or check your network."
            ) from e
        raise RuntimeError(f"Failed to download audio: {error_msg}") from e
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Unexpected error during audio download: {error_msg}")
        if "403" in error_msg or "Forbidden" in error_msg:
            raise RuntimeError(
                "YouTube blocked the download. Try a different video or check your network."
            ) from e
        raise RuntimeError(f"Audio download failed: {error_msg}") from e


def cleanup_audio_file(file_path: str) -> bool:
    """
    Delete the audio file after processing.

    Args:
        file_path: Path to the audio file to delete.

    Returns:
        bool: True if file was deleted, False if file doesn't exist.

    Raises:
        RuntimeError: If file deletion fails.
    """
    logger.info(f"Cleaning up audio file: {file_path}")

    file_obj = Path(file_path)

    if not file_obj.exists():
        logger.warning(f"Audio file not found for cleanup: {file_path}")
        return False

    try:
        file_obj.unlink()
        logger.info(f"Successfully deleted audio file: {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete audio file: {str(e)}")
        raise RuntimeError(f"Could not delete audio file {file_path}: {str(e)}") from e
