"""
Configuration management for AudioMorph.

Reads/writes ``settings.json`` next to the project root.
New default keys are merged automatically on load so upgrades
never lose settings.
"""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)

# ── Resolve project root (works both in source tree and PyInstaller bundle) ──
if hasattr(sys, "_MEIPASS"):
    _PROJECT_ROOT = Path(sys._MEIPASS)
else:
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG_FILE = str(_PROJECT_ROOT / "settings.json")

DEFAULT_EVOLESS_PRESET: dict = {
    "type": "text",
    "text": "evoless.editor",
    "font_family": "Segoe UI",
    "font_size_pct": 2.2,
    "font_weight": "Regular",
    "text_color": "#FFFFFF",
    "letter_spacing": 2.0,
    "text_align": "Center",
    "shadow_enabled": False,
    "shadow_intensity": 60,
    "shadow_offset": 4.0,
    "outline_enabled": False,
    "outline_width": 2.0,
    "outline_color": "#000000",
    "bg_enabled": False,
    "bg_color": "#000000",
    "bg_padding": 14.0,
    "bg_opacity": 55,
    "image_path": "",
    "image_scale_pct": 18.0,
    "opacity": 35,
    "rotation": 0.0,
    "anchor": "bottom_right",
    "margin_pct": 4.0,
    "norm_x": 0.88,
    "norm_y": 0.92,
}

DEFAULT_SETTINGS: dict = {
    "output_format": "mp3",
    "bitrate": "192 kbps",
    "sample_rate": "44100 Hz",
    "channels": "Stereo",
    "normalize_audio": False,
    "fast_stream_copy": False,
    "hardware_accel": True,
    "last_ytdlp_check": 0.0,
    "save_in_source": True,
    "custom_output_dir": "",
    "download_format": "MP4",
    "download_quality": "Best Available",
    "download_output_dir": str(Path.home() / "Downloads"),
    "noplaylist": True,
    "watermark_active_preset": "Evoless Signature",
    "watermark_presets": {
        "Evoless Signature": copy.deepcopy(DEFAULT_EVOLESS_PRESET),
    },
    "watermark_format": "Original (Same as input)",
    "watermark_quality": "High (Visually Lossless / CRF 18)",
    "watermark_save_in_source": True,
    "watermark_output_dir": "",
    "ai_provider": "Google Gemini API (Recommended)",
    "ai_api_key": "",
    "ai_model": "gemini-2.5-flash",
    "ai_custom_endpoint": "http://localhost:11434/v1/chat/completions",
    "viral_target_duration": "Reel/TikTok (30–60s)",
    "viral_clip_count": 5,
    "viral_sentence_guard": True,
    "viral_reframe_mode": "Smart Speaker Center (9:16 Crop)",
    "viral_burn_captions": True,
    "viral_caption_style": "Viral Purple Highlight",
    "viral_watermark_preset": "Evoless Signature",
    "viral_output_dir": "",
    "viral_save_in_source": True,
}


def _merge_defaults(settings: dict) -> dict:
    """Ensure every key from *DEFAULT_SETTINGS* exists in *settings*."""
    merged = {**copy.deepcopy(DEFAULT_SETTINGS), **settings}
    presets = merged.get("watermark_presets")
    if not isinstance(presets, dict) or not presets:
        presets = {"Evoless Signature": copy.deepcopy(DEFAULT_EVOLESS_PRESET)}
    elif "Evoless Signature" not in presets:
        presets = {"Evoless Signature": copy.deepcopy(DEFAULT_EVOLESS_PRESET), **presets}
    # Normalize each preset so newly added keys always have defaults
    normalized_presets = {}
    for name, data in presets.items():
        if isinstance(data, dict):
            normalized_presets[name] = {**copy.deepcopy(DEFAULT_EVOLESS_PRESET), **data}
    merged["watermark_presets"] = normalized_presets
    if merged.get("watermark_active_preset") not in normalized_presets:
        merged["watermark_active_preset"] = next(iter(normalized_presets))
    return merged


