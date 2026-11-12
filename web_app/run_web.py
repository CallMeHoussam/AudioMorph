"""
AudioMorph Web Application Launcher
Starts the Uvicorn web server accessible locally and on your local Wi-Fi network.
"""

import sys
import os
import socket
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output encoding for console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def get_local_ip() -> str:
    """Find local network IP for cross-device access (Mac, iPhone, Android)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def main():
    import uvicorn
    host_ip = get_local_ip()
    port = 8000
    
    print("\n" + "=" * 60)
    print(" AudioMorph Web Application Running!")
    print("=" * 60)
    print(f" Local Access (This PC):    http://localhost:{port}")
    print(f" Network Access (Mac/Phone): http://{host_ip}:{port}")
    print("=" * 60 + "\n")

    uvicorn.run("web_app.server:app", host="0.0.0.0", port=port, reload=True)

if __name__ == "__main__":
    main()
