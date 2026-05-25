"""Tests for the transcriber module."""

import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.transcriber import (
    validate_audio_file,
    transcribe_audio,
    format_transcript_with_timestamps,
    save_transcript,
)


class TestValidateAudioFile:
    """Test suite for audio file validation."""

    def test_validate_existing_file(self) -> None:
        """Test validation of an existing audio file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test_audio.mp3"
            file_path.touch()

            assert validate_audio_file(str(file_path)) is True

    def test_validate_nonexistent_file(self) -> None:
        """Test validation of a file that doesn't exist."""
        assert validate_audio_file("/nonexistent/file.mp3") is False

    def test_validate_directory_instead_of_file(self) -> None:
        """Test validation when path is a directory, not a file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            assert validate_audio_file(temp_dir) is False

    def test_validate_empty_string(self) -> None:
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError):
            validate_audio_file("")

    def test_validate_none(self) -> None:
        """Test that None raises ValueError."""
        with pytest.raises(ValueError):
            validate_audio_file(None)

    def test_validate_wrong_type(self) -> None:
        """Test that non-string types raise ValueError."""
        with pytest.raises(ValueError):
            validate_audio_file(12345)


class TestTranscribeAudio:
    """Test suite for audio transcription."""

    @mock.patch("src.transcriber.whisper.load_model")
    def test_transcribe_audio_success(self, mock_load_model) -> None:
        """Test successful audio transcription."""
        # Setup mock model
        mock_model = mock.MagicMock()
        mock_load_model.return_value = mock_model
        mock_model.transcribe.return_value = {
            "text": "This is a test transcript",
            "segments": [
                {
                    "start": 0.0,
                    "end": 5.0,
                    "text": "This is a test",
                }
            ],
            "language": "en",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create dummy audio file
            audio_file = Path(temp_dir) / "test_audio.mp3"
            audio_file.touch()

            result = transcribe_audio(str(audio_file), model_name="tiny")

            assert result["text"] == "This is a test transcript"
            assert result["language"] == "en"
            assert result["model"] == "tiny"
            assert len(result["segments"]) == 1

    def test_transcribe_audio_invalid_file(self) -> None:
        """Test transcription with an invalid audio file."""
        with pytest.raises(ValueError, match="Invalid or missing audio file"):
            transcribe_audio("/nonexistent/file.mp3")

    @mock.patch("src.transcriber.whisper.load_model")
    def test_transcribe_audio_model_load_error(self, mock_load_model) -> None:
        """Test transcription when model loading fails."""
        mock_load_model.side_effect = RuntimeError("Model not found")

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "test_audio.mp3"
            audio_file.touch()

            with pytest.raises(RuntimeError, match="Failed to load Whisper model"):
                transcribe_audio(str(audio_file))

    @mock.patch("src.transcriber.whisper.load_model")
    def test_transcribe_audio_with_language(self, mock_load_model) -> None:
        """Test transcription with specified language."""
        mock_model = mock.MagicMock()
        mock_load_model.return_value = mock_model
        mock_model.transcribe.return_value = {
            "text": "Esto es una prueba",
            "segments": [],
            "language": "es",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "test_audio.mp3"
            audio_file.touch()

            result = transcribe_audio(str(audio_file), language="es")

            assert result["language"] == "es"
            mock_model.transcribe.assert_called_once()


class TestFormatTranscriptWithTimestamps:
    """Test suite for transcript formatting."""

    def test_format_transcript_basic(self) -> None:
        """Test basic transcript formatting with timestamps."""
        segments = [
            {"start": 0.0, "end": 5.5, "text": "Hello world"},
            {"start": 5.5, "end": 10.0, "text": "This is a test"},
        ]

        result = format_transcript_with_timestamps(segments)

        assert "[00:00:00 - 00:00:05]" in result
        assert "Hello world" in result
        assert "[00:00:05 - 00:00:10]" in result
        assert "This is a test" in result

    def test_format_transcript_long_duration(self) -> None:
        """Test formatting with long timestamps."""
        segments = [
            {
                "start": 3661.5,
                "end": 3665.0,
                "text": "Over an hour in",
            }
        ]

        result = format_transcript_with_timestamps(segments)

        assert "[01:01:01 - 01:01:05]" in result
        assert "Over an hour in" in result

    def test_format_transcript_empty_segments(self) -> None:
        """Test formatting with empty segments list."""
        with pytest.raises(ValueError):
            format_transcript_with_timestamps([])

    def test_format_transcript_invalid_format(self) -> None:
        """Test formatting with invalid segment format."""
        with pytest.raises(ValueError):
            format_transcript_with_timestamps("not a list")

    def test_format_transcript_skip_empty_text(self) -> None:
        """Test that segments with empty text are skipped."""
        segments = [
            {"start": 0.0, "end": 5.0, "text": "First part"},
            {"start": 5.0, "end": 10.0, "text": ""},  # Empty text
            {"start": 10.0, "end": 15.0, "text": "Second part"},
        ]

        result = format_transcript_with_timestamps(segments)

        assert "First part" in result
        assert "Second part" in result
        # Should have 2 lines (2 non-empty segments)
        assert len(result.strip().split("\n")) == 2


class TestSaveTranscript:
    """Test suite for transcript file saving."""

    def test_save_transcript_basic(self) -> None:
        """Test basic transcript saving."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "transcript.txt"
            transcript_text = "This is a test transcript"

            result = save_transcript(transcript_text, str(output_file))

            assert result is True
            assert output_file.exists()
            assert output_file.read_text() == transcript_text

    def test_save_transcript_with_metadata(self) -> None:
        """Test transcript saving with metadata."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "transcript.txt"
            transcript_text = "This is a test"
            metadata = {
                "Title": "Test Video",
                "Duration": "10:30",
                "Language": "en",
            }

            result = save_transcript(
                transcript_text,
                str(output_file),
                include_metadata=True,
                metadata=metadata,
            )

            assert result is True
            content = output_file.read_text()
            assert "TRANSCRIPT METADATA" in content
            assert "Test Video" in content
            assert "This is a test" in content

    def test_save_transcript_creates_directory(self) -> None:
        """Test that save_transcript creates missing directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "subdir" / "transcript.txt"
            transcript_text = "Test"

            result = save_transcript(transcript_text, str(output_file))

            assert result is True
            assert output_file.exists()

    def test_save_transcript_permission_error(self) -> None:
        """Test transcript saving when permission is denied."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "transcript.txt"

            with mock.patch(
                "builtins.open",
                side_effect=PermissionError("Access denied"),
            ):
                with pytest.raises(RuntimeError, match="Could not save transcript"):
                    save_transcript("Test", str(output_file))

    def test_save_transcript_utf8_encoding(self) -> None:
        """Test that transcript is saved in UTF-8 encoding."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "transcript.txt"
            transcript_text = "Test with unicode: 你好 мир 🎉"

            save_transcript(transcript_text, str(output_file))

            content = output_file.read_text(encoding="utf-8")
            assert content == transcript_text
