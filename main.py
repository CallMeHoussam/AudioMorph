"""
AudioMorph — entry point.

Initializes structured logging, optionally triggers a background
yt-dlp update, then launches the CustomTkinter GUI.
"""

import sys
import os
import threading

# Ensure the project root is on sys.path (for dev and frozen builds)
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from utils.logger import setup_logging, get_logger  # noqa: E402

setup_logging()
log = get_logger("audiomorph")


def _try_update_ytdlp() -> None:
    """Best-effort background update of yt-dlp (non-blocking)."""
    if getattr(sys, "frozen", False):
        log.info("Running as frozen app — skipping auto-update.")
        return
        
    try:
        import subprocess
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        log.info("yt-dlp auto-update check completed.")
    except Exception as exc:
        log.debug("yt-dlp auto-update skipped: %s", exc)


def main() -> None:
    """Application entry point."""
    log.info("AudioMorph starting...")

    # Background yt-dlp update (fire-and-forget)
    threading.Thread(target=_try_update_ytdlp, daemon=True).start()

    try:
        from gui.app_window import AudioMorphApp
        app = AudioMorphApp()
        app.mainloop()
    except Exception:
        log.exception("Fatal error — AudioMorph is shutting down.")
        sys.exit(1)

    log.info("AudioMorph exited normally.")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()