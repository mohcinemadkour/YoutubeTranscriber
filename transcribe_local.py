#!/usr/bin/env python3
"""Transcribe a local file with faster-whisper and print plain text + timing."""
import os
import sys
import time
import subprocess
from pathlib import Path

# Prepend NVIDIA pip-installed CUDA DLL directories to PATH so ctranslate2 finds them
def _add_nvidia_to_path():
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

try:
    import ctranslate2
    device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
except Exception:
    device = "cpu"
compute_type = "float16" if device == "cuda" else "int8"

file_path = sys.argv[1] if len(sys.argv) > 1 else "outputs/videoplayback2.mp4"
file_path = Path(file_path)

if not file_path.exists():
    print(f"ERROR: File not found: {file_path}")
    sys.exit(1)

size_mb = file_path.stat().st_size / (1024 * 1024)
print(f"File      : {file_path}")
print(f"Size      : {size_mb:.1f} MB")
print(f"Device    : {device} ({compute_type})")
print()

# --- Get audio duration ---
def get_duration(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip()) if r.returncode == 0 else 0.0
    except Exception:
        return 0.0

# --- Extract audio if video ---
import tempfile, os

video_exts = {".mp4", ".webm", ".avi", ".mov", ".mkv", ".flv"}
audio_path = str(file_path)
tmp_wav = None

if file_path.suffix.lower() in video_exts:
    tmp_wav = str(file_path.parent / f"_tmp_{file_path.stem}.wav")
    print("Extracting audio from video...")
    t_ext = time.time()
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(file_path), "-vn",
         "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", tmp_wav],
        capture_output=True, timeout=300)
    print(f"Extraction: {time.time()-t_ext:.1f}s")
    audio_path = tmp_wav

duration = get_duration(audio_path)
print(f"Duration  : {duration:.1f}s ({duration/60:.1f} min)")
print()

# --- Load model & transcribe ---
from faster_whisper import WhisperModel

print("Loading model (medium)...")
t_load = time.time()
model = WhisperModel("medium", device=device, compute_type=compute_type)
print(f"Model load: {time.time()-t_load:.1f}s")

print("Transcribing...")
t_trans = time.time()
try:
    segments_gen, info = model.transcribe(audio_path, beam_size=5, language="en")
    segments = [{"start": s.start, "end": s.end, "text": s.text} for s in segments_gen]
except RuntimeError as e:
    if "cublas" in str(e).lower() or "cuda" in str(e).lower():
        print(f"CUDA runtime error ({e}), retrying on CPU/int8...")
        model = WhisperModel("medium", device="cpu", compute_type="int8")
        segments_gen, info = model.transcribe(audio_path, beam_size=5, language="en")
        segments = [{"start": s.start, "end": s.end, "text": s.text} for s in segments_gen]
        device = "cpu"
    else:
        raise
transcribe_time = time.time() - t_trans

# --- Clean up temp file ---
if tmp_wav and Path(tmp_wav).exists():
    os.remove(tmp_wav)

# --- Results ---
print(f"Transcribe: {transcribe_time:.1f}s")
if duration > 0:
    print(f"Speed     : {duration/transcribe_time:.1f}x real-time")
print(f"Language  : {info.language}")
print(f"Segments  : {len(segments)}")
print()
print("=" * 60)
print("TRANSCRIPT (plain text, no timestamps):")
print("=" * 60)
print()

# Join full plain text
plain_text = " ".join(s["text"].strip() for s in segments if s["text"].strip())
print(plain_text)

# --- Save transcript to outputs/ ---
from datetime import datetime
out_dir = Path("outputs")
out_dir.mkdir(exist_ok=True)
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
out_file = out_dir / f"transcript_{file_path.stem}_{timestamp}.txt"
out_file.write_text(plain_text, encoding="utf-8")
print()
print(f"Saved to  : {out_file}")
