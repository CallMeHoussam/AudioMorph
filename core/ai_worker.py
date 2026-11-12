import logging
import os
import subprocess
import threading
from typing import Callable, List
from pathlib import Path

log = logging.getLogger(__name__)

class AIWorker(threading.Thread):
    """
    Offline AI processing queue layer.
    Connects to python scripts/binaries for ML processing.
    """
    def __init__(self, items: List[str], action: str, callbacks: dict):
        super().__init__(daemon=True)
        self.items = items
        self.action = action
        self.callbacks = callbacks
        self.cancel_flag = False

    def cancel(self):
        self.cancel_flag = True

    def run(self):
        total = len(self.items)
        if total == 0:
            self.callbacks.get("on_complete", lambda: None)()
            return
            
        for i, filepath in enumerate(self.items):
            if self.cancel_flag:
                break
                
            self.callbacks.get("on_file_start", lambda idx, f: None)(i, filepath)
            
            try:
                base, ext = os.path.splitext(filepath)
                
                if "Background" in self.action:
                    out_path = f"{base}_nobg.png"
                    self._process_background(filepath, out_path)
                    
                elif "Subtitles" in self.action:
                    self._process_subtitles(filepath, os.path.dirname(filepath))
                    
                elif "Vocals" in self.action:
                    self._process_vocals(filepath, os.path.dirname(filepath))
                else:
                    raise Exception("Unknown AI action")
                    
                if not self.cancel_flag:
                    self.callbacks.get("on_file_done", lambda idx, msg: None)(i, "Done")
            except Exception as e:
                err_msg = str(e)
                log.error(f"AI Worker failed on {filepath}: {err_msg}")
                # Pass the exact error (like 'rembg not installed') to the UI
                self.callbacks.get("on_file_error", lambda idx, err: None)(i, err_msg)
                
            self.callbacks.get("on_total_progress", lambda p: None)(((i + 1) / total) * 100)
                
        if not self.cancel_flag:
            self.callbacks.get("on_complete", lambda: None)()

    def _process_background(self, filepath, out_path):
        try:
            from rembg import remove
            from PIL import Image
            input_img = Image.open(filepath)
            output_img = remove(input_img)
            output_img.save(out_path)
        except ImportError:
            raise Exception("rembg not found. Please run 'pip install rembg'")

    def _process_subtitles(self, filepath, out_dir):
        import shutil, sys, importlib.util
        from utils.config import get_ffmpeg_path
        
        if importlib.util.find_spec("whisper") is None and not shutil.which("whisper"):
            raise Exception("Run 'pip install openai-whisper'")
            
        env = os.environ.copy()
        env["PATH"] = f"{os.path.dirname(get_ffmpeg_path())};{env.get('PATH', '')}"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        
        cmd = [
            sys.executable, "-m", "whisper", filepath,
            "--model", "small",
            "--language", "ar",
            "--initial_prompt", "نصوص عربية دقيقة بأسلوب فصيح وواضح.",
            "--output_dir", out_dir,
            "--output_format", "srt"
        ]
        subprocess.run(cmd, env=env, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
    def _process_vocals(self, filepath, out_dir):
        import shutil, sys, importlib.util
        from utils.config import get_ffmpeg_path
        
        env = os.environ.copy()
        env["PATH"] = f"{os.path.dirname(get_ffmpeg_path())};{env.get('PATH', '')}"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        
        if importlib.util.find_spec("demucs") is not None or shutil.which("demucs"):
            cmd = [sys.executable, "-m", "demucs", "-n", "htdemucs", filepath, "--out", out_dir]
            subprocess.run(cmd, env=env, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        elif importlib.util.find_spec("spleeter") is not None or shutil.which("spleeter"):
            cmd = [sys.executable, "-m", "spleeter", "separate", "-p", "spleeter:2stems", "-o", out_dir, filepath]
            subprocess.run(cmd, env=env, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            raise Exception("Run 'pip install demucs'")
