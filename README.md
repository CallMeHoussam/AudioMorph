# AudioMorph Studio 🎵🎬✨

<p align="center">
  <img src="icon.ico" alt="AudioMorph Studio Logo" width="96" height="96" />
</p>

<p align="center">
  <strong>The Flagship Luxury Desktop Media Suite for Windows</strong><br>
  AI Viral Clipper Studio • Online Stream Trimmer • Universal Converter • Custom Video Watermark Studio • Web Downloader • AI Creative Suite
</p>

<p align="center">
  <a href="https://github.com/CallMeHoussam/AudioMorph/releases/latest">
    <img src="https://img.shields.io/badge/Download_for_Windows-v2.2_Installer-7C3AED?style=for-the-badge&logo=windows&logoColor=white" alt="Download for Windows" />
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows_10_%2F_11_x64-09090D?style=flat-square&logo=windows" alt="Platform" />
  <img src="https://img.shields.io/badge/UI_Design-Obsidian_%26_Royal_Amethyst-13131C?style=flat-square" alt="Theme" />
  <img src="https://img.shields.io/badge/AI_Engine-Gemini_%2F_OpenAI_%2F_Ollama_%2F_Heuristic-6D28D9?style=flat-square" alt="AI Engine" />
  <img src="https://img.shields.io/badge/Video_Engine-FFmpeg_7_Hardware_Accelerated-4F46E5?style=flat-square" alt="Engine" />
  <img src="https://img.shields.io/badge/License-MIT-10B981?style=flat-square" alt="License" />
</p>

---

## ⚡ Quick Install (For Regular Users)

No Python, coding knowledge, or command-line setup is required!

