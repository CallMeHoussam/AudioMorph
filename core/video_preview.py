"""
Memory-efficient video metadata prober, frame extractor, and streaming preview player.

Uses ``ffprobe`` / ``ffmpeg`` stdout pipes (``rawvideo`` / ``rgb24``) scaled
directly to preview dimensions so entire video files are never loaded into RAM
and no temporary image files are created during scrubbing or playback.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from PIL import Image

from utils.config import get_ffmpeg_path, get_ffprobe_path
from utils.logger import get_logger

log = get_logger(__name__)

_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


@dataclass
class VideoInfo:
    """Probed metadata for a video file."""

    filepath: str
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool
    video_codec: str = ""
    audio_codec: str = ""
    valid: bool = True
    error: str = ""


def format_duration(seconds: float) -> str:
    """Format seconds into ``MM:SS`` or ``HH:MM:SS``."""
    total = max(0, int(round(seconds)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _parse_fps(rate_str: str) -> float:
    """Parse an ffprobe rational frame rate like ``30000/1001``."""
    if not rate_str or rate_str == "0/0":
        return 30.0
    if "/" in rate_str:
        num_s, den_s = rate_str.split("/", 1)
        try:
            num, den = float(num_s), float(den_s)
            if den > 0 and num > 0:
                return max(1.0, min(120.0, num / den))
        except ValueError:
            pass
    try:
        val = float(rate_str)
        return max(1.0, min(120.0, val)) if val > 0 else 30.0
    except ValueError:
        return 30.0


def _extract_rotation_degrees(stream: dict) -> int:
    """Extract display rotation (in degrees) from stream tags or side_data_list."""
    tags = stream.get("tags") or {}
    if "rotate" in tags:
        try:
            return int(round(float(tags["rotate"])))
        except (ValueError, TypeError):
            pass

    for sd in stream.get("side_data_list") or []:
        if "rotation" in sd:
            try:
                return int(round(float(sd["rotation"])))
            except (ValueError, TypeError):
                pass
    return 0


def probe_video(filepath: str) -> VideoInfo:
    """Probe video resolution, fps, duration, and audio presence via ``ffprobe``."""
    if not filepath or not os.path.isfile(filepath):
        return VideoInfo(filepath, 0, 0, 30.0, 0.0, False, valid=False, error="File not found")

    ffprobe = get_ffprobe_path()
    if not os.path.exists(ffprobe):
        return VideoInfo(filepath, 0, 0, 30.0, 0.0, False, valid=False, error="ffprobe binary not found")

    cmd = [
        ffprobe,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        filepath,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
            creationflags=_CREATE_NO_WINDOW,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            err_msg = (proc.stderr or "Unreadable or invalid video file").strip().splitlines()[-1] if proc.stderr else "Invalid video file"
            return VideoInfo(filepath, 0, 0, 30.0, 0.0, False, valid=False, error=err_msg)

        data = json.loads(proc.stdout)
        streams = data.get("streams") or []
        fmt = data.get("format") or {}

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        if not video_stream:
            return VideoInfo(filepath, 0, 0, 30.0, 0.0, False, valid=False, error="No video stream found")

        width = int(video_stream.get("width") or 0)
        height = int(video_stream.get("height") or 0)
        if width <= 0 or height <= 0:
            return VideoInfo(filepath, 0, 0, 30.0, 0.0, False, valid=False, error="Invalid video dimensions")

        # Account for smartphone display matrix rotation because FFmpeg auto-rotates on decode
        rot = _extract_rotation_degrees(video_stream)
        if abs(rot) % 180 == 90:
            width, height = height, width

        fps = _parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or "30/1")

        duration = 0.0
        for candidate in (fmt.get("duration"), video_stream.get("duration")):
            if candidate is not None:
                try:
                    d = float(candidate)
                    if d > 0:
                        duration = d
                        break
                except (ValueError, TypeError):
                    pass

        return VideoInfo(
            filepath=filepath,
            width=width,
            height=height,
            fps=fps,
            duration=duration,
            has_audio=audio_stream is not None,
            video_codec=str(video_stream.get("codec_name") or ""),
            audio_codec=str(audio_stream.get("codec_name") or "") if audio_stream else "",
            valid=True,
        )
    except subprocess.TimeoutExpired:
        return VideoInfo(filepath, 0, 0, 30.0, 0.0, False, valid=False, error="Probe timed out")
    except Exception as exc:
        log.warning("probe_video failed for %s: %s", filepath, exc)
        return VideoInfo(filepath, 0, 0, 30.0, 0.0, False, valid=False, error=str(exc))


def extract_preview_frame(
    filepath: str,
    timestamp: float,
    target_w: int,
    target_h: int,
    duration: float = 0.0,
) -> Optional[Image.Image]:
    """
    Extract a single preview frame at *timestamp* scaled to ``(target_w, target_h)``.

    Uses fast keyframe seeking (``-ss`` before ``-i``) and reads raw RGB24 bytes
    directly from FFmpeg stdout.
    """
    if not filepath or not os.path.isfile(filepath):
        return None

    ffmpeg_exe = get_ffmpeg_path()
    if not os.path.exists(ffmpeg_exe):
        return None

    target_w = max(2, int(target_w))
    target_h = max(2, int(target_h))
    seek_t = max(0.0, float(timestamp))
    if duration > 0.1:
        seek_t = min(seek_t, max(0.0, duration - 0.05))

    expected_bytes = target_w * target_h * 3

    def _run_extract(t: float) -> Optional[Image.Image]:
        cmd = [
            ffmpeg_exe,
            "-hide_banner",
            "-loglevel", "error",
            "-ss", f"{t:.3f}",
            "-i", filepath,
            "-frames:v", "1",
            "-vf", f"scale={target_w}:{target_h}:flags=bilinear",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "pipe:1",
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=8,
                creationflags=_CREATE_NO_WINDOW,
            )
            if proc.returncode == 0 and len(proc.stdout) >= expected_bytes:
                raw = proc.stdout[:expected_bytes]
                return Image.frombytes("RGB", (target_w, target_h), raw)
        except Exception as exc:
            log.debug("Frame extract error at %.2fs: %s", t, exc)
        return None

    frame = _run_extract(seek_t)
    if frame is None and seek_t > 0.0:
        # Fallback to start if seeking near EOF returned no frames
        frame = _run_extract(0.0)
    return frame


class VideoPlaybackStream:
    """Streams scaled preview frames via an FFmpeg stdout pipe for Play/Pause."""

    def __init__(
        self,
        filepath: str,
        start_time: float,
        target_w: int,
        target_h: int,
        fps: float,
        on_frame: Callable[[Image.Image, float], None],
        on_eof: Callable[[], None],
    ) -> None:
        self.filepath = filepath
        self.start_time = max(0.0, float(start_time))
        self.target_w = max(2, int(target_w))
        self.target_h = max(2, int(target_h))
        self.stream_fps = max(5.0, min(24.0, float(fps) if fps > 0 else 24.0))
        self.on_frame = on_frame
        self.on_eof = on_eof

        self._stop_event = threading.Event()
        self._process: Optional[subprocess.Popen] = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        proc = self._process
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass

    def _run(self) -> None:
        ffmpeg_exe = get_ffmpeg_path()
        frame_bytes = self.target_w * self.target_h * 3
        frame_interval = 1.0 / self.stream_fps

        cmd = [
            ffmpeg_exe,
            "-hide_banner",
            "-loglevel", "error",
            "-ss", f"{self.start_time:.3f}",
            "-i", self.filepath,
            "-vf", f"fps={self.stream_fps:.2f},scale={self.target_w}:{self.target_h}:flags=bilinear",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "pipe:1",
        ]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=frame_bytes * 2,
                creationflags=_CREATE_NO_WINDOW,
            )
        except Exception as exc:
            log.debug("Failed starting preview stream: %s", exc)
            if not self._stop_event.is_set():
                self.on_eof()
            return

        t_start_wall = time.perf_counter()
        frame_idx = 0
        stdout = self._process.stdout

        try:
            while not self._stop_event.is_set() and stdout is not None:
                buf = bytearray()
                while len(buf) < frame_bytes and not self._stop_event.is_set():
                    chunk = stdout.read(frame_bytes - len(buf))
                    if not chunk:
                        break
                    buf.extend(chunk)

                if len(buf) < frame_bytes or self._stop_event.is_set():
                    break

                img = Image.frombytes("RGB", (self.target_w, self.target_h), bytes(buf))
                current_t = self.start_time + frame_idx * frame_interval

                # Pace playback to real-time wall clock
                target_wall = t_start_wall + frame_idx * frame_interval
                sleep_for = target_wall - time.perf_counter()
                if sleep_for > 0:
                    if self._stop_event.wait(sleep_for):
                        break

                if not self._stop_event.is_set():
                    self.on_frame(img, current_t)
                frame_idx += 1
        except Exception as exc:
            log.debug("Preview stream loop ended: %s", exc)
        finally:
            if self._process is not None:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=1)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
            if not self._stop_event.is_set():
                self.on_eof()