def load_settings() -> dict:
    """Load settings from disk, merging any missing defaults."""
    if not os.path.exists(CONFIG_FILE):
        log.info("No settings file found — using defaults.")
        return copy.deepcopy(DEFAULT_SETTINGS)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        log.debug("Loaded settings from %s", CONFIG_FILE)
        return _merge_defaults(data)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to read settings (%s) — using defaults.", exc)
        return copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(settings_dict: dict) -> None:
    """Persist *settings_dict* to disk."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
            json.dump(settings_dict, fh, indent=4)
        log.debug("Settings saved to %s", CONFIG_FILE)
    except OSError as exc:
        log.error("Could not save settings: %s", exc)


def get_ffmpeg_path() -> str:
    """Return the absolute path to ffmpeg binary (cross-platform)."""
    import shutil
    exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    bundled_path = _PROJECT_ROOT / "ffmpeg_engine" / "bin" / exe_name
    if bundled_path.exists():
        return str(bundled_path)

    # Fallback to system FFmpeg in PATH (e.g. brew install ffmpeg on macOS)
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    return str(bundled_path)


def get_ffprobe_path() -> str:
    """Return the absolute path to ffprobe binary (cross-platform)."""
    import shutil
    exe_name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
    bundled_path = _PROJECT_ROOT / "ffmpeg_engine" / "bin" / exe_name
    if bundled_path.exists():
        return str(bundled_path)

    system_ffprobe = shutil.which("ffprobe")
    if system_ffprobe:
        return system_ffprobe

    return str(bundled_path)


def get_ffplay_path() -> Optional[str]:
    """Return the absolute path to ffplay binary if available, else None."""
    import shutil
    exe_name = "ffplay.exe" if sys.platform == "win32" else "ffplay"
    bundled_path = _PROJECT_ROOT / "ffmpeg_engine" / "bin" / exe_name
    if bundled_path.exists():
        return str(bundled_path)

    system_ffplay = shutil.which("ffplay")
    if system_ffplay:
        return system_ffplay

    return None


def get_icon_path() -> str:
    """Return the absolute path to the application icon."""
    return str(_PROJECT_ROOT / "icon.ico")


_HW_ENCODER_UNSET = object()
_HW_ENCODER_CACHE: object = _HW_ENCODER_UNSET


def detect_hardware_h264_encoder(force_refresh: bool = False) -> Optional[str]:
    """
    Probe once (cached in memory) whether bundled FFmpeg supports hardware H.264
    encoding (``h264_nvenc``, ``h264_qsv``, or ``h264_amf``) on this machine.
    Returns the first working encoder name or ``None``.
    """
    global _HW_ENCODER_CACHE
    if _HW_ENCODER_CACHE is not _HW_ENCODER_UNSET and not force_refresh:
        return _HW_ENCODER_CACHE  # type: ignore[return-value]

    ffmpeg_exe = get_ffmpeg_path()
    if not os.path.exists(ffmpeg_exe):
        _HW_ENCODER_CACHE = None
        return None

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        enc_proc = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
            creationflags=creationflags,
        )
        encoders_out = enc_proc.stdout or ""
    except Exception as exc:
        log.debug("Failed querying FFmpeg encoders: %s", exc)
        _HW_ENCODER_CACHE = None
        return None

    for candidate in ("h264_nvenc", "h264_qsv", "h264_amf"):
        if candidate not in encoders_out:
            continue
        try:
            test_proc = subprocess.run(
                [
                    ffmpeg_exe,
                    "-hide_banner",
                    "-loglevel", "error",
                    "-f", "lavfi",
                    "-i", "color=c=black:s=256x256:d=0.05",
                    "-frames:v", "1",
                    "-c:v", candidate,
                    "-f", "null",
                    "-",
                ],
                capture_output=True,
                timeout=4,
                creationflags=creationflags,
            )
            if test_proc.returncode == 0:
                log.info("Detected working hardware H.264 encoder: %s", candidate)
                _HW_ENCODER_CACHE = candidate
                return candidate
        except Exception as exc:
            log.debug("Hardware encoder %s probe failed: %s", candidate, exc)

    _HW_ENCODER_CACHE = None
    return None


def get_video_encoder_args(
    use_hw: bool = True,
    crf: int = 18,
    preset: str = "medium",
) -> tuple[str, list[str]]:
    """
    Return ``(encoder_name, ffmpeg_video_args)`` choosing a verified hardware
    H.264 encoder when *use_hw* is enabled and available, else ``libx264``.
    """
    hw = detect_hardware_h264_encoder() if use_hw else None
    if hw == "h264_nvenc":
        return hw, ["-c:v", "h264_nvenc", "-cq", str(crf), "-preset", "p4", "-pix_fmt", "yuv420p"]
    if hw == "h264_qsv":
        return hw, ["-c:v", "h264_qsv", "-global_quality", str(crf), "-pix_fmt", "yuv420p"]
    if hw == "h264_amf":
        return hw, [
            "-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp",
            "-qp_i", str(crf), "-qp_p", str(crf), "-pix_fmt", "yuv420p",
        ]
    return "libx264", ["-c:v", "libx264", "-crf", str(crf), "-preset", preset, "-pix_fmt", "yuv420p"]
