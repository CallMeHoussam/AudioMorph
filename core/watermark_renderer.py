"""
Unified 1:1 WYSIWYG Watermark Layer Renderer.

Renders both Text and Image/Logo watermarks onto tight-cropped RGBA canvases
scaled proportionally to the target video's real resolution ``(video_w, video_h)``.
Both the live interactive preview and the FFmpeg export pipeline call this same
module so typography, letter spacing, drop shadows, outlines, background pills,
rotation, opacity, and normalized coordinates match pixel-for-pixel.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from utils.logger import get_logger

log = get_logger(__name__)

# Reference width used to scale pixel-denominated effects (letter spacing,
# outline width, shadow offset, background padding) proportionally across
# 720p, 1080p, 4K, 9:16 portrait, and 1:1 square videos.
REFERENCE_WIDTH = 1920.0

CURATED_FONT_FAMILIES = [
    "Segoe UI",
    "Arial",
    "Bahnschrift",
    "Calibri",
    "Verdana",
    "Tahoma",
    "Trebuchet MS",
    "Georgia",
    "Times New Roman",
    "Garamond",
    "Consolas",
    "Courier New",
    "Impact",
    "Segoe Print",
    "Segoe Script",
]

ANCHOR_KEYS = (
    "top_left",
    "top_center",
    "top_right",
    "center_left",
    "center",
    "center_right",
    "bottom_left",
    "bottom_center",
    "bottom_right",
)

_FONT_INDEX_CACHE: Optional[dict[str, dict[str, str]]] = None


def _font_directories() -> list[Path]:
    """Return platform-specific directories containing TrueType/OpenType fonts."""
    dirs: list[Path] = []
    if sys.platform == "win32":
        win_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        dirs.append(win_dir)
        local_fonts = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"
        if local_fonts.exists():
            dirs.append(local_fonts)
    elif sys.platform == "darwin":
        dirs.extend([
            Path("/System/Library/Fonts"),
            Path("/Library/Fonts"),
            Path.home() / "Library" / "Fonts",
        ])
    else:
        dirs.extend([
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".fonts",
            Path.home() / ".local" / "share" / "fonts",
        ])
    return [d for d in dirs if d.exists()]


def get_font_index() -> dict[str, dict[str, str]]:
    """Scan installed system fonts once and cache ``{family: {style: path}}``."""
    global _FONT_INDEX_CACHE
    if _FONT_INDEX_CACHE is not None:
        return _FONT_INDEX_CACHE

    index: dict[str, dict[str, str]] = {}
    for directory in _font_directories():
        for root, _, files in os.walk(directory):
            for fname in files:
                if not fname.lower().endswith((".ttf", ".otf")):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    font = ImageFont.truetype(fpath, 20)
                    family, style = font.getname()
                    if family:
                        index.setdefault(family, {})[style or "Regular"] = fpath
                except Exception:
                    continue

    _FONT_INDEX_CACHE = index
    log.debug("Indexed %d system font families", len(index))
    return _FONT_INDEX_CACHE


def get_available_font_families(curated_only: bool = False) -> list[str]:
    """Return installed font families with clean curated sans/serif choices first."""
    index = get_font_index()
    if not index:
        return ["Segoe UI", "Arial"]

    curated = [f for f in CURATED_FONT_FAMILIES if f in index]
    if curated_only:
        return curated or sorted(index.keys())[:25]

    rest = sorted(f for f in index.keys() if f not in curated)
    return curated + rest


def parse_hex_color(value: str, fallback: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int, int]:
    """Parse ``#RRGGBB`` or ``#RGB`` into an ``(R, G, B)`` tuple safely."""
    if not isinstance(value, str):
        return fallback
    s = value.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        return fallback
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return fallback


