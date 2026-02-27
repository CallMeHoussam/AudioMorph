import threading
from pathlib import Path
import concurrent.futures
import os
from ffmpeg_engine.engine import FFmpegEngine

class ConversionWorker(threading.Thread):
    def __init__(self, file_list, settings, ui_callbacks):
        super().__init__(daemon=True)
        self.file_list = file_list
        self.settings = settings
        self.ui_callbacks = ui_callbacks
        self.is_cancelled = False
        self.engines = []

    def _process_single_file(self, index, file_path):
        if self.is_cancelled: return

        self.ui_callbacks["on_file_start"](index, file_path)
        engine = FFmpegEngine()
        self.engines.append(engine)
        
        try:
            out_ext = self.settings["output_format"].lower()
            in_path = Path(file_path)
            
            if self.settings.get("save_in_source", True):
                out_dir = in_path.parent
            else:
                out_dir = Path(self.settings.get("custom_output_dir", in_path.parent))

            out_path = out_dir / f"{in_path.stem}.{out_ext}"

            engine.convert(
                str(in_path), str(out_path), self.settings,
                lambda p: self.ui_callbacks["on_progress"](index, p)
            )
            
            if not self.is_cancelled:
                self.ui_callbacks["on_file_done"](index, "Done")
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.ui_callbacks["on_file_error"](index, str(e))
        finally:
            if engine in self.engines:
                self.engines.remove(engine)

    def run(self):
        total_files = len(self.file_list)
        # Leave 1 core free to prevent UI freezing
        max_workers = max(1, os.cpu_count() - 1)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Map futures to indexes for accurate UI callbacks
            futures = [
                executor.submit(self._process_single_file, i, f) 
                for i, f in enumerate(self.file_list)
            ]
            
            completed = 0
            for future in concurrent.futures.as_completed(futures):
                if self.is_cancelled: break
                completed += 1
                self.ui_callbacks["on_total_progress"](int((completed / total_files) * 100))

        if not self.is_cancelled:
            self.ui_callbacks["on_complete"]()

    def cancel(self):
        self.is_cancelled = True
        for engine in self.engines:
            engine.cancel()