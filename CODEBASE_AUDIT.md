# AudioMorph Studio — Technical Codebase Audit

**Date:** 2026-11-25  
**Scope:** Full-repository inspection of `main.py`, `gui/`, `core/`, `ffmpeg_engine/`, `utils/`, `AudioMorph.spec`, `installer.iss`, and `web_app/`.

---

## 1. Architecture & How the Code Actually Runs (End-to-End Flow)

### Startup & Entry Point (`main.py`)
1. `main.py` adds the project root to `sys.path` and initializes rotating file + console logging (`utils/logger.py` -> `audiomorph.log`, max 2 MB × 3 backups).
2. In dev mode (not frozen), it spawns a daemon thread `_try_update_ytdlp()` running `pip install --upgrade yt-dlp` silently in the background.
3. Calls `AudioMorphApp().mainloop()` (`gui/app_window.py`) with `multiprocessing.freeze_support()`.

### Master UI Shell (`gui/app_window.py`)
- **Layout:** 3-column CustomTkinter grid (`230px` left navigation rail, expandable center workspace, `280px` right `EXPORT & DELIVERY` dock).
- **Modes:**
  - **Queue-based modes** (`CONVERT`, `DOWNLOAD`, `AI_TOOLS`): Share `self.queue_frame`, `self.file_queue`, `ModernQueueList`, and the right export dock.
  - **Full-screen studio modes** (`VIRAL_CLIPPER`, `WATERMARK`, `CUT`, `SUBTITLES`, `BG_REMOVER`, `VOCAL_ISOLATION`): Mounted as `CTkFrame` instances inside `center_container` and toggled via `grid()` / `grid_remove()`.
- **Settings Persistence (`utils/config.py`):** Loads `settings.json` on startup, merges with `DEFAULT_SETTINGS`, and saves synchronously on export/action start or preset changes.
- **Binary Resolution (`utils/config.py`):** `get_ffmpeg_path()`, `get_ffprobe_path()`, and `get_ffplay_path()` check `<root>/ffmpeg_engine/bin/` first, then fall back to system `PATH`.

### Execution & Threading Model by Feature
- **Media Converter:** `AudioMorphApp.start_action()` -> `core/worker.py::ConversionWorker` -> `ThreadPoolExecutor(max_workers=max(1, os.cpu_count() - 1))` -> `ffmpeg_engine/engine.py::FFmpegEngine.convert()`. Image/archive formats (`zip`, `tar`) are handled in Python; audio/video go through `FFmpeg`.
- **Media Downloader:** `DownloadWorker` (`core/download_worker.py`) runs `max_workers=1` sequentially -> `core/downloader.py::DownloaderEngine.download()` using `yt-dlp`, with regex/HTML web-scraping fallbacks for stock/Cloudflare-protected image/video pages, and appends to `download_history.json`.
- **Online Stream Trimmer:** `gui/online_trimmer_widget.py::OnlineTrimmerDrawer` -> `core/online_trimmer.py::fetch_stream_info()` resolves direct URLs + lightweight `<=720p` preview URLs via `yt-dlp`. Live playback spawns `OnlineStreamPlayer` (an `ffmpeg` raw RGB24 pipe at 24 fps + optional `ffplay` audio process). Final clip export calls `download_trimmed_segment()` (direct `ffmpeg -ss ... -to ...` with fallback to `yt-dlp` `download_ranges`).
- **Viral Clipper Studio:** `gui/viral_clipper_widget.py::ViralClipperWidget` -> `core/viral_clipper.py::analyze_stream_for_viral_clips()` (fetches SRT/VTT via `yt-dlp` or local file, chunks transcripts, queries Gemini/OpenAI/Ollama, or falls back to `fallback_heuristic_highlights()`) -> `core/viral_export_worker.py::ViralExportWorker` (renders 9:16 reframed video + ASS subtitles + watermark PNG in one `ffmpeg` pass).
- **Watermark Studio:** `gui/watermark_widget.py` + `core/watermark_renderer.py` (Pillow RGBA rendering) + `core/video_preview.py` (`ffmpeg` frame extraction) + `core/watermark_worker.py` -> `FFmpegEngine.watermark_video()`.
- **Standalone AI/Audio Studios:** `BgRemoverWidget`, `SubtitleWidget`, `VocalIsolationWidget`, and `AudioCutterWidget` each manage their own `tempfile.mkdtemp()` directory, spawn their own background threads/subprocesses, and use `pygame.mixer` (where audio playback exists).

---

## 2. What Is Working & Well-Built

