"""
Online stream trimmer — extracts remote metadata, scrubs frames via FFmpeg HTTP seeking
without full video download, and performs precision frame-accurate segment downloads.
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from utils.config import get_ffmpeg_path, get_ffplay_path, get_video_encoder_args
from utils.logger import get_logger

log = get_logger(__name__)

_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


@dataclass
class StreamMetadata:
    """Probed metadata for a remote video stream."""

    url: str
    title: str = "Online Stream"
    channel: str = ""
    duration: float = 0.0
    thumbnail: str = ""
    resolutions: list[str] = field(default_factory=list)
    stream_url: str = ""
    audio_stream_url: str = ""
    preview_stream_url: str = ""
    preview_audio_url: str = ""
    is_live: bool = False
    raw_info: dict = field(default_factory=dict)
    valid: bool = True
    error: str = ""
    initial_timestamp: Optional[float] = None


def format_seconds(seconds: float) -> str:
    """Convert float seconds to HH:MM:SS or MM:SS string."""
    tot = max(0, int(round(seconds)))
    h = tot // 3600
    m = (tot % 3600) // 60
    s = tot % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_seconds_tenths(seconds: float) -> str:
    """Convert float seconds to HH:MM:SS.d format with tenths of a second."""
    tot = max(0.0, float(seconds))
    h = int(tot) // 3600
    m = (int(tot) % 3600) // 60
    s = int(tot) % 60
    tenths = int(round((tot - int(tot)) * 10)) % 10
    return f"{h:02d}:{m:02d}:{s:02d}.{tenths:d}"


def parse_timestamp_str(time_str: str) -> float:
    """Parse HH:MM:SS, MM:SS, or raw seconds string into float seconds."""
    s = str(time_str).strip()
    if not s:
        return 0.0
    parts = s.split(":")
    try:
        if len(parts) == 3:
            h, m, sec = float(parts[0]), float(parts[1]), float(parts[2])
            return max(0.0, h * 3600.0 + m * 60.0 + sec)
        if len(parts) == 2:
            m, sec = float(parts[0]), float(parts[1])
            return max(0.0, m * 60.0 + sec)
        return max(0.0, float(s))
    except ValueError:
        return 0.0


def extract_url_timestamp(url: str) -> Optional[float]:
    """
    Extract timestamp from URL query parameter 't' or '#t=' or 'start=' if present.
    Supports formats:
    - 8392s or 8392
    - 2h19m52s, 1h30m, 45s
    - 02:19:52 or 15:30
    """
    if not url:
        return None
    m = re.search(r"[?&#](?:t|start)=([0-9hmsHMS:]+)", str(url))
    if not m:
        return None
    val = m.group(1).lower().strip()
    if not val:
        return None
    if ":" in val:
        return parse_timestamp_str(val)
    if val.isdigit():
        return float(val)
    if val.endswith("s") and val[:-1].isdigit():
        return float(val[:-1])
    h_m = re.search(r"(\d+)h", val)
    m_m = re.search(r"(\d+)m", val)
    s_m = re.search(r"(\d+)s", val)
    if h_m or m_m or s_m:
        h = float(h_m.group(1)) if h_m else 0.0
        m_val = float(m_m.group(1)) if m_m else 0.0
        s = float(s_m.group(1)) if s_m else 0.0
        tot = h * 3600.0 + m_val * 60.0 + s
        return tot if tot > 0 else None
    return None


def fetch_remote_thumbnail(thumbnail_url: str, target_w: int = 280, target_h: int = 158) -> Optional[Image.Image]:
    """Fetch video thumbnail image over HTTP as instant preview fallback."""
    if not thumbnail_url:
        return None
    try:
        import urllib.request
        req = urllib.request.Request(
            thumbnail_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = resp.read()
            img = Image.open(io.BytesIO(data)).convert("RGB")
            return img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    except Exception as ex:
        log.debug("Thumbnail fetch fallback failed: %s", ex)
        return None


def fetch_stream_info(url: str, timeout: int = 25) -> StreamMetadata:
    """
    Fetch remote video metadata and direct playable stream URLs using yt-dlp
    without downloading the video file.
    """
    init_t = extract_url_timestamp(url)

    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
        "socket_timeout": timeout,
        "noplaylist": True,
        "playlist_items": "1",
        "extract_flat": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return StreamMetadata(url=url, valid=False, error="No stream info found")

            title = info.get("title") or "Online Stream"
            channel = info.get("uploader") or info.get("channel") or ""
            duration = float(info.get("duration") or 0.0)
            thumbnail = info.get("thumbnail") or ""
            is_live = bool(info.get("is_live", False))

            stream_url = ""
            audio_stream_url = ""

            # Check requested formats (video + audio streams)
            req_formats = info.get("requested_formats") or []
            if req_formats:
                for fmt in req_formats:
                    vcodec = fmt.get("vcodec") or "none"
                    acodec = fmt.get("acodec") or "none"
                    if vcodec != "none" and not stream_url:
                        stream_url = fmt.get("url") or ""
                    if acodec != "none" and not audio_stream_url and vcodec == "none":
                        audio_stream_url = fmt.get("url") or ""

            # Fallback to direct URL attribute on main info
            if not stream_url:
                stream_url = info.get("url") or ""

            # Discover available resolutions
            formats = info.get("formats") or []
            res_set: set[int] = set()
            for f in formats:
                h = f.get("height")
                if isinstance(h, int) and h >= 144:
                    res_set.add(h)
            sorted_res = sorted(list(res_set), reverse=True)
            res_labels = [f"{h}p" for h in sorted_res] if sorted_res else ["1080p", "720p", "480p"]

            # Locate optimal lightweight preview streams (preferring <= 720p progressive or fast video)
            preview_stream_url = ""
            preview_audio_url = ""

            prog_candidates = [
                f for f in formats
                if f.get("vcodec") != "none" and f.get("acodec") != "none" and (f.get("height") or 0) <= 720
                and f.get("url")
            ]
            if prog_candidates:
                prog_candidates.sort(key=lambda x: (x.get("height") or 0), reverse=True)
                preview_stream_url = prog_candidates[0].get("url") or ""
                preview_audio_url = preview_stream_url

            if not preview_stream_url:
                vid_candidates = [
                    f for f in formats
                    if f.get("vcodec") != "none" and (f.get("height") or 0) <= 720 and f.get("url")
                ]
                if vid_candidates:
                    vid_candidates.sort(key=lambda x: (x.get("height") or 0), reverse=True)
                    preview_stream_url = vid_candidates[0].get("url") or ""

            if not preview_audio_url:
                audio_candidates = [
                    f for f in formats
                    if f.get("acodec") != "none" and f.get("vcodec") == "none" and f.get("url")
                ]
                if audio_candidates:
                    audio_candidates.sort(key=lambda x: (x.get("abr") or 0), reverse=True)
                    preview_audio_url = audio_candidates[0].get("url") or ""

            if not preview_stream_url:
                preview_stream_url = stream_url
            if not preview_audio_url:
                preview_audio_url = audio_stream_url or stream_url

            return StreamMetadata(
                url=url,
                title=title,
                channel=channel,
                duration=duration,
                thumbnail=thumbnail,
                resolutions=res_labels,
                stream_url=stream_url,
                audio_stream_url=audio_stream_url,
                preview_stream_url=preview_stream_url,
                preview_audio_url=preview_audio_url,
                is_live=is_live,
                raw_info=info,
                valid=True,
                initial_timestamp=init_t,
            )

    except Exception as exc:
        log.warning("fetch_stream_info error for %s: %s", url, exc)
        return StreamMetadata(url=url, valid=False, error=str(exc))


def extract_remote_frame(
    stream_url: str,
    timestamp: float,
    target_w: int = 560,
    target_h: int = 315,
    timeout: int = 10,
) -> Optional[Image.Image]:
    """
    Extract a single preview frame at *timestamp* from a remote stream URL via FFmpeg.
    Uses HTTP range headers (-ss before -i) to seek immediately without downloading
    the full stream.
    """
    if not stream_url:
        return None

    ffmpeg_exe = get_ffmpeg_path()
    if not os.path.exists(ffmpeg_exe):
        return None

    target_w = max(16, int(target_w))
    target_h = max(16, int(target_h))
    seek_t = max(0.0, float(timestamp))

    def _try_extract(t: float) -> Optional[Image.Image]:
        cmd = [
            ffmpeg_exe,
            "-hide_banner",
            "-loglevel", "error",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-ss", f"{t:.3f}",
            "-i", stream_url,
            "-frames:v", "1",
            "-vf", f"scale={target_w}:{target_h}:flags=bilinear",
            "-q:v", "3",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "pipe:1",
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                creationflags=_CREATE_NO_WINDOW,
            )
            if proc.returncode == 0 and len(proc.stdout) > 100:
                return Image.open(io.BytesIO(proc.stdout)).convert("RGB")
        except Exception as ex:
            log.debug("Remote frame extraction error at %.2fs: %s", t, ex)
        return None

    frame = _try_extract(seek_t)
    if frame is None and seek_t > 0.5:
        # Fallback to stream beginning if seeking near keyframe boundary failed
        frame = _try_extract(0.0)
    return frame


class OnlineStreamPlayer:
    """
    Zero-zombie-process real-time FFmpeg pipe player for remote stream URLs.
    Paces raw RGB24 video frames at 24fps with wall-clock time alignment
    and optional ffplay background audio playback.
    """

    def __init__(
        self,
        width: int = 560,
        height: int = 315,
        fps: int = 24,
        on_frame: Optional[Callable[[Image.Image, float], None]] = None,
        on_state_change: Optional[Callable[[bool], None]] = None,
        on_cut_finished: Optional[Callable[[], None]] = None,
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.frame_size = width * height * 3
        self.on_frame = on_frame
        self.on_state_change = on_state_change
        self.on_cut_finished = on_cut_finished

        self.preview_stream_url: str = ""
        self.preview_audio_url: str = ""
        self.total_duration: float = 0.0

        self.current_time: float = 0.0
        self.is_playing: bool = False
        self.is_previewing_cut: bool = False
        self.preview_until: Optional[float] = None
        self.audio_enabled: bool = True

        self._proc_video: Optional[subprocess.Popen] = None
        self._proc_audio: Optional[subprocess.Popen] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def set_source(self, metadata: StreamMetadata) -> None:
        self.stop()
        self.preview_stream_url = metadata.preview_stream_url or metadata.stream_url
        self.preview_audio_url = metadata.preview_audio_url or metadata.audio_stream_url or self.preview_stream_url
        self.total_duration = max(0.0, float(metadata.duration or 0.0))
        self.current_time = float(metadata.initial_timestamp or 0.0)

    def play(self, from_time: Optional[float] = None, until_time: Optional[float] = None) -> bool:
        if not self.preview_stream_url:
            return False

        with self._lock:
            self._stop_playback_internal()

            if from_time is not None:
                self.current_time = max(0.0, min(self.total_duration, float(from_time)))
            self.preview_until = until_time
            self.is_previewing_cut = (until_time is not None)
            self._stop_event.clear()
            self.is_playing = True

            ffmpeg_exe = get_ffmpeg_path()
            if not os.path.exists(ffmpeg_exe):
                self.is_playing = False
                return False

            cmd = [
                ffmpeg_exe,
                "-hide_banner",
                "-loglevel", "error",
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5",
                "-ss", f"{self.current_time:.3f}",
                "-i", self.preview_stream_url,
                "-vf", f"scale={self.width}:{self.height},fps={self.fps}",
                "-f", "rawvideo",
                "-pix_fmt", "rgb24",
                "pipe:1",
            ]

            try:
                self._proc_video = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=_CREATE_NO_WINDOW,
                    bufsize=self.frame_size * 4,
                )
            except Exception as ex:
                log.warning("Failed to start FFmpeg video stream pipe: %s", ex)
                self.is_playing = False
                return False

            # Audio preview (ffplay) is launched inside _stream_loop once the first
            # video frame finishes HTTP buffering so A/V start in tight sync.
            self._worker_thread = threading.Thread(target=self._stream_loop, daemon=True)
            self._worker_thread.start()

        if self.on_state_change:
            self.on_state_change(True)
        return True

    def _start_ffplay_audio(self, start_ts: float) -> None:
        ffplay_exe = get_ffplay_path()
        if not (ffplay_exe and self.audio_enabled and self.preview_audio_url):
            return
        try:
            audio_cmd = [
                ffplay_exe,
                "-nodisp",
                "-autoexit",
                "-loglevel", "quiet",
                "-ss", f"{start_ts:.3f}",
                self.preview_audio_url,
            ]
            with self._lock:
                if self._stop_event.is_set() or not self.is_playing:
                    return
                self._proc_audio = subprocess.Popen(
                    audio_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=_CREATE_NO_WINDOW,
                )
        except Exception as ex:
            log.debug("ffplay audio preview start failed: %s", ex)

    def _stream_loop(self) -> None:
        start_wall_time: Optional[float] = None
        base_timestamp = self.current_time
        frame_interval = 1.0 / float(self.fps)
        frame_count = 0
        proc = self._proc_video
        frame_size = self.frame_size
        w, h = self.width, self.height
        hit_cut_limit = False

        try:
            while not self._stop_event.is_set() and proc and proc.stdout:
                chunk = proc.stdout.read(frame_size)
                if not chunk or len(chunk) < frame_size:
                    break

                # Sync wall-clock & audio launch to the moment the first video frame arrives
                if start_wall_time is None:
                    start_wall_time = time.monotonic()
                    self._start_ffplay_audio(base_timestamp)

                current_ts = base_timestamp + (frame_count * frame_interval)
                self.current_time = current_ts

                # Check if previewing cut and reached cut end boundary
                if self.preview_until is not None and current_ts >= self.preview_until:
                    hit_cut_limit = True
                    img = Image.frombytes("RGB", (w, h), chunk)
                    if self.on_frame:
                        self.on_frame(img, self.preview_until)
                    break

                img = Image.frombytes("RGB", (w, h), chunk)
                if self.on_frame:
                    self.on_frame(img, current_ts)

                frame_count += 1
                expected_elapsed = frame_count * frame_interval
                actual_elapsed = time.monotonic() - start_wall_time
                sleep_time = expected_elapsed - actual_elapsed
                if sleep_time > 0.001:
                    time.sleep(sleep_time)
        except Exception as ex:
            log.debug("Stream playback loop exception: %s", ex)
        finally:
            with self._lock:
                self._stop_playback_internal()
                self.is_playing = False
                self.is_previewing_cut = False
            if hit_cut_limit and self.on_cut_finished:
                self.on_cut_finished()
            if self.on_state_change:
                self.on_state_change(False)

    def pause(self) -> None:
        with self._lock:
            self._stop_playback_internal()
            self.is_playing = False
            self.is_previewing_cut = False
        if self.on_state_change:
            self.on_state_change(False)

    def stop(self) -> None:
        self.pause()

    def _stop_playback_internal(self) -> None:
        self._stop_event.set()
        if self._proc_video:
            p = self._proc_video
            self._proc_video = None
            try:
                p.terminate()
                p.wait(timeout=0.25)
            except Exception:
                try:
                    p.kill()
                except Exception as exc:
                    log.debug("Video pipe kill failed: %s", exc)

        if self._proc_audio:
            pa = self._proc_audio
            self._proc_audio = None
            try:
                pa.terminate()
                pa.wait(timeout=0.25)
            except Exception:
                try:
                    pa.kill()
                except Exception as exc:
                    log.debug("Audio preview kill failed: %s", exc)

    def seek(self, timestamp: float) -> None:
        timestamp = max(0.0, min(self.total_duration, float(timestamp)))
        was_playing = self.is_playing
        prev_until = self.preview_until if self.is_previewing_cut else None

        if was_playing:
            self.play(from_time=timestamp, until_time=prev_until)
        else:
            self.current_time = timestamp

    def step(self, delta_seconds: float) -> float:
        was_playing = self.is_playing
        if was_playing:
            self.pause()
        new_time = max(0.0, min(self.total_duration, self.current_time + delta_seconds))
        self.current_time = new_time
        return new_time

    def set_audio_enabled(self, enabled: bool) -> None:
        self.audio_enabled = enabled
        if not enabled and self._proc_audio:
            pa = self._proc_audio
            self._proc_audio = None
            try:
                pa.terminate()
            except Exception:
                pass
        elif enabled and self.is_playing and not self._proc_audio and self.preview_audio_url:
            ffplay_exe = get_ffplay_path()
            if ffplay_exe:
                try:
                    audio_cmd = [
                        ffplay_exe,
                        "-nodisp",
                        "-autoexit",
                        "-loglevel", "quiet",
                        "-ss", f"{self.current_time:.3f}",
                        self.preview_audio_url,
                    ]
                    self._proc_audio = subprocess.Popen(
                        audio_cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                        creationflags=_CREATE_NO_WINDOW,
                    )
                except Exception as ex:
                    log.debug("ffplay audio start error: %s", ex)


def download_trimmed_segment(
    url: str,
    start_sec: float,
    end_sec: float,
    settings: Optional[dict] = None,
    progress_callback: Optional[Callable] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    stream_info: Optional[StreamMetadata] = None,
    output_dir: Optional[str] = None,
    format_choice: Optional[str] = None,
    quality_choice: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Download only the requested [start_sec, end_sec] segment of *url*.
    Ensures frame-accurate cuts and audio synchronization without downloading the whole file.
    """
    start_sec = max(0.0, float(start_sec))
    end_sec = max(start_sec + 0.5, float(end_sec))
    duration_clip = end_sec - start_sec

    cfg = settings or {}
    target_out_dir = output_dir or cfg.get("download_output_dir") or str(Path.home() / "Downloads")
    os.makedirs(target_out_dir, exist_ok=True)

    fmt = (format_choice or cfg.get("download_format") or "MP4").lower()
    quality = quality_choice or cfg.get("download_quality") or "Best Available"

    def _report_prog(pct: int, speed: str = "", eta: str = "", status: str = "downloading"):
        if not progress_callback:
            return
        try:
            progress_callback({
                "percent": pct,
                "speed": speed,
                "eta": eta,
                "status": status,
            })
        except TypeError:
            try:
                progress_callback(pct, speed)
            except Exception:
                pass

    # Strategy 1: Direct FFmpeg extraction if stream_info has direct playable URLs
    ffmpeg_exe = get_ffmpeg_path()
    if stream_info and stream_info.stream_url and os.path.exists(ffmpeg_exe):
        safe_title = re.sub(r'[\\/*?:"<>|]', "", stream_info.title).strip() or "Trimmed_Stream"
        out_name = f"{safe_title}_{format_seconds(start_sec).replace(':', '-')}_to_{format_seconds(end_sec).replace(':', '-')}.{fmt}"
        out_path = os.path.join(target_out_dir, out_name)

        use_stream_copy = bool(cfg.get("fast_stream_copy", False))
        use_hw = bool(cfg.get("hardware_accel", True))

        def _build_trim_cmd(stream_copy: bool = False, force_sw: bool = False) -> list[str]:
            c = [ffmpeg_exe, "-y", "-ss", f"{start_sec:.3f}", "-to", f"{end_sec:.3f}", "-i", stream_info.stream_url]
            if stream_info.audio_stream_url and stream_info.audio_stream_url != stream_info.stream_url:
                c.extend(["-ss", f"{start_sec:.3f}", "-to", f"{end_sec:.3f}", "-i", stream_info.audio_stream_url])
                c.extend(["-map", "0:v:0", "-map", "1:a:0?"])
            else:
                c.extend(["-map", "0:v:0", "-map", "0:a:0?"])

            if fmt in ["mp3", "m4a", "wav", "flac"]:
                c.extend(["-vn"])
                if fmt == "mp3":
                    c.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
                elif fmt == "wav":
                    c.extend(["-c:a", "pcm_s16le"])
                else:
                    c.extend(["-c:a", "aac", "-b:a", "192k"])
            elif stream_copy:
                c.extend(["-c", "copy"])
            else:
                _, v_args = get_video_encoder_args(use_hw=(False if force_sw else use_hw), crf=18, preset="fast")
                c.extend([*v_args, "-c:a", "aac", "-b:a", "192k"])
            c.append(out_path)
            return c

        def _run_trim_cmd(c: list[str], mode_label: str) -> int:
            log.info("Running direct stream segment extraction (%s): %s", mode_label, " ".join(c[:8]))
            proc = subprocess.Popen(
                c,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_CREATE_NO_WINDOW,
            )
            time_regex = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})")
            if proc.stdout:
                for line in proc.stdout:
                    if cancel_check and cancel_check():
                        proc.terminate()
                        try:
                            if os.path.exists(out_path):
                                os.remove(out_path)
                        except OSError as exc:
                            log.debug("Failed removing cancelled clip %s: %s", out_path, exc)
                        raise RuntimeError("Download cancelled by user")

                    m = time_regex.search(line)
                    if m and duration_clip > 0:
                        h, mn, s, cs = map(int, m.groups())
                        cur = h * 3600.0 + mn * 60.0 + s + cs / 100.0
                        pct = min(99, max(1, int((cur / duration_clip) * 100)))
                        _report_prog(pct=pct, speed=mode_label, status="trimming")
            proc.wait()
            return proc.returncode

        try:
            is_video_out = fmt not in ["mp3", "m4a", "wav", "flac"]
            rc = 1
            if use_stream_copy and is_video_out:
                rc = _run_trim_cmd(_build_trim_cmd(stream_copy=True), "Stream Copy")
                if rc != 0:
                    log.info("Stream-copy trim failed (exit %d); falling back to re-encode.", rc)

            if rc != 0:
                rc = _run_trim_cmd(_build_trim_cmd(stream_copy=False, force_sw=False), "Direct Stream")
                if rc != 0 and use_hw and is_video_out:
                    rc = _run_trim_cmd(_build_trim_cmd(stream_copy=False, force_sw=True), "Direct Stream SW")

            if rc == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1024:
                _report_prog(pct=100, status="finished")
                return out_name
        except Exception as ex:
            log.warning("Direct FFmpeg stream extraction failed: %s. Falling back to yt-dlp.", ex)

    # Strategy 2: Universal yt-dlp precision download-sections
    import yt_dlp

    def _range_func(_info_dict, _yt_dlp_instance):
        return [{"start_time": start_sec, "end_time": end_sec}]

    def _hook(d):
        if cancel_check and cancel_check():
            raise yt_dlp.utils.DownloadError("Download cancelled by user")
        if d.get("status") == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
            pct = min(99, max(0, int((downloaded / total) * 100)))
            speed = d.get("_speed_str", "")
            eta = d.get("_eta_str", "")
            _report_prog(pct=pct, speed=speed, eta=eta, status="downloading")

    ydl_opts = {
        "outtmpl": os.path.join(target_out_dir, "%(title)s_trimmed_%(id)s.%(ext)s"),
        "download_ranges": _range_func,
        "force_keyframes_at_cuts": True,
        "ffmpeg_location": os.path.dirname(ffmpeg_exe),
        "noplaylist": True,
        "playlist_items": "1",
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [_hook],
    }

    if fmt in ["mp3", "wav", "m4a", "flac"]:
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": fmt if fmt != "m4a" else "aac",
            "preferredquality": "192",
        }]
    else:
        ydl_opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        ydl_opts["merge_output_format"] = fmt

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        res = ydl.extract_info(url, download=True)
        title = (res or {}).get("title") or "Trimmed Stream"
        _report_prog(pct=100, status="finished")
        return f"{title} (Trimmed)"
