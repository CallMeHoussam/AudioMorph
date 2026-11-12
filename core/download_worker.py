"""
Threaded download worker — manages a queue of URLs and reports
progress, speed, and errors back to the UI via callbacks.
"""

import concurrent.futures
import os
import threading

from core.downloader import CancelledError, DownloadError, DownloaderEngine
from utils.logger import get_logger

log = get_logger(__name__)


class DownloadWorker(threading.Thread):
    """
    Background thread that downloads a list of URLs concurrently.

    ``ui_callbacks`` dict must contain:
        - ``on_file_start(index, url)``
        - ``on_progress(index, data_dict)``   # {percent, speed, eta, status}
        - ``on_file_done(index, title)``
        - ``on_file_error(index, message)``
        - ``on_total_progress(percent)``
        - ``on_complete()``
    """

    def __init__(
        self,
        url_list: list[str],
        settings: dict,
        ui_callbacks: dict,
    ) -> None:
        super().__init__(daemon=True)
        self.url_list = list(url_list)
        self.settings = settings
        self.ui_callbacks = ui_callbacks
        self.is_cancelled = False
        self._engines: list[DownloaderEngine] = []
        self._lock = threading.Lock()

    # ── single-URL download ───────────────────────────────────────────

    def _process_single_url(self, index: int, url: str) -> None:
        if self.is_cancelled:
            return

        self.ui_callbacks["on_file_start"](index, url)
        engine = DownloaderEngine()

        with self._lock:
            self._engines.append(engine)

        try:
            title = engine.download(
                url,
                self.settings,
                lambda data: self.ui_callbacks["on_progress"](index, data),
            )
            if not self.is_cancelled:
                self.ui_callbacks["on_file_done"](index, title)
                self._record_history(url, title, self.settings.get("download_output_dir", ""))

        except CancelledError:
            self.ui_callbacks["on_file_error"](index, "Cancelled")
            log.info("Download cancelled — %s", url)

        except DownloadError as exc:
            self.ui_callbacks["on_file_error"](index, str(exc)[:80])
            log.error("Download failed — %s: %s", url, exc)

        except Exception as exc:
            self.ui_callbacks["on_file_error"](index, str(exc)[:80])
            log.exception("Unexpected error downloading %s", url)

        finally:
            with self._lock:
                if engine in self._engines:
                    self._engines.remove(engine)

    # ── thread entry ──────────────────────────────────────────────────

    def run(self) -> None:
        total = len(self.url_list)
        if total == 0:
            self.ui_callbacks["on_complete"]()
            return

        max_workers = 1  # Process one by one (queue)
        log.info("Download worker started — %d URL(s), %d workers", total, max_workers)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                pool.submit(self._process_single_url, i, url)
                for i, url in enumerate(self.url_list)
            ]

            completed = 0
            for future in concurrent.futures.as_completed(futures):
                if self.is_cancelled:
                    break
                completed += 1
                self.ui_callbacks["on_total_progress"](
                    int((completed / total) * 100)
                )

        if not self.is_cancelled:
            self.ui_callbacks["on_complete"]()
            log.info("All downloads finished.")

    # ── cancel ────────────────────────────────────────────────────────

    def cancel(self) -> None:
        self.is_cancelled = True
        with self._lock:
            for engine in self._engines:
                engine.cancel()
        log.info("Download worker cancel requested.")

    def _record_history(self, url: str, title: str, out_dir: str) -> None:
        try:
            import json, datetime
            history_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "download_history.json")
            entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "url": url,
                "title": title,
                "output_dir": str(out_dir)
            }
            history = []
            if os.path.exists(history_file):
                try:
                    with open(history_file, "r", encoding="utf-8") as f:
                        history = json.load(f)
                except Exception:
                    pass
            history.append(entry)
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=4)
        except Exception as e:
            log.error(f"Failed to record history: {e}")
