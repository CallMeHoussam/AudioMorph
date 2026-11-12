"""
URL validation and platform detection utilities.
"""

import re
from urllib.parse import urlparse

# ── Platform regex patterns (order matters — first match wins) ────────────
_PLATFORM_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("youtube",   re.compile(r"(youtube\.com|youtu\.be)", re.I)),
    ("twitch",    re.compile(r"(twitch\.tv)", re.I)),
    ("kick",      re.compile(r"(kick\.com)", re.I)),
    ("instagram", re.compile(r"(instagram\.com|instagr\.am)", re.I)),
    ("twitter",   re.compile(r"(twitter\.com|x\.com)", re.I)),
    ("tiktok",    re.compile(r"(tiktok\.com|vm\.tiktok\.com)", re.I)),
    ("pinterest", re.compile(r"(pinterest\.com|pin\.it)", re.I)),
    ("vecteezy",  re.compile(r"(vecteezy\.com)", re.I)),
]

_PLAYLIST_PATTERNS: list[re.Pattern] = [
    re.compile(r"youtube\.com/playlist\?list=", re.I),
    re.compile(r"[?&]list=", re.I),
]


def is_valid_url(url: str) -> bool:
    """Return *True* if *url* looks like a valid HTTP(s) URL."""
    try:
        result = urlparse(url.strip())
        return result.scheme in ("http", "https") and bool(result.netloc)
    except Exception:
        return False


def detect_platform(url: str) -> str:
    """
    Return the platform name for *url*.

    Returns one of: ``youtube``, ``twitch``, ``kick``, ``instagram``,
    ``twitter``, ``tiktok``, ``pinterest``, ``vecteezy``, ``direct``, or ``unknown``.
    """
    if not is_valid_url(url):
        return "unknown"

    for name, pattern in _PLATFORM_PATTERNS:
        if pattern.search(url):
            return name

    # If it looks like a direct media link
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in (".mp4", ".mp3", ".m4a", ".webm", ".mkv", ".wav", ".flac", ".ogg")):
        return "direct"

    return "unknown"


def is_playlist(url: str) -> bool:
    """Return *True* if *url* appears to be a playlist URL."""
    return any(p.search(url) for p in _PLAYLIST_PATTERNS)


def platform_display_name(url: str) -> str:
    """Return a human-readable label for the URL's platform."""
    _LABELS = {
        "youtube": "YouTube",
        "twitch": "Twitch",
        "kick": "Kick",
        "instagram": "Instagram",
        "twitter": "Twitter/X",
        "tiktok": "TikTok",
        "pinterest": "Pinterest",
        "vecteezy": "Vecteezy",
        "direct": "Direct",
        "unknown": "URL",
    }
    return _LABELS.get(detect_platform(url), "URL")