- **Design System & Navigation (`gui/theme.py`, `gui/icons.py`, `gui/queue_cards.py`):** Cohesive Obsidian (`#09090D` / `#13131C`) & Royal Amethyst (`#6D28D9`) theme, supersampled PIL vector icons, clean empty states, and responsive 3-column layout.
- **Watermark Studio (`gui/watermark_widget.py`, `core/watermark_renderer.py`, `core/watermark_worker.py`):** Real WYSIWYG RGBA compositing (text, fonts, shadows, outlines, backgrounds, image logos, rotation, opacity), persistent presets (`Evoless Signature`), batch export, and lossless audio stream-copy with fallback re-encode.
- **Online Stream Trimmer (`core/online_trimmer.py`, `gui/online_trimmer_widget.py`):** Real-time 24 fps FFmpeg pipe player, URL timestamp extraction (`&t=8392s`, `2h19m52s`), interactive range-highlighted timeline, `Preview Cut` boundary auto-pause, and direct segment downloading without downloading the full video.
- **Viral Clipper Pipeline (`core/viral_clipper.py`, `core/viral_export_worker.py`):** Real SRT/VTT parser, sentence-boundary snapping, multi-provider LLM integration (Gemini, OpenAI, Ollama), and single-pass `ffmpeg` 9:16 reframing + ASS subtitle burning + watermark overlay.
- **Media Downloader (`core/downloader.py`):** Solid `yt-dlp` wrapper with cancellation hooks, progress parsing, and web-scraping fallbacks.
- **Audio Cutter (`gui/cutter_widget.py`):** Real waveform extraction, zoom/scroll canvas, `pygame.mixer` playback, and FFmpeg trim export.
- **Packaging (`AudioMorph.spec`, `installer.iss`):** Working PyInstaller + Inno Setup 6 pipeline producing `AudioMorph_Setup_v2.2.exe`.

---

## 3. Dead Code, Placeholders & "UI-Only / Mock / Half-Wired" Features

1. **Dead Module — `core/universal_engine.py`:**
   - Contains `UniversalEngine` with an unimplemented `cancel()` (`pass`). It is **never imported or called anywhere**; `ConversionWorker` uses `FFmpegEngine` directly.
2. **Broken / Unbundled AI Dependencies in Frozen App (`core/ai_worker.py`, `gui/bg_remover_widget.py`, `gui/subtitle_widget.py`, `gui/vocal_isolation_widget.py`):**
   - `requirements.txt` does **not** include `rembg`, `openai-whisper`, `demucs`, or `spleeter`, and `AudioMorph.spec` does not bundle them.
   - In the compiled `.exe` (`AudioMorph_Setup_v2.2.exe`), clicking **AI Background Remover**, **AI Subtitles**, or **Vocal Isolator** will fail with `"rembg not found"`, `"Run 'pip install openai-whisper'"`, or `"Run 'pip install demucs'"`.
   - Furthermore, `AIWorker._process_subtitles()` hardcodes `--language ar` and an Arabic `--initial_prompt`, ignoring any user language/model choice.
   - `VocalIsolationWidget` button initially says `ISOLATE (SPLEETER)` before loading a file, then changes to `ISOLATE (AI)`.
3. **Offline Heuristic "AI" Fallback (`core/viral_clipper.py::fallback_heuristic_highlights`):**
   - When no API key is configured for Gemini/OpenAI, Viral Clipper silently runs a keyword/punctuation/word-count heuristic (`!`, `?`, words like `"crazy"`, `"secret"`, `"hack"`) and labels the results with simulated `viral_score` values. It works as a fallback, but it is **not** real AI analysis.
4. **Unused Settings Keys (`utils/config.py` vs `ffmpeg_engine/engine.py`):**
   - `DEFAULT_SETTINGS` defines `"sample_rate": "44100 Hz"` and `"channels": "Stereo"`, but `FFmpegEngine.build_command()` **never reads** `sample_rate` or `channels`.
   - `FFmpegEngine.build_command()` hardcodes `-af loudnorm=I=-16:TP=-1.5:LRA=11` on **every** audio conversion (no toggle in the UI) and hardcodes `-c:v libx264 -c:a aac -b:a 192k` for all video conversions (no CRF/preset/stream-copy control).
5. **Orphaned / Auxiliary Directories & Scratch Files:**
   - `web_app/` (FastAPI/Flask-style web server + Docker), `my_app/` (empty `pyproject.toml` skeleton), `scratch_ffplay.py`, `scratch_test.py`, `scratch_wav.py`, `test_input.docx`, and `scratch/test_suite_all.py` sit in the repo alongside the desktop app.

---

## 4. Performance Bottlenecks & What Makes the App Heavy/Slow

1. **Massive Disk/Installer Footprint (~182 MB Installer, ~500+ MB Unpacked):**
   - `ffmpeg_engine/bin/` bundles `avcodec-62.dll` (~97 MB) plus full `ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe`, and `ffmpeg_engine/lib/*.lib` / `.pc` dev files.
   - `AudioMorph.spec` bundles `yt_dlp`, `curl_cffi`, `pygame`, `customtkinter`, `PIL`, and `tkinter` runtime data.
