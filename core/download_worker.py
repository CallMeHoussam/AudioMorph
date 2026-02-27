import threading
import concurrent.futures
import os
from core.downloader import DownloaderEngine

class DownloadWorker(threading.Thread):
    def __init__(self, url_list, settings, ui_callbacks):
        super().__init__(daemon=True)
        self.url_list = url_list
        self.settings = settings
        self.ui_callbacks = ui_callbacks
        self.is_cancelled = False
        self.engines = []

    def _process_single_url(self, index, url):
        if self.is_cancelled: return

        self.ui_callbacks["on_file_start"](index, url) 
        engine = DownloaderEngine()
        self.engines.append(engine)
        
        try:
            title = engine.download(
                url, self.settings,
                lambda p: self.ui_callbacks["on_progress"](index, p)
            )
            
            if not self.is_cancelled:
                self.ui_callbacks["on_file_done"](index, "Done")
                
        except Exception as e:
            if str(e) == "Cancelled by user":
                self.ui_callbacks["on_file_error"](index, "Cancelled")
            else:
                self.ui_callbacks["on_file_error"](index, "Error")
                print(f"Download Error: {e}")
        finally:
            if engine in self.engines:
                self.engines.remove(engine)

    def run(self):
        total_urls = len(self.url_list)
        max_workers = max(1, os.cpu_count() - 1)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self._process_single_url, i, url) 
                for i, url in enumerate(self.url_list)
            ]
            
            completed = 0
            for future in concurrent.futures.as_completed(futures):
                if self.is_cancelled: break
                completed += 1
                self.ui_callbacks["on_total_progress"](int((completed / total_urls) * 100))

        if not self.is_cancelled:
            self.ui_callbacks["on_complete"]()

    def cancel(self):
        self.is_cancelled = True
        for engine in self.engines:
            engine.cancel()