def _resolve_font(family: str, weight: str, size_px: int) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, int]:
    """
    Load a PIL font for *(family, weight, size_px)*.

    Returns ``(font, faux_stroke_px)`` where ``faux_stroke_px > 0`` simulates
    Medium/Bold/ExtraBold cleanly when the font family lacks a dedicated weight file.
    """
    index = get_font_index()
    styles = index.get(family) or index.get("Segoe UI") or index.get("Arial")
    if not styles and index:
        styles = next(iter(index.values()))

    if not styles:
        return ImageFont.load_default(), 0

    def _find_style(keywords: tuple[str, ...]) -> Optional[str]:
        for kw in keywords:
            for sty, path in styles.items():
                if kw.lower() == sty.lower():
                    return path
        for kw in keywords:
            for sty, path in styles.items():
                if kw.lower() in sty.lower() and "italic" not in sty.lower():
                    return path
        return None

    chosen_path: Optional[str] = None
    faux_ratio = 0.0
    w_norm = (weight or "Regular").strip().lower()

    if w_norm == "regular":
        chosen_path = _find_style(("Regular", "Normal", "Book"))
    elif w_norm == "medium":
        chosen_path = _find_style(("Medium", "Semibold", "SemiBold", "Demi"))
        if not chosen_path:
            chosen_path = _find_style(("Regular", "Normal", "Book"))
            faux_ratio = 0.015
    elif w_norm == "bold":
        chosen_path = _find_style(("Bold",))
        if not chosen_path:
            chosen_path = _find_style(("Regular", "Normal", "Book"))
            faux_ratio = 0.032
    elif w_norm in ("extrabold", "extra bold", "black"):
        chosen_path = _find_style(("Black", "ExtraBold", "Extra Bold", "Heavy", "Ultra"))
        if not chosen_path:
            chosen_path = _find_style(("Bold",))
            if chosen_path:
                faux_ratio = 0.025
            else:
                chosen_path = _find_style(("Regular", "Normal", "Book"))
                faux_ratio = 0.052

    if not chosen_path:
        chosen_path = next(iter(styles.values()))

    try:
        font = ImageFont.truetype(chosen_path, size_px)
        # Support variable fonts (e.g. Bahnschrift) when weight variation exists
        if faux_ratio > 0 and hasattr(font, "get_variation_names"):
            try:
                var_names = [
                    v.decode("utf-8", errors="ignore") if isinstance(v, bytes) else str(v)
                    for v in font.get_variation_names()
                ]
                target_kw = {
                    "medium": ("SemiBold", "Medium", "Semibold"),
                    "bold": ("Bold",),
                    "extrabold": ("Bold", "Black", "ExtraBold"),
                }.get(w_norm, ())
                for kw in target_kw:
                    match = next((v for v in var_names if kw.lower() == v.lower()), None)
                    if match:
                        font.set_variation_by_name(match)
                        faux_ratio = 0.0
                        break
            except Exception:
                pass
        faux_px = max(1, round(size_px * faux_ratio)) if faux_ratio > 0 else 0
        return font, faux_px
    except Exception as exc:
        log.warning("Failed to load font %s: %s", chosen_path, exc)
        return ImageFont.load_default(), 0


def _measure_text_line(font, line: str, spacing_px: float) -> tuple[float, list[tuple[float, str]], float, float]:
    """
    Compute horizontal glyph positions and tight horizontal extents for a single line.

    Returns ``(advance_width, [(x_offset, char), ...], min_left_overhang, max_right_extent)``.
    """
    if not line:
        return 0.0, [], 0.0, 0.0

    # When spacing is effectively zero, let Pillow render the full string so
    # kerning and complex scripts (e.g. Arabic shaping) remain intact.
    if abs(spacing_px) < 0.05:
        bbox = font.getbbox(line)
        advance = float(font.getlength(line))
        min_x = float(min(0, bbox[0]))
        max_x = float(max(advance, bbox[2]))
        return advance, [(0.0, line)], min_x, max_x

    positions: list[tuple[float, str]] = []
    cursor = 0.0
    min_x = 0.0
    max_x = 0.0
    last_idx = len(line) - 1
    for i, ch in enumerate(line):
        positions.append((cursor, ch))
        try:
            cb = font.getbbox(ch)
            min_x = min(min_x, cursor + cb[0])
            max_x = max(max_x, cursor + cb[2])
        except Exception:
            pass
        ch_w = float(font.getlength(ch))
        max_x = max(max_x, cursor + ch_w)
        cursor += ch_w
        if i < last_idx:
            cursor += spacing_px
    visual_w = max(1.0, max_x - min_x)
    return visual_w, positions, min_x, max_x


def _apply_opacity(img: Image.Image, opacity_pct: float) -> Image.Image:
    """Multiply the alpha channel of *img* by ``opacity_pct / 100.0``."""
    alpha_scale = max(0.0, min(1.0, float(opacity_pct) / 100.0))
    if alpha_scale >= 0.999:
        return img
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    r, g, b, a = img.split()
    if alpha_scale <= 0.0:
        a = a.point(lambda _: 0)
    else:
        lut = [int(round(i * alpha_scale)) for i in range(256)]
        a = a.point(lut)
    return Image.merge("RGBA", (r, g, b, a))


