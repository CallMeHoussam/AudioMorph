#!/usr/bin/env bash
# AudioMorph Web App macOS / Linux Launcher

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$DIR"

if [ -f ".venv/bin/python" ]; then
    .venv/bin/python web_app/run_web.py
else
    python3 web_app/run_web.py
fi
