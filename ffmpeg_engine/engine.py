import subprocess
import re
import os
import sys
from pathlib import Path
from utils.config import get_ffmpeg_path

class FFmpegEngine:
    def __init__(self):
        self.ffmpeg_exe = get_ffmpeg_path()
        self.process = None
        self.cancelled = False

    def build_command(self, input_file, output_file, settings):
        fmt_ext = settings.get("output_format", "mp3").lower()
        cmd = [self.ffmpeg_exe, "-y", "-i", input_file]

        audio_formats = ["mp3", "wav", "m4a", "aac", "flac"]
        video_formats = ["mp4", "mkv", "mov", "avi"]
        image_formats = ["jpg", "png", "webp", "ico", "jpeg"]

        if fmt_ext in audio_formats:
            cmd.extend(["-vn", "-map_metadata", "0", "-id3v2_version", "3"])
            cmd.extend(["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"])
            
            if fmt_ext == "mp3":
                cmd.extend(["-c:a", "libmp3lame"])
            elif fmt_ext == "wav":
                cmd.extend(["-c:a", "pcm_s16le"])
            elif fmt_ext in ["m4a", "aac"]:
                cmd.extend(["-c:a", "aac"])
            elif fmt_ext == "flac":
                cmd.extend(["-c:a", "flac"])

            bitrate = settings.get("bitrate", "192 kbps").split()[0] + "k"
            if fmt_ext not in ["wav", "flac"]:
                cmd.extend(["-b:a", bitrate])

        elif fmt_ext in video_formats:
            cmd.extend(["-c:v", "libx264", "-c:a", "aac", "-b:a", "192k"])
            
        elif fmt_ext in image_formats:
            if fmt_ext == "ico":
                # ICO files only accept up to 256x256 dimensions natively 
                cmd.extend(["-vf", "scale='min(256,iw)':'min(256,ih)':force_original_aspect_ratio=decrease,pad=256:256:(ow-iw)/2:(oh-ih)/2:color=black@0"])

        cmd.append(output_file)
        return cmd

    def convert(self, input_file, output_file, settings, progress_callback):
        fmt_ext = settings.get("output_format", "mp3").lower()
        
        archive_formats = ["zip", "tar"]

        if fmt_ext in archive_formats:
            import zipfile
            import tarfile
            from pathlib import Path
            if fmt_ext == "zip":
                with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(input_file, arcname=Path(input_file).name)
            elif fmt_ext == "tar":
                with tarfile.open(output_file, "w") as tarf:
                    tarf.add(input_file, arcname=Path(input_file).name)
            progress_callback(100)
            return

        if not os.path.exists(self.ffmpeg_exe):
            raise FileNotFoundError(f"FFmpeg not found at: {self.ffmpeg_exe}")

        cmd = self.build_command(input_file, output_file, settings)
        
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding='utf-8',     
            errors='replace',    
            creationflags=creationflags
        )

        duration_secs = 1
        time_regex = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.\d{2}")
        dur_regex = re.compile(r"Duration: (\d{2}):(\d{2}):(\d{2})\.\d{2}")

        for line in self.process.stdout:
            # Get total duration for progress bar
            dur_match = dur_regex.search(line)
            if dur_match:
                h, m, s = map(int, dur_match.groups())
                duration_secs = max(1, h * 3600 + m * 60 + s)

            # Update progress
            time_match = time_regex.search(line)
            if time_match:
                h, m, s = map(int, time_match.groups())
                current_secs = h * 3600 + m * 60 + s
                progress = min(100, int((current_secs / duration_secs) * 100))
                progress_callback(progress)

        self.process.wait()
        if self.process.returncode != 0 and self.process.returncode != 255:
            raise RuntimeError(f"FFmpeg failed with exit code {self.process.returncode}")

    def watermark_video(
        self,
        input_file: str,
        watermark_png: str,
        output_file: str,
        exact_x: int,
        exact_y: int,
        crf: int = 18,
        has_audio: bool = True,
        known_duration: float = 0.0,
        needs_even_pad: bool = False,
        progress_callback=None,
    ) -> None:
        """
        Composite *watermark_png* onto *input_file* at ``(exact_x, exact_y)``.

        Attempts lossless audio stream copy (``-c:a copy``) first and falls
        back cleanly to re-encoding audio if the target container/codec rejects
        stream copy.
        """
        if not os.path.exists(self.ffmpeg_exe):
            raise FileNotFoundError(f"FFmpeg not found at: {self.ffmpeg_exe}")

        self.cancelled = False
        ext = Path(output_file).suffix.lower()

        filter_complex = f"[0:v][1:v]overlay={int(exact_x)}:{int(exact_y)}:format=auto"
        if needs_even_pad and ext != ".webm":
            filter_complex += ",pad=ceil(iw/2)*2:ceil(ih/2)*2"

        if ext == ".webm":
            video_args = ["-c:v", "libvpx-vp9", "-crf", str(crf), "-b:v", "0", "-pix_fmt", "yuv420p"]
            fallback_audio = ["-c:a", "libopus", "-b:a", "192k"]
        elif ext == ".avi":
            video_args = ["-c:v", "libx264", "-crf", str(crf), "-preset", "medium", "-pix_fmt", "yuv420p"]
            fallback_audio = ["-c:a", "libmp3lame", "-b:a", "192k"]
        else:
            video_args = ["-c:v", "libx264", "-crf", str(crf), "-preset", "medium", "-pix_fmt", "yuv420p"]
            fallback_audio = ["-c:a", "aac", "-b:a", "192k"]

        extra_container_args = ["-movflags", "+faststart"] if ext in (".mp4", ".mov", ".m4v") else []

        def _build_wm_cmd(audio_args: list[str]) -> list[str]:
            cmd = [
                self.ffmpeg_exe,
                "-y",
                "-i", input_file,
                "-i", watermark_png,
                "-filter_complex", filter_complex,
                *video_args,
            ]
            if has_audio:
                cmd.extend(audio_args)
            else:
                cmd.append("-an")
            cmd.extend(extra_container_args)
            cmd.append(output_file)
            return cmd

        rc, last_err = self._run_ffmpeg_with_progress(
            _build_wm_cmd(["-c:a", "copy"]),
            known_duration=known_duration,
            progress_callback=progress_callback,
        )

        # Retry with audio re-encode if stream copy failed due to container mismatch
        if rc != 0 and not self.cancelled and has_audio:
            rc, last_err = self._run_ffmpeg_with_progress(
                _build_wm_cmd(fallback_audio),
                known_duration=known_duration,
                progress_callback=progress_callback,
            )

        if self.cancelled:
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                except OSError:
                    pass
            return

        if rc != 0:
            raise RuntimeError(f"FFmpeg failed (exit {rc}): {last_err}")

    def _run_ffmpeg_with_progress(
        self,
        cmd: list[str],
        known_duration: float = 0.0,
        progress_callback=None,
    ) -> tuple[int, str]:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )

        duration_secs = float(known_duration) if known_duration and known_duration > 0 else 1.0
        time_regex = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})")
        dur_regex = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2})\.(\d{2})")
        tail_lines: list[str] = []

        if self.process.stdout is not None:
            for line in self.process.stdout:
                if self.cancelled:
                    break
                stripped = line.strip()
                if stripped:
                    tail_lines.append(stripped)
                    if len(tail_lines) > 12:
                        tail_lines.pop(0)

                if duration_secs <= 1.0:
                    dur_match = dur_regex.search(line)
                    if dur_match:
                        h, m, s, cs = map(int, dur_match.groups())
                        duration_secs = max(0.1, h * 3600 + m * 60 + s + cs / 100.0)

                time_match = time_regex.search(line)
                if time_match and progress_callback:
                    h, m, s, cs = map(int, time_match.groups())
                    current_secs = h * 3600 + m * 60 + s + cs / 100.0
                    pct = min(99, max(0, int((current_secs / duration_secs) * 100)))
                    progress_callback(pct)

        self.process.wait()
        rc = self.process.returncode
        self.process = None
        last_err = tail_lines[-1] if tail_lines else "Unknown FFmpeg error"
        return rc, last_err

    def cancel(self):
        self.cancelled = True
        proc = self.process
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass