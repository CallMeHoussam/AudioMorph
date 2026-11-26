import importlib.util
import os
import shutil
import subprocess
import sys
import threading
from typing import List, Optional

from utils.logger import get_logger

log = get_logger(__name__)

_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def check_ai_backend_available(pkg_name: str, cli_name: str = "") -> tuple[bool, Optional[list[str]], str]:
    """
    Safely check whether an offline AI backend (*rembg*, *whisper*, *demucs*, *spleeter*)
    is usable in the current environment without crashing or spawning recursive frozen GUIs.

    Returns ``(available, command_prefix_or_none, user_friendly_message)``.
    """
    is_frozen = getattr(sys, "frozen", False)

    if not is_frozen and importlib.util.find_spec(pkg_name) is not None:
        return True, [sys.executable, "-m", pkg_name], ""

    if cli_name:
        cli_path = shutil.which(cli_name)
        if cli_path:
            return True, [cli_path], ""

    if is_frozen:
        return (
            False,
            None,
            f"Optional offline AI plugin '{pkg_name}' is not bundled in the standalone installer.\n"
            f"To enable it, install Python + '{pkg_name}' on PATH or run AudioMorph from source.",
        )
    return False, None, f"'{pkg_name}' is not installed. Run 'pip install {pkg_name}' to enable this tool."


class AIWorker(threading.Thread):
    """
    Offline AI processing queue layer.
    Connects to python packages/CLI binaries for ML processing.
    """

    def __init__(self, items: List[str], action: str, callbacks: dict, settings: Optional[dict] = None):
        super().__init__(daemon=True)
        self.items = list(items)
        self.action = action
        self.callbacks = callbacks
        self.settings = settings or {}
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
                base, _ = os.path.splitext(filepath)

                if "Background" in self.action:
                    out_path = f"{base}_nobg.png"
                    self._process_background(filepath, out_path)
                elif "Subtitles" in self.action:
                    self._process_subtitles(filepath, os.path.dirname(filepath))
                elif "Vocals" in self.action:
                    self._process_vocals(filepath, os.path.dirname(filepath))
                else:
                    raise RuntimeError(f"Unknown AI action: {self.action}")

                if not self.cancel_flag:
                    self.callbacks.get("on_file_done", lambda idx, msg: None)(i, "Done")
            except Exception as e:
                err_msg = str(e)
                log.error("AI Worker failed on %s: %s", filepath, err_msg)
                self.callbacks.get("on_file_error", lambda idx, err: None)(i, err_msg)

            self.callbacks.get("on_total_progress", lambda p: None)(((i + 1) / total) * 100)

        if not self.cancel_flag:
            self.callbacks.get("on_complete", lambda: None)()

    def _process_background(self, filepath: str, out_path: str) -> None:
        try:
            from PIL import Image
            from rembg import remove

            with Image.open(filepath) as input_img:
                output_img = remove(input_img)
                output_img.save(out_path)
        except ImportError:
            _, _, msg = check_ai_backend_available("rembg")
            raise RuntimeError(msg)

    def _process_subtitles(self, filepath: str, out_dir: str) -> None:
        from utils.config import get_ffmpeg_path

        ok, cmd_prefix, msg = check_ai_backend_available("whisper", cli_name="whisper")
        if not ok or not cmd_prefix:
            raise RuntimeError(msg or "Install 'openai-whisper' first.")

        env = os.environ.copy()
        env["PATH"] = f"{os.path.dirname(get_ffmpeg_path())}{os.pathsep}{env.get('PATH', '')}"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        model = self.settings.get("whisper_model", "small")
        language = self.settings.get("whisper_language", "auto")

        cmd = [
            *cmd_prefix,
            filepath,
            "--model", model,
            "--output_dir", out_dir,
            "--output_format", "srt",
        ]
        if language and language.lower() != "auto":
            cmd.extend(["--language", language])

        subprocess.run(cmd, env=env, check=True, creationflags=_CREATE_NO_WINDOW)

    def _process_vocals(self, filepath: str, out_dir: str) -> None:
        from utils.config import get_ffmpeg_path

        env = os.environ.copy()
        env["PATH"] = f"{os.path.dirname(get_ffmpeg_path())}{os.pathsep}{env.get('PATH', '')}"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        ok_demucs, cmd_demucs, msg_demucs = check_ai_backend_available("demucs", cli_name="demucs")
        if ok_demucs and cmd_demucs:
            cmd = [*cmd_demucs, "-n", "htdemucs", filepath, "--out", out_dir]
            subprocess.run(cmd, env=env, check=True, creationflags=_CREATE_NO_WINDOW)
            return

        ok_spleeter, cmd_spleeter, _ = check_ai_backend_available("spleeter", cli_name="spleeter")
        if ok_spleeter and cmd_spleeter:
            cmd = [*cmd_spleeter, "separate", "-p", "spleeter:2stems", "-o", out_dir, filepath]
            subprocess.run(cmd, env=env, check=True, creationflags=_CREATE_NO_WINDOW)
            return

        raise RuntimeError(msg_demucs)