2. **Over-Aggressive Concurrency in `ConversionWorker` (`core/worker.py`):**
   - `max_workers = max(1, os.cpu_count() - 1)` spawns up to `N-1` simultaneous `ffmpeg` processes. On an 8–16 core CPU, running 7–15 concurrent `libx264` or `loudnorm` encodes saturates RAM, disk I/O, and CPU, causing system-wide lag.
3. **Always Re-Encoding Video (`ffmpeg_engine/engine.py`, `core/online_trimmer.py`):**
   - `FFmpegEngine.build_command()` and `download_trimmed_segment()` always re-encode video with `libx264` instead of offering `-c copy` (stream copy) when container/codec compatibility allows—making simple remuxes or trims 10–50× slower than necessary.
4. **Synchronous Startup `yt-dlp` Auto-Update (`main.py`):**
   - `_try_update_ytdlp()` runs `pip install --upgrade yt-dlp` in the background on every dev launch (30s timeout), consuming network/disk I/O at startup.
5. **UI Thread Polling & Canvas Redraws:**
   - `OnlineTrimmerDrawer._poll_ui_queue()` runs every `40ms` continuously even when idle.
   - `OnlineStreamPlayer` decodes raw `560×315×3` RGB24 frames (`~529 KB/frame`) at 24 fps (~12.7 MB/s) through Python `Image.frombytes` -> `ImageTk.PhotoImage` on the Tkinter main thread, which is fine on modern CPUs but can cause GC pressure during long playback.

---

## 5. Bugs, Edge Cases & Fragile Spots

1. **Duplicate / Unmanaged Temp Directories:**
   - `BgRemoverWidget`, `SubtitleWidget`, and `VocalIsolationWidget` create `tempfile.mkdtemp(...)` in `__init__` and **never clean them up** on app exit (`_on_close()`), leaking temp files in `%TEMP%` over time.
2. **Hardcoded Windows-Only Subprocess Flags:**
   - `core/ai_worker.py` (lines 95, 108, 111) passes `creationflags=subprocess.CREATE_NO_WINDOW` unconditionally without checking `os.name == "nt"`, which would raise `AttributeError` on macOS/Linux.
3. **Audio/Video Sync Drift in `OnlineStreamPlayer` (`core/online_trimmer.py`):**
   - Video (`ffmpeg` pipe) and audio (`ffplay`) are launched as two independent subprocesses. If HTTP buffering takes 1.5s for `ffmpeg` and 0.3s for `ffplay` (or vice versa), audio and video drift out of sync with no mechanism to resync.
4. **Thread-Safety on `ConversionWorker.engines` (`core/worker.py`):**
   - `self.engines.append(engine)` and `self.engines.remove(engine)` are called from `ThreadPoolExecutor` worker threads without a `threading.Lock()`, risking race conditions during cancellation.
5. **Silent Exception Swallowing:**
   - Several `except Exception: pass` blocks (e.g., `core/online_trimmer.py`, `core/download_worker.py`) hide JSON parse or subprocess cleanup failures instead of logging them.

---

## 6. Concrete Improvement Roadmap (Prioritized)

### Quick Wins (High Impact, Low Effort)
1. **Remove `core/universal_engine.py` and root scratch files** (`scratch_*.py`, `test_input.docx`) from the main repo or move them to a separate `archive/` folder.
2. **Cap `ConversionWorker` concurrency** to `min(4, max(1, (os.cpu_count() or 2) // 2))` and add a `threading.Lock()` around `self.engines`.
3. **Clean up temp directories** in `BgRemoverWidget`, `SubtitleWidget`, and `VocalIsolationWidget` inside `AudioMorphApp._on_close()`.
4. **Guard `CREATE_NO_WINDOW`** in `core/ai_worker.py` with `subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0`.

### Core Reliability & Speed Fixes
5. **Add Stream-Copy (`-c copy`) Option** in `FFmpegEngine.build_command()` and `OnlineTrimmer` for fast lossless remuxing/trimming without `libx264` re-encoding.
6. **Wire or Remove Unused Settings:** Either hook `sample_rate`, `channels`, and an optional `loudnorm` toggle into `FFmpegEngine.build_command()`, or remove them from `DEFAULT_SETTINGS`.
7. **Fix AI Tools Packaging Story:** Either clearly gate/hide AI tools in the frozen `.exe` with an in-app "Install AI Pack / Requires Python" notice, or bundle lightweight ONNX/API-based alternatives instead of failing with raw `pip install` errors.

### Architectural & UX Upgrades
8. **Trim `ffmpeg_engine/` Dev Bloat:** Exclude `ffmpeg_engine/lib/*.lib` and `.pc` files from `AudioMorph.spec` / repo if not needed at runtime.
9. **Decouple `app_window.py` (`~69 KB`):** Extract mode controllers (Converter, Downloader, Export Dock) into smaller dedicated modules so `app_window.py` stays maintainable.
10. **Stop `OnlineTrimmerDrawer` UI Queue Polling When Idle:** Only schedule `self.after(40, ...)` while loading or playing.
