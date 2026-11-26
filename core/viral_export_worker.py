"""
Viral Reel Packaging Worker — handles 9:16 re-framing (center crop, blurred background fit,
split screen), dynamic styled ASS caption burning, and single-pass watermark compositing.
"""

from __future__ import annotations

import copy
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from core.online_trimmer import format_seconds
from core.video_preview import probe_video
from core.viral_clipper import SubtitleBlock, ViralClip
from core.watermark_renderer import compute_watermark_xy, render_watermark_rgba
from utils.config import get_ffmpeg_path, get_video_encoder_args, load_settings
from utils.logger import get_logger

log = get_logger(__name__)

_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def sanitize_filename(title: str, max_len: int = 50) -> str:
    """Sanitize title for safe cross-platform filesystem filenames."""
    s = re.sub(r'[\\/*?:"<>|]', "", str(title or "Viral_Clip")).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:max_len] if len(s) > max_len else s


def _format_ass_time(seconds: float) -> str:
    """Format seconds into ASS subtitle timestamp string: H:MM:SS.cs."""
    tot_cs = max(0, int(round(seconds * 100)))
    h = tot_cs // 360000
    rem = tot_cs % 360000
    m = rem // 6000
    rem = rem % 6000
    s = rem // 100
    cs = rem % 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generate_clip_ass_file(
    clip: ViralClip,
    blocks: list[SubtitleBlock],
    style_name: str = "Viral Purple Highlight",
    target_w: int = 1080,
    target_h: int = 1920,
) -> Optional[str]:
    """
    Generate a styled ASS subtitle file for *clip* by rebasing subtitle timestamps
    to 00:00:00 and breaking lines into punchy 3-5 word chunks.
    """
    if not blocks:
        return None

    # Find blocks that overlap with [clip.start_sec, clip.end_sec]
    clip_blocks = [
        b for b in blocks
        if (b.end_sec > clip.start_sec and b.start_sec < clip.end_sec)
    ]
    if not clip_blocks:
        return None

    # Configure style tokens
    margin_v = max(120, int(round(target_h * 0.16)))
    font_size = 50 if target_h >= 1920 else (36 if target_h >= 1080 else 24)

    style_clean = (style_name or "").strip().lower()
    if "yellow" in style_clean:
        font_name = "Impact"
        primary_col = "&H0000FFFF&"   # Vibrant Yellow in BGR hex
        outline_col = "&H00000000&"   # Black stroke
        outline_w = 4.0
        shadow_w = 2.5
    elif "white" in style_clean:
        font_name = "Segoe UI"
        primary_col = "&H00FFFFFF&"   # Crisp White
        outline_col = "&H00000000&"   # Black stroke
        outline_w = 3.5
        shadow_w = 2.0
    else:  # Viral Purple Highlight (default)
        font_name = "Segoe UI"
        primary_col = "&H00D9286D&"   # Royal Purple / Amethyst
        outline_col = "&H00000000&"   # Black stroke
        outline_w = 4.0
        shadow_w = 2.0

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {target_w}
PlayResY: {target_h}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ViralStyle,{font_name},{font_size},{primary_col},&H000000FF&,{outline_col},&H80000000&,-1,0,0,0,100,100,0,0,1,{outline_w},{shadow_w},2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    dialogue_lines: list[str] = []
    for b in clip_blocks:
        rel_start = max(0.0, b.start_sec - clip.start_sec)
        rel_end = min(clip.duration_sec, b.end_sec - clip.start_sec)
        if rel_end <= rel_start:
            continue

        words = b.text.split()
        if len(words) <= 5:
            t_start = _format_ass_time(rel_start)
            t_end = _format_ass_time(rel_end)
            dialogue_lines.append(f"Dialogue: 0,{t_start},{t_end},ViralStyle,,0,0,0,,{b.text}")
        else:
            # Chunk longer sentences into rapid punchy segments
            chunk_size = 4
            num_chunks = (len(words) + chunk_size - 1) // chunk_size
            step = (rel_end - rel_start) / max(1, num_chunks)
            for c_i in range(num_chunks):
                chunk_words = words[c_i * chunk_size : (c_i + 1) * chunk_size]
                c_start = rel_start + c_i * step
                c_end = min(rel_end, rel_start + (c_i + 1) * step)
                t_start = _format_ass_time(c_start)
                t_end = _format_ass_time(c_end)
                phrase = " ".join(chunk_words)
                dialogue_lines.append(f"Dialogue: 0,{t_start},{t_end},ViralStyle,,0,0,0,,{phrase}")

    if not dialogue_lines:
        return None

    full_ass = header + "\n".join(dialogue_lines) + "\n"
    tmp_file = tempfile.NamedTemporaryFile(prefix="audiomorph_ass_", suffix=".ass", delete=False, mode="w", encoding="utf-8")
    tmp_file.write(full_ass)
    tmp_file.close()
    return tmp_file.name


