import os
from pathlib import Path
from utils.config import get_ffmpeg_path

class DownloaderEngine:
    def __init__(self):
        self.ffmpeg_exe = get_ffmpeg_path()
        self.is_cancelled = False
        self._ydl = None

    def cancel(self):
        self.is_cancelled = True

    def _progress_hook(self, d, progress_callback):
        if self.is_cancelled:
            raise Exception("Cancelled by user")
        
        if d['status'] == 'downloading':
            try:
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
                if total_bytes:
                    downloaded_bytes = d.get('downloaded_bytes', 0)
                    percent = int((downloaded_bytes / total_bytes) * 100)
                    progress_callback(percent)
            except:
                pass

    def download(self, url, settings, progress_callback):
        import yt_dlp
        self.is_cancelled = False
        
        format_choice = settings.get("download_format", "mp4").lower()
        quality = settings.get("download_quality", "Best Available")
        out_dir = settings.get("download_output_dir", str(Path.home() / "Downloads"))
        
        ydl_opts = {
            'outtmpl': os.path.join(out_dir, '%(title)s.%(ext)s'),
            'ffmpeg_location': os.path.dirname(self.ffmpeg_exe),
            'noplaylist': True,
            'quiet': True,
            'progress_hooks': [lambda d: self._progress_hook(d, progress_callback)],
        }

        audio_formats = ['mp3', 'wav', 'm4a', 'aac', 'flac']

        if format_choice in audio_formats:
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format_choice,
                'preferredquality': '192',
            }]
        else:
            if "Audio Only" in quality:
                 ydl_opts['format'] = 'bestaudio/best'
                 ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            elif "4K" in quality:
                ydl_opts['format'] = 'bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best'
                ydl_opts['merge_output_format'] = format_choice
            elif "2K" in quality:
                ydl_opts['format'] = 'bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best'
                ydl_opts['merge_output_format'] = format_choice
            elif "1080p" in quality:
                ydl_opts['format'] = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best'
                ydl_opts['merge_output_format'] = format_choice
            elif "720p" in quality:
                ydl_opts['format'] = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best'
                ydl_opts['merge_output_format'] = format_choice
            elif "480p" in quality:
                ydl_opts['format'] = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best'
                ydl_opts['merge_output_format'] = format_choice
            else:
                ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
                ydl_opts['merge_output_format'] = format_choice

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            self._ydl = ydl
            info = ydl.extract_info(url, download=True)
            return info.get('title', 'Unknown Title')
