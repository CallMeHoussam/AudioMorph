"""
Programmatic crisp vector-style icon generator for AudioMorph.

Renders minimalist line and duotone icons at 3x supersampled resolution via
Pillow and downscales with ``Image.Resampling.LANCZOS`` into cached
``ctk.CTkImage`` instances for razor-sharp HiDPI UI rendering.
"""

from __future__ import annotations

import math
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageDraw

from gui.theme import ACCENT_PRIMARY, TEXT_PRIMARY

_ICON_CACHE: dict[tuple[str, int, str, str], ctk.CTkImage] = {}


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    s = (hex_color or "#FFFFFF").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return (248, 250, 252, alpha)
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), alpha)


def _draw_brand(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    # Rounded prism badge with centered audio waveform bars
    p = s * 0.08
    draw.rounded_rectangle([p, p, s - p, s - p], radius=s * 0.24, fill=accent)
    bars = [
        (0.28, 0.40, 0.60),
        (0.42, 0.24, 0.76),
        (0.58, 0.30, 0.70),
        (0.72, 0.42, 0.58),
    ]
    w = max(2, round(s * 0.085))
    for bx, y0, y1 in bars:
        x = s * bx
        draw.line([(x, s * y0), (x, s * y1)], fill=fg, width=w)


def _draw_audio(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.085))
    # Minimalist vertical equalizer waveform
    bars = [
        (0.20, 0.42, 0.58),
        (0.35, 0.26, 0.74),
        (0.50, 0.16, 0.84),
        (0.65, 0.30, 0.70),
        (0.80, 0.40, 0.60),
    ]
    for i, (bx, y0, y1) in enumerate(bars):
        x = s * bx
        col = accent if i in (1, 3) else fg
        draw.line([(x, s * y0), (x, s * y1)], fill=col, width=w)


def _draw_video(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.075))
    draw.rounded_rectangle(
        [s * 0.12, s * 0.18, s * 0.88, s * 0.82],
        radius=s * 0.14,
        outline=fg,
        width=w,
    )
    # Play triangle inside
    tri = [(s * 0.42, s * 0.35), (s * 0.42, s * 0.65), (s * 0.66, s * 0.50)]
    draw.polygon(tri, fill=accent)


def _draw_image(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.075))
    draw.rounded_rectangle(
        [s * 0.14, s * 0.16, s * 0.86, s * 0.84],
        radius=s * 0.14,
        outline=fg,
        width=w,
    )
    # Sun dot
    r = s * 0.08
    draw.ellipse([s * 0.60 - r, s * 0.34 - r, s * 0.60 + r, s * 0.34 + r], fill=accent)
    # Mountain silhouette
    pts = [(s * 0.22, s * 0.74), (s * 0.42, s * 0.48), (s * 0.56, s * 0.62), (s * 0.68, s * 0.52), (s * 0.80, s * 0.74)]
    draw.line(pts, fill=fg, width=w, joint="curve")


def _draw_archive(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.075))
    draw.rounded_rectangle([s * 0.14, s * 0.16, s * 0.86, s * 0.34], radius=s * 0.06, outline=fg, width=w)
    draw.rounded_rectangle([s * 0.20, s * 0.34, s * 0.80, s * 0.84], radius=s * 0.08, outline=fg, width=w)
    draw.line([(s * 0.40, s * 0.52), (s * 0.60, s * 0.52)], fill=accent, width=w)
    draw.line([(s * 0.50, s * 0.34), (s * 0.50, s * 0.52)], fill=accent, width=w)


def _draw_download(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.08))
    # Arrow down
    draw.line([(s * 0.50, s * 0.18), (s * 0.50, s * 0.62)], fill=accent, width=w)
    draw.line([(s * 0.32, s * 0.46), (s * 0.50, s * 0.64), (s * 0.68, s * 0.46)], fill=accent, width=w, joint="curve")
    # Tray
    draw.line([(s * 0.18, s * 0.66), (s * 0.18, s * 0.82), (s * 0.82, s * 0.82), (s * 0.82, s * 0.66)], fill=fg, width=w, joint="curve")


def _draw_watermark(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.075))
    # Outer frame
    draw.rounded_rectangle([s * 0.12, s * 0.18, s * 0.88, s * 0.82], radius=s * 0.12, outline=fg, width=w)
    # Corner signature stamp pill in bottom-right
    draw.rounded_rectangle([s * 0.44, s * 0.54, s * 0.78, s * 0.72], radius=s * 0.06, fill=accent)
    # Diagonal sparkle line
    draw.line([(s * 0.24, s * 0.34), (s * 0.46, s * 0.34)], fill=fg, width=w)