def _render_text_watermark(config: dict, video_w: int, video_h: int) -> Optional[Image.Image]:
    """Render a styled text watermark into a tight RGBA image at target video scale."""
    raw_text = config.get("text", "")
    if not raw_text or not raw_text.strip():
        return None

    ref_scale = max(0.1, float(video_w) / REFERENCE_WIDTH)
    font_size_pct = max(0.4, min(25.0, float(config.get("font_size_pct", 2.2))))
    font_px = max(8, round(video_w * (font_size_pct / 100.0)))

    font, faux_px = _resolve_font(
        config.get("font_family", "Segoe UI"),
        config.get("font_weight", "Regular"),
        font_px,
    )

    spacing_px = float(config.get("letter_spacing", 0.0)) * ref_scale
    text_rgb = parse_hex_color(config.get("text_color", "#FFFFFF"), (255, 255, 255))
    align = (config.get("text_align", "Center") or "Center").strip().lower()

    outline_on = bool(config.get("outline_enabled", False))
    outline_px = max(1, round(float(config.get("outline_width", 2.0)) * ref_scale)) if outline_on else 0
    outline_rgb = parse_hex_color(config.get("outline_color", "#000000"), (0, 0, 0))

    shadow_on = bool(config.get("shadow_enabled", False))
    shadow_intensity = max(0.0, min(100.0, float(config.get("shadow_intensity", 60)))) / 100.0
    shadow_offset_px = max(1.0, float(config.get("shadow_offset", 4.0)) * ref_scale) if shadow_on else 0.0
    shadow_blur_px = max(1.0, shadow_offset_px * 0.75) if shadow_on else 0.0

    bg_on = bool(config.get("bg_enabled", False))
    bg_rgb = parse_hex_color(config.get("bg_color", "#000000"), (0, 0, 0))
    bg_pad_px = max(2, round(float(config.get("bg_padding", 14.0)) * ref_scale)) if bg_on else 0
    bg_alpha = int(round(255 * max(0.0, min(100.0, float(config.get("bg_opacity", 55)))) / 100.0))

    lines = raw_text.splitlines() or [raw_text]
    try:
        ascent, descent = font.getmetrics()
        line_h = max(font_px, ascent + descent)
    except Exception:
        line_h = max(font_px, int(font_px * 1.25))
    line_gap = max(2, round(font_px * 0.22))

    measured_lines = [_measure_text_line(font, ln, spacing_px) for ln in lines]
    max_line_w = max((m[0] for m in measured_lines), default=1.0)
    block_h = len(lines) * line_h + max(0, len(lines) - 1) * line_gap

    # Compute generous canvas padding so strokes, overhangs, pill & blur never clip
    stroke_pad = outline_px + faux_px + 4
    shadow_pad = int(round(shadow_offset_px + shadow_blur_px * 3.0)) + 4 if shadow_on else 0
    left_overhang = max((max(0.0, -m[2]) for m in measured_lines), default=0.0)
    right_overhang = max((max(0.0, m[3] - m[0]) for m in measured_lines), default=0.0)

    pad_x = int(stroke_pad + bg_pad_px + shadow_pad + left_overhang + right_overhang + 8)
    pad_y = int(stroke_pad + bg_pad_px + shadow_pad + max(6, round(font_px * 0.25)))

    canvas_w = max(8, int(round(max_line_w + pad_x * 2)))
    canvas_h = max(8, int(round(block_h + pad_y * 2)))

    text_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_layer)

    text_origin_x = pad_x + int(round(left_overhang))
    text_origin_y = pad_y

    # Pass 1: Outline stroke across all lines/glyphs so adjacent glyph strokes
    # never overlap glyph interiors when letter spacing is negative.
    if outline_on and outline_px > 0:
        total_stroke = outline_px + faux_px
        for row_idx, (line_w, positions, min_x, _) in enumerate(measured_lines):
            if not positions:
                continue
            if align == "center":
                align_dx = (max_line_w - line_w) / 2.0
            elif align == "right":
                align_dx = max_line_w - line_w
            else:
                align_dx = 0.0
            y_pos = text_origin_y + row_idx * (line_h + line_gap)
            for ch_x, seg in positions:
                draw.text(
                    (text_origin_x + align_dx + ch_x - min_x, y_pos),
                    seg,
                    font=font,
                    fill=(*outline_rgb, 255),
                    stroke_width=total_stroke,
                    stroke_fill=(*outline_rgb, 255),
                )

    # Pass 2: Text fill (with optional faux weight stroke)
    for row_idx, (line_w, positions, min_x, _) in enumerate(measured_lines):
        if not positions:
            continue
        if align == "center":
            align_dx = (max_line_w - line_w) / 2.0
        elif align == "right":
            align_dx = max_line_w - line_w
        else:
            align_dx = 0.0
        y_pos = text_origin_y + row_idx * (line_h + line_gap)
        for ch_x, seg in positions:
            draw.text(
                (text_origin_x + align_dx + ch_x - min_x, y_pos),
                seg,
                font=font,
                fill=(*text_rgb, 255),
                stroke_width=faux_px,
                stroke_fill=(*text_rgb, 255),
            )

    text_bbox = text_layer.getbbox()
    if not text_bbox:
        return None

    composed = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    # Optional Background Pill/Box (drawn behind text & text shadow)
    if bg_on:
        bx0 = max(0, text_bbox[0] - bg_pad_px)
        by0 = max(0, text_bbox[1] - bg_pad_px)
        bx1 = min(canvas_w, text_bbox[2] + bg_pad_px)
        by1 = min(canvas_h, text_bbox[3] + bg_pad_px)
        radius = max(2, int(round(min((bx1 - bx0) * 0.25, (by1 - by0) * 0.35, bg_pad_px * 0.9 + 6))))

        if shadow_on and shadow_intensity > 0:
            box_mask = Image.new("L", (canvas_w, canvas_h), 0)
            bdraw = ImageDraw.Draw(box_mask)
            bdraw.rounded_rectangle([bx0, by0, bx1, by1], radius=radius, fill=255)
            dx = int(round(shadow_offset_px))
            dy = int(round(shadow_offset_px))
            shifted_mask = Image.new("L", (canvas_w, canvas_h), 0)
            shifted_mask.paste(box_mask, (dx, dy))
            blurred_mask = shifted_mask.filter(ImageFilter.GaussianBlur(radius=shadow_blur_px))
            if shadow_intensity < 1.0:
                blurred_mask = blurred_mask.point(lambda p: int(round(p * shadow_intensity)))
            shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            shadow_layer.putalpha(blurred_mask)
            composed = Image.alpha_composite(composed, shadow_layer)

        bg_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(bg_layer)
        bg_draw.rounded_rectangle([bx0, by0, bx1, by1], radius=radius, fill=(*bg_rgb, bg_alpha))
        composed = Image.alpha_composite(composed, bg_layer)
    elif shadow_on and shadow_intensity > 0:
        # Drop shadow behind text
        alpha_mask = text_layer.split()[3]
        dx = int(round(shadow_offset_px))
        dy = int(round(shadow_offset_px))
        shifted_mask = Image.new("L", (canvas_w, canvas_h), 0)
        shifted_mask.paste(alpha_mask, (dx, dy))
        blurred_mask = shifted_mask.filter(ImageFilter.GaussianBlur(radius=shadow_blur_px))
        if shadow_intensity < 1.0:
            blurred_mask = blurred_mask.point(lambda p: int(round(p * shadow_intensity)))
        shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        shadow_layer.putalpha(blurred_mask)
        composed = Image.alpha_composite(composed, shadow_layer)

    composed = Image.alpha_composite(composed, text_layer)

    # Crop tightly before rotation so rotation pivot is centered on visible bounds
    tight_bbox = composed.getbbox()
    if not tight_bbox:
        return None
    composed = composed.crop(tight_bbox)

    # Rotation (UI convention: positive degrees rotate clockwise -> PIL -angle)
    rotation = float(config.get("rotation", 0.0))
    if abs(rotation) > 0.05:
        composed = composed.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=True)

    # Apply master opacity after rotation to preserve smooth anti-aliased edges
    composed = _apply_opacity(composed, float(config.get("opacity", 100)))

    final_bbox = composed.getbbox()
    if final_bbox:
        composed = composed.crop(final_bbox)
    return composed


