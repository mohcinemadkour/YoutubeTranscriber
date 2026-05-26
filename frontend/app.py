"""Streamlit frontend for YouTube Transcriber application."""

import logging
import os
import time
from typing import Optional

import requests
import streamlit as st

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
API_BASE_URL = os.getenv("API_URL", "http://localhost:8000")
CHECK_STATUS_INTERVAL = 2  # seconds
MAX_RETRIES = 30

# Streamlit page configuration
st.set_page_config(
    page_title="YouTube Transcriber",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        margin-bottom: 2rem;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 1rem;
        border-radius: 0.5rem;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        padding: 1rem;
        border-radius: 0.5rem;
    }
    .info-box {
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        color: #0c5460;
        padding: 1rem;
        border-radius: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def is_api_available() -> bool:
    """
    Check if the FastAPI backend is available.

    Returns:
        bool: True if API is reachable, False otherwise.
    """
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=2)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"API health check failed: {str(e)}")
        return False


def submit_transcription(youtube_url: str, include_metadata: bool) -> Optional[str]:
    """
    Submit a transcription request to the backend.

    Args:
        youtube_url: The YouTube URL to transcribe.
        include_metadata: Whether to include metadata in the transcript.

    Returns:
        str: Job ID if successful, None otherwise.
    """
    try:
        response = requests.post(
            f"{API_BASE_URL}/transcribe",
            json={
                "youtube_url": youtube_url,
                "include_metadata": include_metadata,
            },
            timeout=5,
        )

        if response.status_code == 200:
            data = response.json()
            logger.info(f"Transcription job submitted: {data['job_id']}")
            return data["job_id"]
        else:
            error_detail = response.json().get("detail", "Unknown error")
            logger.error(f"Transcription submission failed: {error_detail}")
            st.error(f"❌ Error: {error_detail}")
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {str(e)}")
        st.error(f"❌ Failed to connect to API: {str(e)}")
        return None


def submit_file_transcription(uploaded_file) -> Optional[str]:
    """
    Submit a file transcription request to the backend.

    Args:
        uploaded_file: Streamlit UploadedFile object.

    Returns:
        str: Job ID if successful, None otherwise.
    """
    try:
        logger.info(f"Submitting file: {uploaded_file.name}, Size: {uploaded_file.size} bytes")
        files = {"file": (uploaded_file.name, uploaded_file.getbuffer())}
        logger.info(f"File buffer size: {len(uploaded_file.getbuffer())} bytes")
        
        response = requests.post(
            f"{API_BASE_URL}/transcribe/file",
            files=files,
            timeout=300,
        )

        if response.status_code == 200:
            data = response.json()
            logger.info(f"File transcription job submitted: {data['job_id']}")
            return data["job_id"]
        else:
            error_detail = response.json().get("detail", "Unknown error")
            logger.error(f"File transcription submission failed: {error_detail}")
            st.error(f"❌ Error: {error_detail}")
            return None

    except requests.exceptions.Timeout:
        logger.error("File upload timed out after 300 seconds")
        st.error("❌ Upload timeout: File took too long to upload. Try a smaller file.")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {str(e)}")
        st.error(f"❌ Failed to connect to API: {str(e)}")
        return None


def get_job_status(job_id: str) -> Optional[dict]:
    """
    Get the status of a transcription job.

    Args:
        job_id: The job ID to check.

    Returns:
        dict: Job status information, or None if failed.
    """
    try:
        response = requests.get(
            f"{API_BASE_URL}/status/{job_id}",
            timeout=5,
        )

        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Failed to get job status: {response.status_code}")
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {str(e)}")
        return None


def list_transcripts() -> list:
    """
    Get a list of available transcript files.

    Returns:
        list: List of transcript files with metadata.
    """
    try:
        response = requests.get(
            f"{API_BASE_URL}/outputs",
            timeout=5,
        )

        if response.status_code == 200:
            return response.json().get("files", [])
        else:
            logger.error(f"Failed to list outputs: {response.status_code}")
            return []

    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {str(e)}")
        return []


def download_transcript(filename: str) -> Optional[bytes]:
    """
    Download a transcript file.

    Args:
        filename: The transcript filename to download.

    Returns:
        bytes: File content, or None if failed.
    """
    try:
        response = requests.get(
            f"{API_BASE_URL}/outputs/{filename}",
            timeout=10,
        )

        if response.status_code == 200:
            return response.content
        else:
            logger.error(f"Failed to download transcript: {response.status_code}")
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {str(e)}")
        return None


