import os
import subprocess
from pathlib import Path
from PIL import Image
import shutil

class UniversalEngine:
    def __init__(self, ffmpeg_path):
        self.ffmpeg_exe = ffmpeg_path

    def convert(self, in_file, out_file, target_format, settings, progress_callback):
        ext = target_format.lower()
        
        # AUDIO & VIDEO
        if ext in ['mp3', 'wav', 'aac', 'flac', 'mp4', 'mkv', 'mov', 'avi']:
            self._ffmpeg_run(in_file, out_f=out_file, fmt=ext, settings=settings, cb=progress_callback)
        
        # IMAGES
        elif ext in ['jpg', 'png', 'webp', 'ico']:
            with Image.open(in_file) as img:
                if ext == 'jpg': img = img.convert("RGB")
                img.save(out_file)
            progress_callback(100)

    def _ffmpeg_run(self, in_f, out_f, fmt, settings, cb):
        cmd = [self.ffmpeg_exe, "-y", "-i", in_f, "-map_metadata", "0", "-id3v2_version", "3"]
        if fmt in ['mp3', 'wav', 'aac', 'flac']: cmd.append("-vn")
        cmd.append(out_f)
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   universal_newlines=True, encoding='utf-8', errors='replace',
                                   creationflags=0x08000000) # CREATE_NO_WINDOW
        process.wait()

    def cancel(self):
        # Implementation for process termination
        pass