def _render_image_watermark(config: dict, video_w: int, video_h: int) -> Optional[Image.Image]:
    """Load, scale, rotate, and apply opacity to an image/logo watermark."""
    image_path = (config.get("image_path") or "").strip()
    if not image_path or not os.path.isfile(image_path):
        return None

    try:
        with Image.open(image_path) as src:
            img = ImageOps.exif_transpose(src).convert("RGBA")
    except Exception as exc:
        log.warning("Failed to open watermark image %s: %s", image_path, exc)
        return None

    orig_w, orig_h = img.size
    if orig_w <= 0 or orig_h <= 0:
        return None

    scale_pct = max(1.0, min(95.0, float(config.get("image_scale_pct", 18.0))))
    target_w = max(4, int(round(video_w * (scale_pct / 100.0))))
    target_h = max(4, int(round(target_w * (orig_h / float(orig_w)))))

    img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    rotation = float(config.get("rotation", 0.0))
    if abs(rotation) > 0.05:
        img = img.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=True)

    img = _apply_opacity(img, float(config.get("opacity", 100)))

    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    return img


def render_watermark_rgba(config: dict, video_w: int, video_h: int) -> Optional[Image.Image]:
    """
    Render the active watermark (text or image) at exact target video scale.

    Returns a tight-cropped ``PIL.Image.Image`` in ``RGBA`` mode, or ``None``
    if the watermark currently has no visible content.
    """
    video_w = max(16, int(video_w))
    video_h = max(16, int(video_h))
    wm_type = (config.get("type") or "text").strip().lower()
    if wm_type == "image":
        return _render_image_watermark(config, video_w, video_h)
    return _render_text_watermark(config, video_w, video_h)