def wait_for_completion(job_id: str, progress_bar, status_text) -> Optional[str]:
    """
    Wait for a transcription job to complete with progress updates.

    Args:
        job_id: The job ID to monitor.
        progress_bar: Streamlit progress bar element.
        status_text: Streamlit text element for status updates.

    Returns:
        str: Output filename if successful, None if failed.
    """
    retries = 0

    while retries < MAX_RETRIES:
        job_status = get_job_status(job_id)

        if job_status is None:
            status_text.text("❌ Failed to check job status")
            return None

        status = job_status.get("status")
        message = job_status.get("message", "")
        progress = job_status.get("progress", 0)

        # Update progress bar
        progress_bar.progress(progress / 100)
        status_text.text(f"📊 Status: {message}")

        if status == "completed":
            return job_status.get("output_file")

        elif status == "failed":
            error = job_status.get("error", "Unknown error")
            status_text.text(f"❌ Error: {error}")
            return None

        time.sleep(CHECK_STATUS_INTERVAL)
        retries += 1

    status_text.text("❌ Job timed out")
    return None


def main() -> None:
    """Main Streamlit application."""
    st.markdown(
        '<div class="main-title">🎬 YouTube to Transcript</div>',
        unsafe_allow_html=True,
    )

    # Check API availability
    if not is_api_available():
        st.markdown(
            '<div class="error-box">'
            "❌ <strong>Error:</strong> Cannot connect to the backend API at "
            f"{API_BASE_URL}. Make sure the FastAPI server is running.<br/>"
            "Run: <code>python main.py</code>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        include_metadata = st.checkbox(
            "Include metadata in transcript",
            value=True,
            help="Add title, duration, and language info to the transcript",
        )
        st.markdown("---")
        st.markdown("**About**")
        st.info(
            "Download YouTube videos and transcribe them to text using "
            "OpenAI Whisper. Transcripts include timestamps for easy navigation."
        )

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📥 YouTube URL", "📤 Upload Audio", "📋 History", "ℹ️ About"])

    with tab1:
        st.header("Transcribe a YouTube Video")

        col1, col2 = st.columns([3, 1])

        with col1:
            youtube_url = st.text_input(
                "Enter YouTube URL:",
                placeholder="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                help="Paste a YouTube video or playlist URL",
            )

        with col2:
            submit_button = st.button("🚀 Transcribe", use_container_width=True, key="youtube_transcribe_button")

        if submit_button:
            if not youtube_url:
                st.error("❌ Please enter a YouTube URL")
            else:
                with st.spinner("Submitting transcription request..."):
                    job_id = submit_transcription(youtube_url, include_metadata)

                    if job_id:
                        st.success(f"✅ Job submitted! Job ID: `{job_id}`")

                        # Show progress
                        st.markdown("---")
                        st.subheader("📊 Transcription Progress")

                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        output_file = wait_for_completion(
                            job_id, progress_bar, status_text
                        )

                        if output_file:
                            st.markdown("---")
                            st.success(
                                f"✅ Transcription completed! File: `{output_file}`"
                            )

                            # Download button
                            transcript_content = download_transcript(output_file)
                            if transcript_content:
                                st.download_button(
                                    label="⬇️ Download Transcript",
                                    data=transcript_content,
                                    file_name=output_file,
                                    mime="text/plain",
                                    use_container_width=True,
                                )

                                # Show preview
                                st.markdown("---")
                                st.subheader("👁️ Transcript Preview")
                                content_str = transcript_content.decode("utf-8")
                                lines = content_str.split("\n")[:20]
                                preview = "\n".join(lines)
                                st.text_area(
                                    "First 20 lines:",
                                    preview,
                                    height=250,
                                    disabled=True,
                                )

    with tab2:
        st.header("Transcribe from Audio File")

        st.markdown(
            '<div class="info-box">'
            "<strong>📝 Download Tools:</strong> If YouTube blocks automatic downloads, "
            "manually download audio using:<br>"
            "• <a href='https://www.giststack.com/tools/youtube-video-downloader' target='_blank'><strong>GistStack YouTube Downloader</strong></a><br>"
            "• <a href='https://cobalt.tools' target='_blank'>cobalt.tools</a><br>"
            "Then upload the audio file here."
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown("**Supported formats:** MP3, MP4, WAV, M4A, OGG, WebM, FLAC")
        st.markdown("**Max file size:** 500MB")

        # Use a form to handle file upload more reliably
        with st.form("file_upload_form", clear_on_submit=False):
            uploaded_file = st.file_uploader(
                "Choose an audio or video file",
                type=["mp3", "mp4", "wav", "m4a", "ogg", "webm", "flac"],
                key="form_file_upload"
            )
            
            submit_btn = st.form_submit_button("🚀 Transcribe", use_container_width=True)

        if submit_btn and uploaded_file is not None:
            file_size_mb = uploaded_file.size / (1024 * 1024)
            st.info(f"📁 Uploading: **{uploaded_file.name}** ({file_size_mb:.1f}MB)")
            
            with st.spinner("📤 Uploading... (5 min timeout)"):
                try:
                    # Get bytes directly - NOT buffer
                    file_bytes = uploaded_file.getvalue()
                    logger.info(f"File size: {len(file_bytes)} bytes, name: {uploaded_file.name}")
                    
                    files = {"file": (uploaded_file.name, file_bytes)}
                    logger.info(f"Sending POST to {API_BASE_URL}/transcribe/file")
                    
                    response = requests.post(
                        f"{API_BASE_URL}/transcribe/file",
                        files=files,
                        timeout=300,
                    )
                    logger.info(f"Response status: {response.status_code}")

                    if response.status_code == 200:
                        job_id = response.json()["job_id"]
                        st.success(f"✅ Job submitted! Job ID: `{job_id}`")
                        
                        # Show progress
                        st.markdown("---")
                        st.subheader("📊 Transcription Progress")
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        output_file = wait_for_completion(job_id, progress_bar, status_text)
                        
                        if output_file:
                            st.markdown("---")
                            st.success(f"✅ Transcription completed! File: `{output_file}`")
                            
                            transcript_content = download_transcript(output_file)
                            if transcript_content:
                                st.download_button(
                                    label="⬇️ Download Transcript",
                                    data=transcript_content,
                                    file_name=output_file,
                                    mime="text/plain",
                                    use_container_width=True,
                                )

                                st.markdown("---")
                                st.subheader("👁️ Transcript Preview")
                                content_str = transcript_content.decode("utf-8")
                                lines = content_str.split("\n")[:20]
                                preview = "\n".join(lines)
                                st.text_area(
                                    "First 20 lines:",
                                    preview,
                                    height=250,
                                    disabled=True,
                                )
                    else:
                        error_detail = response.json().get("detail", "Unknown error")
                        st.error(f"❌ Backend error: {error_detail}")
                        logger.error(f"Backend error: {error_detail}")

                except requests.exceptions.Timeout:
                    st.error("❌ Upload timed out after 300 seconds. File too large?")
                    logger.error("Upload timeout")
                except requests.exceptions.ConnectionError as e:
                    st.error(f"❌ Connection error: {str(e)}")
                    logger.error(f"Connection error: {str(e)}")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    logger.error(f"Unexpected error: {str(e)}")
        elif submit_btn and uploaded_file is None:
            st.error("❌ Please select a file first")

    with tab3:
        st.header("📋 Available Transcripts")

        if st.button("🔄 Refresh List"):
            st.rerun()

        transcripts = list_transcripts()

        if not transcripts:
            st.info(
                "📭 No transcripts available yet. Transcribe a video to get started!"
            )
        else:
            # Sort by modified date (newest first)
            transcripts.sort(key=lambda x: x["modified"], reverse=True)

            st.markdown(f"Found **{len(transcripts)}** transcript(s)")

            for transcript in transcripts:
                col1, col2, col3 = st.columns([2, 1, 1])

                with col1:
                    st.text(transcript["filename"])

                with col2:
                    st.text(f"{transcript['size_mb']} MB")

                with col3:
                    if st.button("⬇️", key=transcript["filename"]):
                        with st.spinner("Downloading..."):
                            content = download_transcript(transcript["filename"])
                            if content:
                                st.download_button(
                                    "Save File",
                                    content,
                                    transcript["filename"],
                                    "text/plain",
                                    key=f"download-{transcript['filename']}",
                                )

    with tab4:
        st.header("ℹ️ About YouTube Transcriber")

        st.markdown("""
            ### Features
            - 🎥 Download YouTube videos
            - 🎤 Extract audio automatically
            - 📝 Transcribe with timestamps
            - ⏱️ Monitor progress in real-time
            - 💾 Save and download transcripts

            ### How it Works
            1. Enter a YouTube URL
            2. The app downloads the audio
            3. OpenAI Whisper transcribes it
            4. Get a timestamped transcript

            ### Technology
            - **Backend**: FastAPI
            - **Frontend**: Streamlit
            - **Transcription**: OpenAI Whisper
            - **Download**: yt-dlp

            ### Requirements
            - Python 3.12+
            - FFmpeg (for audio processing)
            - Internet connection

            ### Status
            """)

        # API status indicator
        if is_api_available():
            st.markdown(
                '<div class="success-box">✅ Backend API is running</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="error-box">❌ Backend API is not available</div>',
                unsafe_allow_html=True,
            )


if __name__ == "__main__":
    main()