def _draw_cut(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.075))
    r = s * 0.11
    # Scissors handles
    draw.ellipse([s * 0.24 - r, s * 0.32 - r, s * 0.24 + r, s * 0.32 + r], outline=fg, width=w)
    draw.ellipse([s * 0.24 - r, s * 0.68 - r, s * 0.24 + r, s * 0.68 + r], outline=fg, width=w)
    # Blades
    draw.line([(s * 0.33, s * 0.36), (s * 0.80, s * 0.68)], fill=accent, width=w)
    draw.line([(s * 0.33, s * 0.64), (s * 0.80, s * 0.32)], fill=fg, width=w)


def _draw_subtitles(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.075))
    draw.rounded_rectangle([s * 0.12, s * 0.20, s * 0.88, s * 0.78], radius=s * 0.12, outline=fg, width=w)
    draw.line([(s * 0.26, s * 0.42), (s * 0.56, s * 0.42)], fill=accent, width=w)
    draw.line([(s * 0.64, s * 0.42), (s * 0.74, s * 0.42)], fill=fg, width=w)
    draw.line([(s * 0.26, s * 0.58), (s * 0.40, s * 0.58)], fill=fg, width=w)
    draw.line([(s * 0.48, s * 0.58), (s * 0.74, s * 0.58)], fill=accent, width=w)


def _draw_bg_remover(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.075))
    # Magic wand diagonal
    draw.line([(s * 0.20, s * 0.80), (s * 0.62, s * 0.38)], fill=fg, width=w)
    # Four-point sparkle star at tip
    cx, cy, rad = s * 0.70, s * 0.28, s * 0.15
    draw.line([(cx, cy - rad), (cx, cy + rad)], fill=accent, width=w)
    draw.line([(cx - rad, cy), (cx + rad, cy)], fill=accent, width=w)
    # Small accent dot
    dr = s * 0.045
    draw.ellipse([s * 0.34 - dr, s * 0.26 - dr, s * 0.34 + dr, s * 0.26 + dr], fill=accent)


def _draw_vocal(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.075))
    # Mic capsule
    draw.rounded_rectangle([s * 0.38, s * 0.14, s * 0.62, s * 0.54], radius=s * 0.12, outline=fg, width=w)
    # Stand arc
    draw.arc([s * 0.26, s * 0.26, s * 0.74, s * 0.68], start=0, end=180, fill=accent, width=w)
    draw.line([(s * 0.50, s * 0.68), (s * 0.50, s * 0.84)], fill=fg, width=w)
    draw.line([(s * 0.34, s * 0.84), (s * 0.66, s * 0.84)], fill=fg, width=w)


def _draw_ai_tools(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.075))
    cx, cy = s * 0.50, s * 0.50
    r_out, r_in = s * 0.34, s * 0.11
    pts = []
    for i in range(8):
        ang = i * (math.pi / 4.0) - math.pi / 2.0
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + math.cos(ang) * r, cy + math.sin(ang) * r))
    draw.polygon(pts, outline=fg, fill=accent, width=max(1, w // 2))


def _draw_add(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.09))
    draw.line([(s * 0.50, s * 0.22), (s * 0.50, s * 0.78)], fill=fg, width=w)
    draw.line([(s * 0.22, s * 0.50), (s * 0.78, s * 0.50)], fill=fg, width=w)


def _draw_folder(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.075))
    pts = [
        (s * 0.14, s * 0.24),
        (s * 0.42, s * 0.24),
        (s * 0.50, s * 0.34),
        (s * 0.86, s * 0.34),
        (s * 0.86, s * 0.78),
        (s * 0.14, s * 0.78),
    ]
    draw.polygon(pts, outline=fg, width=w)
    draw.line([(s * 0.18, s * 0.44), (s * 0.82, s * 0.44)], fill=accent, width=max(1, w - 1))


def _draw_trash(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.075))
    draw.line([(s * 0.20, s * 0.28), (s * 0.80, s * 0.28)], fill=fg, width=w)
    draw.line([(s * 0.38, s * 0.18), (s * 0.62, s * 0.18)], fill=fg, width=w)
    draw.rounded_rectangle([s * 0.26, s * 0.28, s * 0.74, s * 0.82], radius=s * 0.06, outline=fg, width=w)
    draw.line([(s * 0.42, s * 0.42), (s * 0.42, s * 0.68)], fill=accent, width=w)
    draw.line([(s * 0.58, s * 0.42), (s * 0.58, s * 0.68)], fill=accent, width=w)