def compute_watermark_xy(
    video_w: int,
    video_h: int,
    wm_w: int,
    wm_h: int,
    config: dict,
) -> tuple[int, int]:
    """
    Compute the exact top-left integer ``(x, y)`` placement on ``(video_w, video_h)``.

    - When ``anchor != 'custom'``, snaps cleanly to the 9-point grid respecting
      ``margin_pct`` so edges never touch the frame boundary.
    - When ``anchor == 'custom'``, maps normalized center ``(norm_x, norm_y)``
      in ``[0.0, 1.0]`` proportionally to ``(video_w, video_h)``.
    """
    anchor = (config.get("anchor") or "bottom_right").strip().lower()
    margin = max(0.0, min(40.0, float(config.get("margin_pct", 4.0)))) / 100.0

    if anchor in ANCHOR_KEYS:
        v_pos, h_pos = anchor.split("_", 1) if "_" in anchor else ("center", "center")
        if anchor == "center":
            v_pos, h_pos = "center", "center"

        if h_pos == "left":
            x = margin * video_w
        elif h_pos == "right":
            x = (1.0 - margin) * video_w - wm_w
        else:
            x = (video_w - wm_w) / 2.0

        if v_pos == "top":
            y = margin * video_h
        elif v_pos == "bottom":
            y = (1.0 - margin) * video_h - wm_h
        else:
            y = (video_h - wm_h) / 2.0

        return int(round(x)), int(round(y))

    norm_x = max(0.0, min(1.0, float(config.get("norm_x", 0.5))))
    norm_y = max(0.0, min(1.0, float(config.get("norm_y", 0.5))))
    x = norm_x * video_w - (wm_w / 2.0)
    y = norm_y * video_h - (wm_h / 2.0)
    return int(round(x)), int(round(y))


def xy_to_normalized_center(
    x: float,
    y: float,
    wm_w: float,
    wm_h: float,
    video_w: float,
    video_h: float,
) -> tuple[float, float]:
    """Convert top-left watermark coordinates into normalized center ``(norm_x, norm_y)``."""
    cx = (x + wm_w / 2.0) / max(1.0, float(video_w))
    cy = (y + wm_h / 2.0) / max(1.0, float(video_h))
    return max(0.0, min(1.0, cx)), max(0.0, min(1.0, cy))


def appearance_cache_key(config: dict, video_w: int, video_h: int) -> tuple:
    """Return a hashable key representing all visual attributes except position."""
    wm_type = (config.get("type") or "text").strip().lower()
    if wm_type == "image":
        img_path = (config.get("image_path") or "").strip()
        mtime = 0.0
        if img_path and os.path.isfile(img_path):
            try:
                mtime = os.path.getmtime(img_path)
            except OSError:
                pass
        return (
            "image",
            int(video_w),
            int(video_h),
            img_path,
            mtime,
            round(float(config.get("image_scale_pct", 18.0)), 2),
            round(float(config.get("rotation", 0.0)), 2),
            int(round(float(config.get("opacity", 100)))),
        )

    return (
        "text",
        int(video_w),
        int(video_h),
        config.get("text", ""),
        config.get("font_family", "Segoe UI"),
        round(float(config.get("font_size_pct", 2.2)), 3),
        config.get("font_weight", "Regular"),
        config.get("text_color", "#FFFFFF"),
        round(float(config.get("letter_spacing", 0.0)), 2),
        config.get("text_align", "Center"),
        bool(config.get("shadow_enabled", False)),
        int(round(float(config.get("shadow_intensity", 60)))),
        round(float(config.get("shadow_offset", 4.0)), 2),
        bool(config.get("outline_enabled", False)),
        round(float(config.get("outline_width", 2.0)), 2),
        config.get("outline_color", "#000000"),
        bool(config.get("bg_enabled", False)),
        config.get("bg_color", "#000000"),
        round(float(config.get("bg_padding", 14.0)), 2),
        int(round(float(config.get("bg_opacity", 55)))),
        round(float(config.get("rotation", 0.0)), 2),
        int(round(float(config.get("opacity", 100)))),
    )

