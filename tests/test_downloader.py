"""Tests for the downloader module."""

import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.downloader import (
    validate_youtube_url,
    download_audio,
    cleanup_audio_file,
)
from src.utils import build_output_filename, sanitize_filename


class TestValidateYoutubeUrl:
    """Test suite for YouTube URL validation."""

    def test_valid_youtube_watch_url(self) -> None:
        """Test validation of standard YouTube watch URL."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert validate_youtube_url(url) is True

    def test_valid_youtube_short_url(self) -> None:
        """Test validation of shortened YouTube URL."""
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert validate_youtube_url(url) is True

    def test_valid_youtube_playlist_url(self) -> None:
        """Test validation of YouTube playlist URL."""
        url = "https://www.youtube.com/playlist?list=PLxxx"
        assert validate_youtube_url(url) is True

    def test_valid_youtube_url_without_https(self) -> None:
        """Test validation of YouTube URL without https."""
        url = "www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert validate_youtube_url(url) is True

    def test_invalid_url_wrong_domain(self) -> None:
        """Test that non-YouTube URLs are rejected."""
        url = "https://www.example.com/watch?v=dQw4w9WgXcQ"
        assert validate_youtube_url(url) is False

    def test_invalid_url_empty_string(self) -> None:
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError):
            validate_youtube_url("")

    def test_invalid_url_none(self) -> None:
        """Test that None raises ValueError."""
        with pytest.raises(ValueError):
            validate_youtube_url(None)

    def test_invalid_url_wrong_type(self) -> None:
        """Test that non-string types raise ValueError."""
        with pytest.raises(ValueError):
            validate_youtube_url(12345)


class TestDownloadAudio:
    """Test suite for audio download functionality."""

    @mock.patch("src.downloader.yt_dlp.YoutubeDL")
    def test_download_audio_success(self, mock_ydl_class) -> None:
        """Test successful audio download."""
        # Setup mock
        mock_ydl_instance = mock.MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl_instance
        mock_ydl_instance.extract_info.return_value = {
            "title": "Test Video",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create dummy audio file
            audio_file = Path(temp_dir) / "Test Video.mp3"
            audio_file.touch()

            result_path, video_title = download_audio(
                "https://www.youtube.com/watch?v=test",
                output_dir=temp_dir,
            )

            assert video_title == "Test Video"
            assert Path(result_path).exists()

    @mock.patch("src.downloader.yt_dlp.YoutubeDL")
    def test_download_audio_invalid_url(self, mock_ydl_class) -> None:
        """Test download with invalid YouTube URL."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(ValueError, match="Invalid YouTube URL"):
                download_audio(
                    "https://www.example.com/watch?v=test",
                    output_dir=temp_dir,
                )

    def test_download_audio_missing_output_dir(self) -> None:
        """Test download when output directory doesn't exist."""
        with pytest.raises(FileNotFoundError, match="Output directory not found"):
            download_audio(
                "https://www.youtube.com/watch?v=test",
                output_dir="/nonexistent/directory",
            )

    @mock.patch("src.downloader.yt_dlp.YoutubeDL")
    def test_download_audio_yt_dlp_error(self, mock_ydl_class) -> None:
        """Test download when yt-dlp raises an error."""
        import yt_dlp

        mock_ydl_instance = mock.MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl_instance
        mock_ydl_instance.extract_info.side_effect = yt_dlp.utils.DownloadError(
            "Video not found"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(RuntimeError, match="Failed to download audio"):
                download_audio(
                    "https://www.youtube.com/watch?v=nonexistent",
                    output_dir=temp_dir,
                )


class TestCleanupAudioFile:
    """Test suite for audio file cleanup."""

    def test_cleanup_existing_file(self) -> None:
        """Test cleanup of an existing audio file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test_audio.mp3"
            file_path.touch()

            assert file_path.exists()
            result = cleanup_audio_file(str(file_path))

            assert result is True
            assert not file_path.exists()

    def test_cleanup_nonexistent_file(self) -> None:
        """Test cleanup of a file that doesn't exist."""
        result = cleanup_audio_file("/nonexistent/file.mp3")
        assert result is False

    def test_cleanup_file_permission_error(self) -> None:
        """Test cleanup when file cannot be deleted due to permissions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test_audio.mp3"
            file_path.touch()

            with mock.patch("pathlib.Path.unlink", side_effect=PermissionError()):
                with pytest.raises(RuntimeError, match="Could not delete audio file"):
                    cleanup_audio_file(str(file_path))


class TestBuildOutputFilename:
    """Test suite for filename truncation and path length handling."""

    def test_long_title_truncated_to_60_chars(self) -> None:
        """Test that titles longer than 60 chars are truncated."""
        long_title = (
            "This is a very long YouTube video title that "
            "exceeds 60 characters and should be truncated"
        )
        filename = build_output_filename(long_title)
        # Extract the title part (before the timestamp)
        title_part = filename.split("_")[0]
        assert len(title_part) <= 60

    def test_filename_never_exceeds_100_chars(self) -> None:
        """Test that output filename never exceeds 100 characters."""
        long_title = "A" * 200  # Very long title
        filename = build_output_filename(long_title, include_timestamp=True)
        assert len(filename) <= 100, f"Filename too long ({len(filename)} chars): {filename}"

    def test_special_characters_removed(self) -> None:
        """Test that special characters are removed from filenames."""
        title_with_special = 'Video: "Best" <Tutorial> | 2024 (HD)'
        filename = build_output_filename(title_with_special)
        # Check that special characters are gone
        assert '"' not in filename
        assert "<" not in filename
        assert ">" not in filename
        assert "|" not in filename
        assert ":" not in filename

    def test_sanitize_filename_hard_cap_80_chars(self) -> None:
        """Test that sanitize_filename hard caps at specified length."""
        long_title = "B" * 150
        sanitized = sanitize_filename(long_title, max_length=80)
        assert len(sanitized) <= 80

    def test_filename_with_timestamp_format(self) -> None:
        """Test that output filename has correct format with timestamp."""
        title = "Test Video"
        filename = build_output_filename(title, include_timestamp=True)
        # Should be: "Test Video_YYYY-MM-DD_HH-MM-SS.txt"
        assert filename.endswith(".txt")
        assert "_" in filename
        # Check timestamp format (YYYY-MM-DD_HH-MM-SS)
        parts = filename.replace(".txt", "").split("_")
        assert len(parts) >= 2  # Title + timestamp parts

    def test_filename_without_timestamp(self) -> None:
        """Test filename generation without timestamp."""
        title = "Test Video"
        filename = build_output_filename(title, include_timestamp=False)
        assert filename == "Test Video.txt"
        assert len(filename) < 100
