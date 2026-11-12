@echo off
title AudioMorph Web Launcher
cd /d "%~dp0\.."
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe web_app\run_web.py
) else (
    python web_app\run_web.py
)
pause