def _draw_close(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.09))
    draw.line([(s * 0.26, s * 0.26), (s * 0.74, s * 0.74)], fill=fg, width=w)
    draw.line([(s * 0.74, s * 0.26), (s * 0.26, s * 0.74)], fill=fg, width=w)


def _draw_play(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    tri = [(s * 0.32, s * 0.22), (s * 0.32, s * 0.78), (s * 0.78, s * 0.50)]
    draw.polygon(tri, fill=fg)


def _draw_pause(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.14))
    draw.line([(s * 0.36, s * 0.24), (s * 0.36, s * 0.76)], fill=fg, width=w)
    draw.line([(s * 0.64, s * 0.24), (s * 0.64, s * 0.76)], fill=fg, width=w)


def _draw_export(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.085))
    # Up-right launch arrow inside subtle frame
    draw.line([(s * 0.32, s * 0.68), (s * 0.74, s * 0.26)], fill=fg, width=w)
    draw.line([(s * 0.42, s * 0.26), (s * 0.74, s * 0.26), (s * 0.74, s * 0.58)], fill=fg, width=w, joint="curve")
    draw.line([(s * 0.20, s * 0.80), (s * 0.80, s * 0.80)], fill=accent, width=w)


def _draw_check(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.095))
    draw.line([(s * 0.20, s * 0.52), (s * 0.42, s * 0.74), (s * 0.80, s * 0.28)], fill=fg, width=w, joint="curve")


def _draw_preset(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.075))
    pts = [
        (s * 0.26, s * 0.16),
        (s * 0.74, s * 0.16),
        (s * 0.74, s * 0.84),
        (s * 0.50, s * 0.66),
        (s * 0.26, s * 0.84),
    ]
    draw.polygon(pts, outline=fg, width=w)
    draw.line([(s * 0.38, s * 0.34), (s * 0.62, s * 0.34)], fill=accent, width=w)


def _draw_upload(draw: ImageDraw.ImageDraw, s: int, fg, accent) -> None:
    w = max(2, round(s * 0.08))
    draw.line([(s * 0.50, s * 0.64), (s * 0.50, s * 0.20)], fill=accent, width=w)
    draw.line([(s * 0.32, s * 0.38), (s * 0.50, s * 0.20), (s * 0.68, s * 0.38)], fill=accent, width=w, joint="curve")
    draw.line([(s * 0.18, s * 0.68), (s * 0.18, s * 0.82), (s * 0.82, s * 0.82), (s * 0.82, s * 0.68)], fill=fg, width=w, joint="curve")


_DRAWERS = {
    "brand": _draw_brand,
    "audio": _draw_audio,
    "video": _draw_video,
    "image": _draw_image,
    "archive": _draw_archive,
    "download": _draw_download,
    "watermark": _draw_watermark,
    "cut": _draw_cut,
    "subtitles": _draw_subtitles,
    "bg_remover": _draw_bg_remover,
    "vocal": _draw_vocal,
    "ai_tools": _draw_ai_tools,
    "add": _draw_add,
    "folder": _draw_folder,
    "trash": _draw_trash,
    "clear": _draw_trash,
    "close": _draw_close,
    "play": _draw_play,
    "pause": _draw_pause,
    "export": _draw_export,
    "check": _draw_check,
    "preset": _draw_preset,
    "upload": _draw_upload,
}


def get_icon(
    name: str,
    size: int = 20,
    color: str = TEXT_PRIMARY,
    accent: Optional[str] = None,
) -> ctk.CTkImage:
    """
    Return a cached ``ctk.CTkImage`` rendered at 3x supersampling for *name*.
    """
    accent_col = accent or ACCENT_PRIMARY
    key = (name, int(size), color.lower(), accent_col.lower())
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached

    ss = max(24, int(size) * 3)
    img = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    fg_rgba = _hex_to_rgba(color)
    ac_rgba = _hex_to_rgba(accent_col)
    drawer = _DRAWERS.get(name, _draw_ai_tools)
    drawer(draw, ss, fg_rgba, ac_rgba)

    final_img = img.resize((int(size), int(size)), Image.Resampling.LANCZOS)
    ctk_img = ctk.CTkImage(light_image=final_img, dark_image=final_img, size=(int(size), int(size)))
    _ICON_CACHE[key] = ctk_img
    return ctk_img

