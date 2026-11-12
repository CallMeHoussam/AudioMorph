"""
Download engine — wraps yt-dlp with multi-platform support,
quality selection, Twitch handling, and structured progress reporting.
"""

import os
from pathlib import Path

from utils.config import get_ffmpeg_path
from utils.logger import get_logger
from utils.validators import detect_platform

log = get_logger(__name__)

# ── Custom exceptions ────────────────────────────────────────────────────────


class DownloadError(Exception):
    """Any non-recoverable download failure."""


class CancelledError(Exception):
    """Download was cancelled by the user."""


class PlatformNotSupportedError(DownloadError):
    """URL platform could not be handled by yt-dlp."""


# ── Quality preset mapping ───────────────────────────────────────────────────

_QUALITY_FORMAT: dict[str, str] = {
    "Best Available": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
    "4K":             "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best",
    "2K":             "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best",
    "1080p":          "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best",
    "720p":           "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best",
    "480p":           "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best",
}

_AUDIO_FORMATS = {"mp3", "wav", "m4a", "aac", "flac"}


class _YtDlpLogger:
    """Route yt-dlp output through our structured logger instead of stderr."""

    def debug(self, msg: str) -> None:
        # yt-dlp sends download progress as debug messages — skip them
        if msg.startswith("[download]"):
            return
        log.debug(msg)

    def info(self, msg: str) -> None:
        log.debug(msg)

    def warning(self, msg: str) -> None:
        log.warning("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        log.error("yt-dlp: %s", msg)


class DownloaderEngine:
    """
    Download media from any yt-dlp-supported platform.

    ``progress_callback`` receives a dict:
        ``{"percent": int, "speed": str, "eta": str, "status": str}``
    """

    def __init__(self) -> None:
        self.ffmpeg_exe: str = get_ffmpeg_path()
        self.is_cancelled: bool = False
        self._ydl = None

    # ── public API ────────────────────────────────────────────────────

    def cancel(self) -> None:
        self.is_cancelled = True

    def download(self, url: str, settings: dict, progress_callback) -> str:
        """
        Download *url* according to *settings*.

        Returns the media title on success.
        Raises ``CancelledError``, ``DownloadError``, or
        ``PlatformNotSupportedError`` on failure.
        """
        import yt_dlp

        self.is_cancelled = False
        platform = detect_platform(url)
        log.info("Starting download — platform=%s url=%s", platform, url)

        format_choice = settings.get("download_format", "MP4").lower()
        quality = settings.get("download_quality", "Best Available")
        out_dir = settings.get("download_output_dir", str(Path.home() / "Downloads"))
        noplaylist = settings.get("noplaylist", True)

        ydl_opts = self._build_opts(
            format_choice, quality, out_dir, noplaylist, progress_callback
        )
        
        if format_choice in ["jpg", "png", "webp"]:
            return self._download_image(url, out_dir, format_choice, progress_callback)

        if platform == "vecteezy":
            try:
                log.info("Vecteezy URL detected — using direct video scraper for %s", url)
                return self._download_web_video(url, out_dir, format_choice, progress_callback)
            except Exception as v_err:
                log.warning("Vecteezy direct scraper failed, falling back to yt-dlp: %s", v_err)

        # ── Platform-specific tweaks ─────────────────────────────────
        self._apply_platform_tweaks(ydl_opts, platform)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self._ydl = ydl
                info = ydl.extract_info(url, download=True)
                title = (info or {}).get("title", "Unknown Title")
                log.info("Download finished — %s", title)
                return title

        except yt_dlp.utils.DownloadError as exc:
            msg = str(exc)
            if self.is_cancelled:
                raise CancelledError("Cancelled by user") from exc

            # Try video fallback for Cloudflare / 403 / missing format errors
            if any(k in msg for k in ("Cloudflare", "403", "No video formats found", "Requested format is not available")):
                log.info("Attempting direct video scraper fallback for %s", url)
                try:
                    return self._download_web_video(url, out_dir, format_choice, progress_callback)
                except Exception as vid_exc:
                    log.info("Direct video scraper failed: %s. Trying image fallback.", vid_exc)
                    try:
                        return self._download_image(url, out_dir, "jpg", progress_callback)
                    except Exception as img_exc:
                        raise DownloadError(f"{msg}\n(Web fallback also failed: {vid_exc})") from exc

            # Twitch subscriber-only / unavailable
            if any(kw in msg.lower() for kw in ("subscriber", "sub-only", "unavailable", "private")):
                raise DownloadError(
                    f"Content unavailable (subscriber-only or private): {msg}"
                ) from exc
            raise DownloadError(msg) from exc

        except Exception as exc:
            if self.is_cancelled:
                raise CancelledError("Cancelled by user") from exc
            log.exception("Unexpected download error")
            raise DownloadError(str(exc)) from exc

    # ── private helpers ───────────────────────────────────────────────

    def _build_opts(
        self,
        format_choice: str,
        quality: str,
        out_dir: str,
        noplaylist: bool,
        progress_callback,
    ) -> dict:
        opts: dict = {
            "outtmpl": os.path.join(out_dir, "%(extractor_key)s", "%(title)s [%(id)s].%(ext)s"),
            "ffmpeg_location": os.path.dirname(self.ffmpeg_exe),
            "noplaylist": noplaylist,
            "quiet": True,
            "no_warnings": True,
            "verbose": False,
            "noprogress": True,
            "logger": _YtDlpLogger(),
            "progress_hooks": [lambda d: self._progress_hook(d, progress_callback)],
            "js_runtimes": {"node": {}},
            "remote_components": ["ejs:github"],
        }

        is_audio_format = format_choice in _AUDIO_FORMATS
        is_audio_quality = "Audio Only" in quality

        if is_audio_format or is_audio_quality:
            codec = format_choice if is_audio_format else "mp3"
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": codec,
                    "preferredquality": "192",
                }
            ]
        else:
            fmt_str = _QUALITY_FORMAT.get(quality, _QUALITY_FORMAT["Best Available"])
            opts["format"] = fmt_str
            opts["merge_output_format"] = format_choice

        return opts

    @staticmethod
    def _apply_platform_tweaks(opts: dict, platform: str) -> None:
        """Add platform-specific yt-dlp options."""
        try:
            from yt_dlp.networking.impersonate import ImpersonateTarget
            import yt_dlp.networking._curlcffi as _cfl
            if _cfl.CurlCFFIRH._is_available():
                opts["impersonate"] = ImpersonateTarget("chrome", "116", "windows", "10")
        except Exception:
            pass

        if platform in ("tiktok", "instagram", "pinterest"):
            opts["format"] = "bestvideo+bestaudio/b"
            
        if platform == "twitch":
            # Prefer mp4 container for Twitch to avoid issues
            opts.setdefault("merge_output_format", "mp4")
        elif platform == "kick":
            # Kick API requires browser-like headers to avoid 403
            opts["http_headers"] = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Referer": "https://kick.com/",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://kick.com",
            }
        elif platform == "twitter":
            opts["extractor_args"] = {"twitter": {"legacy_api": ["true"]}}
        elif platform == "instagram":
            # Instagram stories may need cookies — hint in logs
            log.debug("Instagram download — cookies may be required for private content")

    def _progress_hook(self, d: dict, progress_callback) -> None:
        """Translate yt-dlp progress dicts into a clean callback."""
        if self.is_cancelled:
            raise CancelledError("Cancelled by user")

        status = d.get("status", "")

        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            percent = int((downloaded / total) * 100) if total else 0
            speed_bps = d.get("speed") or 0
            speed_str = self._format_speed(speed_bps)
            eta_raw = d.get("eta")
            eta_str = f"{eta_raw}s" if eta_raw is not None else "—"

            progress_callback({
                "percent": min(percent, 100),
                "speed": speed_str,
                "eta": eta_str,
                "status": "downloading",
            })

        elif status == "finished":
            progress_callback({
                "percent": 100,
                "speed": "",
                "eta": "",
                "status": "processing",
            })

    @staticmethod
    def _format_speed(bps: float) -> str:
        if not bps:
            return "—"
        if bps >= 1_048_576:
            return f"{bps / 1_048_576:.1f} MB/s"
        if bps >= 1024:
            return f"{bps / 1024:.0f} KB/s"
        return f"{bps:.0f} B/s"

    def _download_image(self, url: str, out_dir: str, format_choice: str, progress_callback) -> str:
        """Fallback web scraper for high quality image extraction."""
        import urllib.request
        import re
        import uuid
        import subprocess
        platform = detect_platform(url)
        extract_folder = platform.capitalize() if platform else "Web"
        final_out_dir = os.path.join(out_dir, extract_folder)
        os.makedirs(final_out_dir, exist_ok=True)
        
        progress_callback({"percent": 20, "speed": "—", "eta": "—", "status": "downloading"})
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        
        try:
            html = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')
        except Exception as e:
            raise DownloadError(f"Failed to load page: {e}")
            
        if self.is_cancelled:
            raise CancelledError("Cancelled by user")
            
        # Flexible meta search for og:image or twitter:image
        match = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+>', html, re.I)
        if not match:
            # Fallback: just look for the first content meta with an image URL
            match = re.search(r'<meta[^>]+content=["\'](https://[^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', html, re.I)
            
        if not match:
            raise DownloadError("No high quality image found on this page!")
            
        meta_tag = match.group(0)
        content_match = re.search(r'content=["\']([^"\']+)["\']', meta_tag, re.I)
        if not content_match:
             # If we used the fallback match, we might already have the URL in a group
             img_url = match.group(1) if len(match.groups()) > 0 else None
        else:
             img_url = content_match.group(1)

        if not img_url:
            raise DownloadError("No high quality image found on this page!")
            
        img_url = img_url.replace('&amp;', '&')
        if "pinimg.com" in img_url:
            img_url = re.sub(r'/(236x|474x|736x)/', '/originals/', img_url)

        title_match = re.search(r'<title>(.*?)</title>', html, re.I)
        title = title_match.group(1) if title_match else f"Image_{uuid.uuid4().hex[:6]}"
        title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()

        progress_callback({"percent": 50, "speed": "—", "eta": "—", "status": "downloading"})
        
        img_req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            img_data = urllib.request.urlopen(img_req).read()
        except Exception as e:
            raise DownloadError(f"Failed to fetch image data: {e}")

        progress_callback({"percent": 80, "speed": "—", "eta": "—", "status": "processing"})
        
        temp_path = os.path.join(final_out_dir, f"{uuid.uuid4().hex}.tmp")
        final_path = os.path.join(final_out_dir, f"{title} [{uuid.uuid4().hex[:4]}].{format_choice}")
        
        with open(temp_path, "wb") as f:
            f.write(img_data)
            
        try:
            subprocess.run([self.ffmpeg_exe, "-y", "-i", temp_path, final_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
             # If ffmpeg fails, just try renaming it loosely
             if os.path.exists(temp_path):
                 fallback_path = os.path.join(final_out_dir, f"{title} [{uuid.uuid4().hex[:4]}].jpg")
                 import shutil
                 shutil.copy(temp_path, fallback_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
        progress_callback({"percent": 100, "speed": "—", "eta": "—", "status": "completed"})
        return title

    def _download_web_video(self, url: str, out_dir: str, format_choice: str, progress_callback) -> str:
        """Fallback web scraper for direct video extraction (e.g. Vecteezy, stock video sites)."""
        import urllib.request
        import re
        import uuid
        platform = detect_platform(url)
        extract_folder = platform.capitalize() if platform and platform != "unknown" else "Web"
        final_out_dir = os.path.join(out_dir, extract_folder)
        os.makedirs(final_out_dir, exist_ok=True)
        
        progress_callback({"percent": 15, "speed": "—", "eta": "—", "status": "downloading"})
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': url,
        }
        req = urllib.request.Request(url, headers=headers)
        
        try:
            html = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')
        except Exception as e:
            raise DownloadError(f"Failed to load page: {e}")
            
        if self.is_cancelled:
            raise CancelledError("Cancelled by user")
            
        # Look for video meta tags or mp4 links
        video_url = None
        meta_match = re.search(r'<meta[^>]+(?:property|name)=["\']og:video(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
        if meta_match:
            video_url = meta_match.group(1)
            
        if not video_url:
            mp4_links = re.findall(r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*', html)
            if mp4_links:
                video_url = mp4_links[0]
                
        if not video_url:
            raise DownloadError("No direct video link found on page.")
            
        video_url = video_url.replace('&amp;', '&')
        
        title_match = re.search(r'<title>(.*?)</title>', html, re.I)
        raw_title = title_match.group(1) if title_match else f"Video_{uuid.uuid4().hex[:6]}"
        title = raw_title.split('|')[0].replace('Stock Video at Vecteezy', '').strip()
        title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip() or f"Video_{uuid.uuid4().hex[:6]}"
        
        progress_callback({"percent": 40, "speed": "—", "eta": "—", "status": "downloading"})
        
        video_req = urllib.request.Request(video_url, headers=headers)
        try:
            with urllib.request.urlopen(video_req) as resp:
                total_size = int(resp.headers.get('content-length', 0))
                downloaded = 0
                chunks = []
                chunk_size = 1024 * 256
                while True:
                    if self.is_cancelled:
                        raise CancelledError("Cancelled by user")
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        pct = int(40 + (downloaded / total_size) * 55)
                        progress_callback({"percent": min(pct, 95), "speed": "—", "eta": "—", "status": "downloading"})
                video_data = b"".join(chunks)
        except Exception as e:
            if self.is_cancelled:
                raise CancelledError("Cancelled by user") from e
            raise DownloadError(f"Failed to fetch video stream: {e}")
            
        progress_callback({"percent": 95, "speed": "—", "eta": "—", "status": "processing"})
        
        ext = "mp4" if format_choice in ("mp4", "best available") else format_choice
        final_path = os.path.join(final_out_dir, f"{title} [{uuid.uuid4().hex[:4]}].{ext}")
        
        with open(final_path, "wb") as f:
            f.write(video_data)
            
        progress_callback({"percent": 100, "speed": "—", "eta": "—", "status": "completed"})
        return title