class ViralExportWorker(threading.Thread):
    """
    Background batch worker executing the complete 1-click viral export pipeline:
    precision cutting -> 9:16 re-framing -> dynamic caption burning -> watermark overlay.
    """

    def __init__(
        self,
        source_media: str,
        clips: list[ViralClip],
        subtitle_blocks: list[SubtitleBlock],
        packaging_settings: dict,
        ui_callbacks: dict,
        is_url_source: bool = False,
    ) -> None:
        super().__init__(daemon=True)
        self.source_media = str(source_media).strip()
        self.clips = [c for c in clips if c.included]
        self.subtitle_blocks = list(subtitle_blocks)
        self.settings = dict(packaging_settings)
        self.ui_callbacks = ui_callbacks
        self.is_url_source = is_url_source
        self.is_cancelled = False
        self._current_proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._per_clip_progress = [0] * len(self.clips)

    def cancel(self) -> None:
        self.is_cancelled = True
        with self._lock:
            if self._current_proc is not None:
                try:
                    self._current_proc.terminate()
                except Exception:
                    pass

    def _emit_total_progress(self) -> None:
        if not self.clips:
            return
        tot = int(sum(self._per_clip_progress) / len(self.clips))
        cb = self.ui_callbacks.get("on_total_progress")
        if cb:
            cb(min(100, max(0, tot)))

    def _prepare_local_source_for_clip(self, clip: ViralClip, tmp_dir: str) -> Optional[str]:
        """
        If source is a YouTube/stream URL, download only this clip's range first.
        If source is a local video file, return its path directly.
        """
        if not self.is_url_source:
            return self.source_media if os.path.isfile(self.source_media) else None

        # Download just this section from remote URL
        import yt_dlp
        seg_out = os.path.join(tmp_dir, f"raw_seg_{clip.id}.mp4")

        def _range_func(_info, _ydl):
            return [{"start_time": clip.start_sec, "end_time": clip.end_sec}]

        ydl_opts = {
            "outtmpl": seg_out,
            "download_ranges": _range_func,
            "force_keyframes_at_cuts": True,
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "ffmpeg_location": os.path.dirname(get_ffmpeg_path()),
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.source_media])
            return seg_out if os.path.exists(seg_out) else None
        except Exception as exc:
            log.warning("URL segment download error for clip %s: %s", clip.id, exc)
            return None

    def _export_single_clip(self, idx: int, clip: ViralClip, tmp_dir: str) -> tuple[bool, str]:
        if self.is_cancelled:
            return False, "Cancelled"

        self.ui_callbacks["on_clip_start"](idx, clip)

        # 1. Prepare video source
        local_src = self._prepare_local_source_for_clip(clip, tmp_dir)
        if not local_src or not os.path.isfile(local_src):
            err = "Failed to resolve or download video segment"
            self.ui_callbacks["on_clip_error"](idx, err)
            return False, err

        info = probe_video(local_src)
        src_w = info.width or 1920
        src_h = info.height or 1080

        # Output resolution & framing style
        reframe_mode = self.settings.get("reframe_mode", "Smart Speaker Center (9:16 Crop)")
        is_vertical = "9:16" in reframe_mode
        target_w, target_h = (1080, 1920) if is_vertical else (src_w, src_h)

        # Output path
        out_dir = self.settings.get("output_dir") or str(Path.home() / "Videos" / "AudioMorph_Clips")
        os.makedirs(out_dir, exist_ok=True)
        safe_name = f"{clip.rank:02d}_{sanitize_filename(clip.title)}.mp4"
        out_path = os.path.join(out_dir, safe_name)

        # 2. Build Filtergraph
        filter_parts: list[str] = []
        last_v_tag = "[0:v]"

        # A. Framing filter
        if is_vertical:
            if "blurred" in reframe_mode.lower():
                # Gaussian-blurred zoomed background + sharp 16:9 center
                filter_parts.append(
                    f"{last_v_tag}scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
                    f"{last_v_tag}scale=1080:-2:force_original_aspect_ratio=decrease[fg];"
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v_reframed]"
                )
                last_v_tag = "[v_reframed]"
            elif "split" in reframe_mode.lower():
                # Split Screen top & bottom
                filter_parts.append(
                    f"{last_v_tag}crop=iw:ih*0.62:0:0,scale=1080:960[top];"
                    f"{last_v_tag}crop=iw*0.62:ih*0.5:(iw-ow)/2:ih*0.5,scale=1080:960[bot];"
                    f"[top][bot]vstack[v_reframed]"
                )
                last_v_tag = "[v_reframed]"
            else:
                # Smart Speaker Center crop
                filter_parts.append(f"{last_v_tag}crop=ih*9/16:ih:(iw-ow)/2:0,scale=1080:1920[v_reframed]")
                last_v_tag = "[v_reframed]"
        else:
            # 16:9 Landscape original
            filter_parts.append(f"{last_v_tag}null[v_reframed]")
            last_v_tag = "[v_reframed]"

        # B. Watermark overlay
        tmp_wm_path = None
        wm_preset_name = self.settings.get("watermark_preset") or "None"
        app_cfg = load_settings()
        wm_presets = app_cfg.get("watermark_presets", {})
        if wm_preset_name != "None" and wm_preset_name in wm_presets:
            wm_cfg = wm_presets[wm_preset_name]
            wm_img = render_watermark_rgba(wm_cfg, target_w, target_h)
            if wm_img and wm_img.width > 0 and wm_img.height > 0:
                wx, wy = compute_watermark_xy(target_w, target_h, wm_img.width, wm_img.height, wm_cfg)
                tmp_wm_file = tempfile.NamedTemporaryFile(prefix="audiomorph_wm_clip_", suffix=".png", delete=False)
                tmp_wm_path = tmp_wm_file.name
                tmp_wm_file.close()
                wm_img.save(tmp_wm_path, "PNG")

                filter_parts.append(f"{last_v_tag}[1:v]overlay={wx}:{wy}[v_wm]")
                last_v_tag = "[v_wm]"

        # C. Dynamic Subtitles
        tmp_ass_path = None
        burn_captions = bool(self.settings.get("burn_captions", True))
        if burn_captions and self.subtitle_blocks:
            style_name = self.settings.get("caption_style", "Viral Purple Highlight")
            tmp_ass_path = generate_clip_ass_file(
                clip, self.subtitle_blocks, style_name=style_name, target_w=target_w, target_h=target_h
            )
            if tmp_ass_path:
                esc_ass = tmp_ass_path.replace("\\", "/").replace(":", r"\:")
                filter_parts.append(f"{last_v_tag}ass=filename='{esc_ass}'[v_sub]")
                last_v_tag = "[v_sub]"

        # Final map tag
        filtergraph = ";".join(filter_parts)

        # 3. Construct FFmpeg command (use HW accel if enabled, fallback to libx264 on error)
        ffmpeg_exe = get_ffmpeg_path()
        use_hw = bool(app_cfg.get("hardware_accel", True))
        enc_name, v_enc_args = get_video_encoder_args(use_hw=use_hw, crf=18, preset="medium")

        def _build_clip_cmd(video_args: list[str]) -> list[str]:
            c = [ffmpeg_exe, "-y"]
            if not self.is_url_source:
                c.extend(["-ss", f"{clip.start_sec:.3f}", "-t", f"{clip.duration_sec:.3f}"])
            c.extend(["-i", local_src])
            if tmp_wm_path:
                c.extend(["-i", tmp_wm_path])
            c.extend([
                "-filter_complex", filtergraph,
                "-map", last_v_tag,
                "-map", "0:a:0?",
                *video_args,
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                out_path,
            ])
            return c

        def _run_clip_cmd(cmd: list[str]) -> int:
            log.info("Executing viral clip export: %s", " ".join(cmd[:10]))
            with self._lock:
                self._current_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=_CREATE_NO_WINDOW,
                )

            time_regex = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})")
            if self._current_proc.stdout:
                for line in self._current_proc.stdout:
                    if self.is_cancelled:
                        break
                    m = time_regex.search(line)
                    if m:
                        h, mn, s, cs = map(int, m.groups())
                        cur = h * 3600.0 + mn * 60.0 + s + cs / 100.0
                        pct = min(99, max(1, int((cur / clip.duration_sec) * 100)))
                        self._per_clip_progress[idx] = pct
                        self.ui_callbacks["on_clip_progress"](idx, pct)
                        self._emit_total_progress()

            self._current_proc.wait()
            return self._current_proc.returncode

        try:
            rc = _run_clip_cmd(_build_clip_cmd(v_enc_args))
            if rc != 0 and not self.is_cancelled and enc_name != "libx264":
                log.warning("Hardware encoder %s failed on viral clip; retrying with libx264.", enc_name)
                _, sw_args = get_video_encoder_args(use_hw=False, crf=18, preset="medium")
                rc = _run_clip_cmd(_build_clip_cmd(sw_args))

            if self.is_cancelled or rc != 0 or not os.path.exists(out_path):
                if os.path.exists(out_path):
                    try:
                        os.remove(out_path)
                    except OSError:
                        pass
                msg = "Cancelled" if self.is_cancelled else f"Export failed (exit code {rc})"
                self.ui_callbacks["on_clip_error"](idx, msg)
                return False, msg

            self._per_clip_progress[idx] = 100
            self._emit_total_progress()
            self.ui_callbacks["on_clip_done"](idx, out_path)
            return True, out_dir

        except Exception as exc:
            log.exception("Error exporting clip %s: %s", clip.id, exc)
            self.ui_callbacks["on_clip_error"](idx, str(exc))
            return False, str(exc)
        finally:
            with self._lock:
                self._current_proc = None
            if tmp_wm_path and os.path.exists(tmp_wm_path):
                try:
                    os.remove(tmp_wm_path)
                except OSError:
                    pass
            if tmp_ass_path and os.path.exists(tmp_ass_path):
                try:
                    os.remove(tmp_ass_path)
                except OSError:
                    pass

    def run(self) -> None:
        total = len(self.clips)
        if total == 0:
            self.ui_callbacks.get("on_complete", lambda s: None)({"succeeded": 0, "failed": 0, "dirs": []})
            return

        succeeded = 0
        failed = 0
        output_dirs: list[str] = []

        with tempfile.TemporaryDirectory(prefix="audiomorph_export_") as tmp_dir:
            for idx, clip in enumerate(self.clips):
                if self.is_cancelled:
                    break
                ok, dir_or_err = self._export_single_clip(idx, clip, tmp_dir)
                if ok:
                    succeeded += 1
                    if dir_or_err not in output_dirs:
                        output_dirs.append(dir_or_err)
                else:
                    failed += 1

        self.ui_callbacks.get("on_complete", lambda s: None)({
            "succeeded": succeeded,
            "failed": failed,
            "output_dirs": output_dirs,
            "cancelled": self.is_cancelled,
        })
