"""
AudioMorph Web Server (FastAPI)
Cross-platform, web-based audio & video processing suite.
"""

import os
import sys
import shutil
import tempfile
import uuid
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.config import get_ffmpeg_path
from ffmpeg_engine.engine import FFmpegEngine
from core.downloader import DownloaderEngine

app = FastAPI(title="AudioMorph Web Suite", version="1.0.0")

# Enable CORS for cross-origin access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup directories
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMP_DIR = BASE_DIR / "temp_uploads"
TEMP_DIR.mkdir(exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

def cleanup_file(path: str):
    """Background task to remove temp files after download."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Index HTML not found")
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))

@app.post("/api/convert")
async def convert_media(
    file: UploadFile = File(...),
    output_format: str = Form("mp3"),
    bitrate: str = Form("192 kbps"),
    sample_rate: str = Form("44100 Hz"),
    channels: str = Form("Stereo")
):
    task_id = uuid.uuid4().hex
    original_ext = Path(file.filename).suffix or ".tmp"
    input_path = str(TEMP_DIR / f"input_{task_id}{original_ext}")
    output_filename = f"{Path(file.filename).stem}_converted.{output_format.lower()}"
    output_path = str(TEMP_DIR / f"output_{task_id}.{output_format.lower()}")

    # Save uploaded file
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        engine = FFmpegEngine()
        settings = {
            "output_format": output_format.lower(),
            "bitrate": bitrate,
            "sample_rate": sample_rate,
            "channels": channels,
        }

        # Progress reporting placeholder
        def progress_cb(pct):
            pass

        engine.convert(input_path, output_path, settings, progress_cb)

        if not os.path.exists(output_path):
            raise HTTPException(status_code=500, detail="Conversion failed: output file not created")

        # Cleanup input file immediately
        cleanup_file(input_path)

        return FileResponse(
            path=output_path,
            filename=output_filename,
            media_type="application/octet-stream",
            background=BackgroundTask(cleanup_file, output_path)
        )
    except Exception as exc:
        cleanup_file(input_path)
        cleanup_file(output_path)
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/api/download")
async def download_media(
    url: str = Form(...),
    download_format: str = Form("mp4"),
    quality: str = Form("Best Available")
):
    task_id = uuid.uuid4().hex
    out_dir = TEMP_DIR / f"dl_{task_id}"
    out_dir.mkdir(exist_ok=True)

    try:
        downloader = DownloaderEngine()
        settings = {
            "download_format": download_format,
            "download_quality": quality,
            "download_output_dir": str(out_dir),
            "noplaylist": True,
        }

        def progress_cb(info):
            pass

        title = downloader.download(url, settings, progress_cb)

        # Find downloaded file inside out_dir
        downloaded_files = list(out_dir.rglob("*"))
        media_files = [f for f in downloaded_files if f.is_file() and not f.name.endswith(".tmp")]

        if not media_files:
            raise HTTPException(status_code=500, detail="Downloaded media file not found")

        target_file = media_files[0]
        filename = target_file.name

        return FileResponse(
            path=str(target_file),
            filename=filename,
            media_type="application/octet-stream",
            background=BackgroundTask(shutil.rmtree, str(out_dir), ignore_errors=True)
        )
    except Exception as exc:
        shutil.rmtree(str(out_dir), ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/api/cut")
async def cut_media(
    file: UploadFile = File(...),
    start_time: str = Form("00:00:00"),
    end_time: str = Form("00:00:10")
):
    task_id = uuid.uuid4().hex
    ext = Path(file.filename).suffix or ".mp3"
    input_path = str(TEMP_DIR / f"cut_in_{task_id}{ext}")
    output_filename = f"{Path(file.filename).stem}_trimmed{ext}"
    output_path = str(TEMP_DIR / f"cut_out_{task_id}{ext}")

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        ffmpeg_exe = get_ffmpeg_path()
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        cmd = [
            ffmpeg_exe, "-y",
            "-ss", start_time,
            "-to", end_time,
            "-i", input_path,
            "-c", "copy",
            output_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)
        
        if res.returncode != 0 or not os.path.exists(output_path):
            # Fallback with re-encoding if stream copy fails
            cmd_recode = [
                ffmpeg_exe, "-y",
                "-ss", start_time,
                "-to", end_time,
                "-i", input_path,
                output_path
            ]
            subprocess.run(cmd_recode, check=True, creationflags=creationflags)

        cleanup_file(input_path)
        return FileResponse(
            path=output_path,
            filename=output_filename,
            media_type="application/octet-stream",
            background=BackgroundTask(cleanup_file, output_path)
        )
    except Exception as exc:
        cleanup_file(input_path)
        cleanup_file(output_path)
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/api/subtitles")
async def generate_subtitles(
    file: UploadFile = File(...),
    model: str = Form("small"),
    language: str = Form("ar")
):
    task_id = uuid.uuid4().hex
    ext = Path(file.filename).suffix or ".mp3"
    input_path = str(TEMP_DIR / f"sub_in_{task_id}{ext}")
    out_dir = TEMP_DIR / f"sub_out_{task_id}"
    out_dir.mkdir(exist_ok=True)

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        ffmpeg_exe = get_ffmpeg_path()
        env = os.environ.copy()
        env["PATH"] = f"{os.path.dirname(ffmpeg_exe)}{os.pathsep}{env.get('PATH', '')}"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        cmd = [
            sys.executable, "-m", "whisper", input_path,
            "--model", model,
            "--language", language,
            "--output_dir", str(out_dir),
            "--output_format", "srt"
        ]

        # Add initial prompt for Arabic if applicable
        if language == "ar":
            cmd.extend(["--initial_prompt", "نصوص عربية دقيقة بأسلوب فصيح وواضح."])

        proc = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)
        
        srt_files = list(out_dir.glob("*.srt"))
        if not srt_files:
            error_details = proc.stderr.decode('utf-8', errors='ignore') or "Whisper failed to create subtitles"
            raise HTTPException(status_code=500, detail=f"Subtitle generation failed: {error_details}")

        srt_path = str(srt_files[0])
        output_filename = f"{Path(file.filename).stem}.srt"

        cleanup_file(input_path)
        return FileResponse(
            path=srt_path,
            filename=output_filename,
            media_type="application/x-subrip",
            background=BackgroundTask(shutil.rmtree, str(out_dir), ignore_errors=True)
        )
    except Exception as exc:
        cleanup_file(input_path)
        shutil.rmtree(str(out_dir), ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/api/vocal-isolation")
async def separate_vocals(
    file: UploadFile = File(...),
    target: str = Form("vocals")  # "vocals" or "no_vocals"
):
    task_id = uuid.uuid4().hex
    ext = Path(file.filename).suffix or ".mp3"
    input_path = str(TEMP_DIR / f"voc_in_{task_id}{ext}")
    output_filename = f"{Path(file.filename).stem}_{target}.mp3"
    output_path = str(TEMP_DIR / f"voc_out_{task_id}.mp3")

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        ffmpeg_exe = get_ffmpeg_path()
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        
        # Audio filter highpass/lowpass fallback for vocal extraction/isolation if demucs isn't present
        if target == "vocals":
            # Vocal isolation bandpass filter (human voice ~300Hz-3400Hz)
            af_filter = "highpass=f=200,lowpass=f=3500"
        else:
            # Vocal remover (center channel subtraction)
            af_filter = "pan=stereo|c0=c0-c1|c1=c1-c0"

        cmd = [
            ffmpeg_exe, "-y",
            "-i", input_path,
            "-af", af_filter,
            output_path
        ]
        subprocess.run(cmd, check=True, creationflags=creationflags)

        cleanup_file(input_path)
        return FileResponse(
            path=output_path,
            filename=output_filename,
            media_type="application/octet-stream",
            background=BackgroundTask(cleanup_file, output_path)
        )
    except Exception as exc:
        cleanup_file(input_path)
        cleanup_file(output_path)
        raise HTTPException(status_code=500, detail=str(exc))