1. **Download:** Click the button above or visit [Releases Latest](https://github.com/CallMeHoussam/AudioMorph/releases/latest) and download **`AudioMorph_Setup_v2.2.exe`**.
2. **Install:** Double-click the installer and follow the 3-click setup wizard.
3. **Launch:** Open **AudioMorph Studio** directly from your Desktop or Start Menu. All engines, video codecs, and dependencies are 100% pre-packaged and ready out of the box!

---

## 🌟 What is AudioMorph Studio?

**AudioMorph Studio** is a unified desktop creative station engineered with an obsidian surface hierarchy, royal purple accents, vector iconography, and high-performance multi-threaded background workers.

```
┌─────────────────┬──────────────────────────────────────────┬────────────────────────┐
│  SIDEBAR RAIL   │       CENTER WORKSPACE / TIMELINE        │   EXPORT & DELIVERY    │
│  ────────────   │       ───────────────────────────        │   ─────────────────    │
│  CONVERT SUITE  │ • Contextual Top Workspace Header        │ • Format & Codec Cards │
│  WEB & STREAM   │ • 3-Tab Watermark Inspector              │ • Quality Selectors    │
│  CREATIVE & AI  │ • AI Viral Stream Clipper Studio         │ • 9:16 Packaging Tools │
│  PRO STUDIO     │ • Remote Frame Stream Trimmer            │ • Pinned Action Dock   │
└─────────────────┴──────────────────────────────────────────┴────────────────────────┘
```

---

## ✨ Features Breakdown

### ⚡ 1. AI Viral Stream Clipper Studio (Flagship)
Transform multi-hour YouTube streams, Twitch VODs, podcasts, or local videos into viral 9:16 short-form reels for **TikTok**, **YouTube Shorts**, and **Instagram Reels** with 1 click:
- **Flexible Source Ingestion:** Paste any online stream URL (YouTube, Twitch, Kick, X) or drag & drop local high-res video files (`MP4`, `MKV`, `MOV`, `WebM`).
- **Transcript & Subtitles Engine:**
  - Auto-fetch YouTube captions in milliseconds via `yt-dlp` (`--write-auto-subs --skip-download`) without downloading the video.
  - Or drag & drop custom `.srt` / `.vtt` subtitle files.
- **AI Viral Director Controls:**
  - Target clip count (1 to 30 clips) and target duration (15s to 90s).
  - Custom topic and keywords focus prompt (e.g. *"funniest moments, rage, plot twists, crypto, insane gameplay"*).
  - Sentence-Completion Guard with smart audio breathing room (`-0.25s` intro padding, `+0.35s` outro buffer) so clips never cut off mid-word.
- **Pluggable AI & Local Engines:**
  - **Google Gemini API:** Native high-speed analysis using standard HTTP requests (no heavy SDK overhead).
  - **OpenAI-Compatible:** Connect to OpenAI (GPT-4o/mini), Groq, OpenRouter, or DeepSeek.
  - **Local Ollama:** Run 100% offline and private on your local GPU (Llama 3, Mistral, Qwen).
  - **Built-in Heuristic Highlight Scanner:** Instant offline fallback analyzing punctuation density, speech tempo, dialogue intensity, and exclamation hooks without requiring any API key.
- **Multi-Hour Stream Chunking:** Automatically divides massive streams into ~15-minute windows with 90-second semantic overlap to prevent lost context across boundaries.
- **Interactive Cinema Stage & Clip Curation:**
  - Ranked clip cards with Virality Score pills (`95+ Viral`), auto-generated click-worthy titles, hook quotes, and duration readouts.
  - Fine-tune clip boundaries in real-time with `[-1s]` and `[+1s]` nudge buttons.
  - Live 9:16 frame guidelines and transport controls on the video canvas.
- **1-Click Viral Reel Packaging:**
  - **Smart 9:16 Reframe Modes:**
    - `Smart Center Crop (9:16)`: Precision crop centered on the action.
    - `Blurred Background Fit`: Ultra-popular aesthetic stacking blurred background fill behind the sharp original video.
    - `Split-Screen (Top / Bottom)`: Perfect for reaction videos, gaming facecams, and mobile reels.
  - **Dynamic Burned-in Subtitles (ASS):** Fast word-by-word highlighted captions rendered in 3 viral styles (*Modern Bold White*, *Viral Purple Highlight*, *Yellow Pop*).
  - **Automated Watermark Overlay:** Integrates with Watermark Studio templates (e.g. `Evoless Signature`) to automatically watermark every generated reel.
  - **Single-Pass FFmpeg Pipeline:** Chains reframe, watermark, and subtitles into a single hardware-accelerated pass.

---

### ✂️ 2. YouTube & Web Online Stream Trimmer
Download only the exact segment you need without wasting bandwidth or disk space downloading the full multi-hour video:
- **Instant Remote Frame Extraction:** Leverages FFmpeg HTTP range-seeking and direct CDN streams to fetch preview frames in milliseconds.
- **Dual-Range Timeline:** Interactive Start/End sliders with live visual timestamp updates and direct manual time entry (`HH:MM:SS` or `MM:SS`).
- **Debounced Remote Scrubbing:** Smooth preview scrubbing with a 250ms debounced background worker.
- **Quick Preset Buttons:** Instant clip length buttons (`30s`, `1m`, `3m`, `5m`) for rapid trimming.
- **Precision Section Download:** Instructs `yt-dlp` (`--download-sections`) or direct FFmpeg range pipes to download and mux strictly the selected timestamp window.

---

### 💎 3. Custom Video Watermark Studio
- **3-Tab Modular Inspector:**
  - **Content:** Text signature or custom logo upload (`PNG`, `JPG`, `WebP` with transparent alpha support), font families, weights, and live typography sizing.
  - **Effects:** Progressive disclosure controls for drop shadow (intensity/offset), outer stroke/outline, and frosted background badge box.
  - **Layout:** Live opacity slider (`0%` to `100%`), free rotation (`-180°` to `+180°`), 9-point quick snap grid, and edge-safe margins.
- **Interactive Cinema Stage:** Drag the watermark directly on the video canvas to position it with real-time coordinate syncing.
- **Video Playback Scrubber:** Multi-threaded frame streamer with interactive timeline seek slider, play/pause transport, and timestamp readouts.
- **1:1 WYSIWYG Rendering:** Guaranteed pixel-identical watermark placement on exports matching the live preview across `16:9`, `9:16` (Reels/TikTok), and `1:1` formats.
- **Preset Management:** Save, recall, update, and delete branded signature templates (includes default `@evoless.editor` preset).

---

### 🔄 4. Universal Media Converter
- **Audio:** MP3, WAV, AAC, FLAC (with lossless metadata preservation and loudness balance).
- **Video:** MP4, MKV, MOV, AVI (H.264/AAC with CRF quality presets).
- **Image:** JPG, PNG, WEBP, ICO (smart multi-resolution icon scaling).
- **Archive:** ZIP, TAR packaging with instant compression.
- **Modern Queue List:** Individual file cards with format badges, file size readouts, per-file mini progress bars, and emerald completion pills.

---

### ⬇️ 5. Multi-Platform Web Stream Downloader
- **Supported Platforms:** YouTube (up to 4K + playlists), TikTok, Instagram (Reels & Stories), Twitch, Kick, and X (Twitter).
- **Audio Extraction:** High-fidelity conversion to MP3, M4A, FLAC, or WAV.
- **Visual Feedback:** Real-time transfer speed, ETA countdown, and clean task cancellation.

---

### 🤖 6. Creative AI Suite
- **AI Background Remover:** Fast cutout tool for images.
- **AI Subtitles:** Automated speech-to-text subtitle generator for video and audio.
- **Vocal Isolator:** Split musical tracks into isolated vocals and backing stems with integrated waveform preview player.
- **Audio Trimmer & Cutter:** Precise audio clipping tool with millisecond timeline scrubbing.

---

## 🎨 Luxury Obsidian Design System

AudioMorph Studio incorporates modern design principles inspired by Linear, Raycast, and DaVinci Resolve:
- **Obsidian & Royal Amethyst Palette:** Deep matte background (`#09090D`), panel surfaces (`#13131C`), card elevation (`#1A1A26`), and royal purple highlights (`#6D28D9` / `#7C3AED`).
- **Crisp Supersampled Vector Icons:** 25+ programmatic anti-aliased vector icons rendered at 2x resolution with `Image.LANCZOS` downsampling.
- **Empty-State Dropzone Heroes:** Clutter-free onboarding states with drag-and-drop support (`tkinterdnd2`).
- **Responsive 3-Column Studio Layout:** Fixed-width navigation rail (`230px`), expandable center workspace, and scrollable right export inspector with pinned action dock.

---

## 💻 Run from Source (Developers)

If you want to contribute, modify, or run AudioMorph directly in Python:

### 1. Prerequisites
- **OS:** Windows 10 / 11 (x64)
- **Python:** 3.10+ (Python 3.13 tested)
- **Git**

### 2. Clone Repository
```bash
git clone https://github.com/CallMeHoussam/AudioMorph.git
cd AudioMorph
```

### 3. Setup Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 4. FFmpeg Engine Requirement
AudioMorph relies on `ffmpeg.exe` and `ffprobe.exe` for media processing:
- **Default Source Path:** Place `ffmpeg.exe` and `ffprobe.exe` inside `ffmpeg_engine/bin/`, **or**
- **System PATH:** AudioMorph automatically detects FFmpeg if it is installed in your Windows `PATH`.

### 5. Launch the Application
```bash
python main.py
```

---

## 📦 Building Standalone Installer

To build the standalone Windows executable and Inno Setup installer:

```powershell
# 1. Compile standalone executable with PyInstaller
pyinstaller --noconfirm --clean AudioMorph.spec

# 2. Compile Windows single-file installer (requires Inno Setup 6)
& "C:\Users\Evoless\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

The compiled installer will be generated at the root directory:
```
AudioMorph_Setup_v2.2.exe
```

---

## 📂 Repository Structure

```
AudioMorph/
├── core/                        # Background processing & engines
│   ├── ai_worker.py             # Multi-threaded AI workflow queue
│   ├── download_worker.py       # Stream download queue worker
│   ├── downloader.py            # yt-dlp core wrapper & sanitizers
│   ├── online_trimmer.py        # Remote stream metadata, frame grabber & precision segment trimmer
│   ├── universal_engine.py      # Core conversion router
│   ├── video_preview.py         # Streaming frame decoder & seek engine
│   ├── viral_clipper.py         # AI Director, LLM APIs (Gemini/OpenAI/Ollama), chunker & snapping
│   ├── viral_export_worker.py   # 1-Click 9:16 reframe, ASS subtitle generator & watermark compositor
│   ├── watermark_renderer.py    # 1:1 WYSIWYG watermark compositing engine
│   ├── watermark_worker.py      # Batch video watermark export worker
│   └── worker.py                # Multi-threaded conversion worker
├── ffmpeg_engine/               # FFmpeg wrapper & presets
│   ├── bin/                     # Bundled binaries (ignored in git)
│   ├── presets/                 # VPX & video encoding presets
│   └── engine.py                # Process execution & duration parsing
├── gui/                         # Presentation layer (CustomTkinter)
│   ├── app_window.py            # Master 3-column studio layout & navigation
│   ├── icons.py                 # Supersampled programmatic vector icons
│   ├── online_trimmer_widget.py # Remote stream trimmer drawer with timeline & preview canvas
│   ├── queue_cards.py           # ModernQueueList & EmptyDropzoneHero
│   ├── theme.py                 # Obsidian & Royal Amethyst design tokens
│   ├── viral_clipper_widget.py  # 3-Column AI Viral Stream Clipper Studio
│   ├── watermark_widget.py      # Watermark Studio (Inspector, Stage, Queue)
│   ├── cutter_widget.py         # Precision audio trim widget
│   ├── subtitle_widget.py       # AI subtitle transcript editor
│   ├── bg_remover_widget.py     # AI background remover tool
│   └── vocal_isolation_widget.py# Vocal isolation & player tool
├── utils/                       # Shared utilities
│   ├── config.py                # Persistent settings & preset manager
│   ├── logger.py                # Structured rotating logger
│   └── validators.py            # URL & path validators
├── AudioMorph.spec              # PyInstaller production build specification
├── installer.iss                # Inno Setup 6 Windows installer script
├── requirements.txt             # Project dependencies
├── settings.example.json        # Template configuration file
├── icon.ico                     # Application brand icon
├── main.py                      # Application entry point
└── README.md                    # Project documentation
```

---

## 📄 License
This project is licensed under the **MIT License**.

Created with passion by **Evoless** • [GitHub Repository](https://github.com/CallMeHoussam/AudioMorph.git)
