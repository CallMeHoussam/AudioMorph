"""
Structured logging for AudioMorph.

Replaces all print() calls with proper logging.
Console output uses a concise colored format; a rotating file
handler writes detailed logs to audiomorph.log.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FORMAT_CONSOLE = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_LOG_FORMAT_FILE = "%(asctime)s │ %(levelname)-7s │ %(name)s:%(lineno)d │ %(message)s"
_DATE_FORMAT = "%H:%M:%S"

_initialised = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with console + file handlers (call once at startup)."""
    global _initialised
    if _initialised:
        return
    _initialised = True

    root = logging.getLogger()
    root.setLevel(level)

    # ── Console handler ──────────────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(_LOG_FORMAT_CONSOLE, datefmt=_DATE_FORMAT))
    root.addHandler(console)

    # ── Rotating file handler ────────────────────────────────────────
    log_dir = Path(__file__).resolve().parent.parent
    log_file = log_dir / "audiomorph.log"
    try:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT_FILE, datefmt=_DATE_FORMAT))
        root.addHandler(file_handler)
    except OSError:
        root.warning("Could not create log file at %s", log_file)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (use ``__name__`` as convention)."""
    return logging.getLogger(name)
