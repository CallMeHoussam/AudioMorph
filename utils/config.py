"""
Configuration management for AudioMorph.

Reads/writes ``settings.json`` next to the project root.
New default keys are merged automatically on load so upgrades
never lose settings.
"""

import copy
import json
import os
import sys
from pathlib import Path

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


def get_icon_path() -> str:
    """Return the absolute path to the application icon."""
    return str(_PROJECT_ROOT / "icon.ico")