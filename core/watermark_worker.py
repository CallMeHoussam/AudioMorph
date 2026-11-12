"""
Background batch worker for video watermarking via FFmpeg.

Processes queued videos sequentially (letting ``libx264`` saturate CPU cores
efficiently without memory/disk thrashing), generates a resolution-matched
RGBA watermark PNG per video, invokes ``FFmpegEngine.watermark_video``,
cleans up temporary PNGs in ``finally:``, and supports clean mid-render
cancellation.
"""

from __future__ import annotations

import copy
import os
import tempfile
import threading
from pathlib import Path

from core.video_preview import probe_video
from core.watermark_renderer import compute_watermark_xy, render_watermark_rgba
from ffmpeg_engine.engine import FFmpegEngine
from utils.logger import get_logger

log = get_logger(__name__)

QUALITY_CRF_MAP = {
    "High (Visually Lossless / CRF 18)": 18,
    "Balanced (CRF 21)": 21,
    "Compact (CRF 25)": 25,
}


def resolve_output_path(input_file: str, export_settings: dict) -> Path:
    """Compute a non-destructive output path with ``_watermarked`` suffix."""
    in_path = Path(input_file)
    fmt = (export_settings.get("format") or "Original (Same as input)").strip()
    if fmt.lower().startswith("original"):
        out_ext = in_path.suffix if in_path.suffix else ".mp4"
    else:
        out_ext = f".{fmt.lower()}"

    save_in_source = bool(export_settings.get("save_in_source", True))
    custom_dir = (export_settings.get("custom_output_dir") or "").strip()
    if save_in_source or not custom_dir:
        out_dir = in_path.parent
    else:
        out_dir = Path(custom_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    candidate = out_dir / f"{in_path.stem}_watermarked{out_ext}"
    if candidate.resolve() == in_path.resolve():
        candidate = out_dir / f"{in_path.stem}_watermarked_out{out_ext}"
    return candidate


class WatermarkWorker(threading.Thread):
    """Background thread that exports one or more watermarked videos."""

    def __init__(
        self,
        file_list: list[str],
        watermark_config: dict,
        export_settings: dict,
        ui_callbacks: dict,
    ) -> None:
        super().__init__(daemon=True)
        self.file_list = list(file_list)
        self.watermark_config = copy.deepcopy(watermark_config)
        self.export_settings = dict(export_settings)
        self.ui_callbacks = ui_callbacks
        self.is_cancelled = False
        self._lock = threading.Lock()
        self._active_engine: FFmpegEngine | None = None
        self._per_file_progress = [0] * len(self.file_list)

    def _emit_total_progress(self) -> None:
        if not self.file_list:
            return
        total = int(sum(self._per_file_progress) / len(self.file_list))
        cb = self.ui_callbacks.get("on_total_progress")
        if cb:
            cb(min(100, max(0, total)))

    def _process_single_file(self, index: int, file_path: str) -> tuple[bool, str]:
        """Process one video. Returns ``(success, output_dir_or_error)``."""
        if self.is_cancelled:
            return False, "Cancelled"

        self.ui_callbacks["on_file_start"](index, file_path)
        info = probe_video(file_path)
        if not info.valid:
            err = info.error or "Invalid or corrupted video"
            self.ui_callbacks["on_file_error"](index, err)
            return False, err

        wm_img = render_watermark_rgba(self.watermark_config, info.width, info.height)
        if wm_img is None or wm_img.width <= 0 or wm_img.height <= 0:
            err = "Watermark is empty (no text or image)"
            self.ui_callbacks["on_file_error"](index, err)
            return False, err

        exact_x, exact_y = compute_watermark_xy(
            info.width, info.height, wm_img.width, wm_img.height, self.watermark_config
        )

        out_path = resolve_output_path(file_path, self.export_settings)
        crf = QUALITY_CRF_MAP.get(self.export_settings.get("quality", ""), 18)

        tmp_png = None
        engine = FFmpegEngine()
        with self._lock:
            self._active_engine = engine

        try:
            with tempfile.NamedTemporaryFile(
                prefix="audiomorph_wm_", suffix=".png", delete=False
            ) as tmp:
                tmp_png = tmp.name
            wm_img.save(tmp_png, format="PNG")

            def _on_prog(pct: int) -> None:
                if self.is_cancelled:
                    return
                self._per_file_progress[index] = pct
                self.ui_callbacks["on_progress"](index, pct)
                self._emit_total_progress()

            engine.watermark_video(
                input_file=file_path,
                watermark_png=tmp_png,
                output_file=str(out_path),
                exact_x=exact_x,
                exact_y=exact_y,
                crf=crf,
                has_audio=info.has_audio,
                known_duration=info.duration,
                needs_even_pad=(info.width % 2 != 0 or info.height % 2 != 0),
                progress_callback=_on_prog,
            )

            if self.is_cancelled:
                self.ui_callbacks["on_file_error"](index, "Cancelled")
                return False, "Cancelled"

            self._per_file_progress[index] = 100
            self._emit_total_progress()
            self.ui_callbacks["on_file_done"](index, str(out_path))
            return True, str(out_path.parent)

        except Exception as exc:
            log.exception("Watermark export failed for %s", file_path)
            if self.is_cancelled:
                self.ui_callbacks["on_file_error"](index, "Cancelled")
                return False, "Cancelled"
            self.ui_callbacks["on_file_error"](index, str(exc))
            return False, str(exc)
        finally:
            with self._lock:
                self._active_engine = None
            if tmp_png and os.path.exists(tmp_png):
                try:
                    os.remove(tmp_png)
                except OSError as exc:
                    log.debug("Failed to remove temp watermark %s: %s", tmp_png, exc)

    def run(self) -> None:
        output_dirs: list[str] = []
        succeeded = 0
        failed = 0

        for idx, filepath in enumerate(self.file_list):
            if self.is_cancelled:
                break
            ok, result = self._process_single_file(idx, filepath)
            if ok:
                succeeded += 1
                if result not in output_dirs:
                    output_dirs.append(result)
            elif not self.is_cancelled:
                failed += 1

        if not self.is_cancelled:
            cb = self.ui_callbacks.get("on_complete")
            if cb:
                cb({"succeeded": succeeded, "failed": failed, "output_dirs": output_dirs})

    def cancel(self) -> None:
        self.is_cancelled = True
        with self._lock:
            if self._active_engine is not None:
                self._active_engine.cancel()

