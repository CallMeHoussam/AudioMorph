import concurrent.futures
import os
import threading
from pathlib import Path

from ffmpeg_engine.engine import FFmpegEngine
from utils.logger import get_logger

log = get_logger(__name__)


class ConversionWorker(threading.Thread):
    def __init__(self, file_list, settings, ui_callbacks):
        super().__init__(daemon=True)
        self.file_list = list(file_list)
        self.settings = settings
        self.ui_callbacks = ui_callbacks
        self.is_cancelled = False
        self.engines: list[FFmpegEngine] = []
        self._lock = threading.Lock()

    def _process_single_file(self, index, file_path):
        if self.is_cancelled:
            return

        self.ui_callbacks["on_file_start"](index, file_path)
        engine = FFmpegEngine()
        with self._lock:
            self.engines.append(engine)

        try:
            out_ext = self.settings["output_format"].lower()
            in_path = Path(file_path)

            if self.settings.get("save_in_source", True):
                out_dir = in_path.parent
            else:
                out_dir = Path(self.settings.get("custom_output_dir") or in_path.parent)

            os.makedirs(out_dir, exist_ok=True)
            out_path = out_dir / f"{in_path.stem}.{out_ext}"
            # Avoid overwriting source if target extension matches input
            if out_path.resolve() == in_path.resolve():
                out_path = out_dir / f"{in_path.stem}_converted.{out_ext}"

            engine.convert(
                str(in_path), str(out_path), self.settings,
                lambda p: self.ui_callbacks["on_progress"](index, p),
            )

            if not self.is_cancelled:
                self.ui_callbacks["on_file_done"](index, "Done")

        except Exception as e:
            log.error("Conversion error for %s: %s", file_path, e)
            self.ui_callbacks["on_file_error"](index, str(e))
        finally:
            with self._lock:
                if engine in self.engines:
                    self.engines.remove(engine)

    def run(self):
        total_files = len(self.file_list)
        if total_files == 0:
            self.ui_callbacks["on_complete"]()
            return

        # Safe balanced cap so batch encodes never freeze the system or saturate disk I/O
        max_workers = min(4, max(1, (os.cpu_count() or 2) // 2))

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self._process_single_file, i, f)
                for i, f in enumerate(self.file_list)
            ]

            completed = 0
            for future in concurrent.futures.as_completed(futures):
                if self.is_cancelled:
                    break
                completed += 1
                self.ui_callbacks["on_total_progress"](int((completed / total_files) * 100))

        if not self.is_cancelled:
            self.ui_callbacks["on_complete"]()

    def cancel(self):
        self.is_cancelled = True
        with self._lock:
            engines_snapshot = list(self.engines)
        for engine in engines_snapshot:
            engine.cancel()
