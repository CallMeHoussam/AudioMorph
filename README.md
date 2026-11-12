# AudioMorph Studio 🎵🎬✨

<p align="center">
  <img src="icon.ico" alt="AudioMorph Studio Logo" width="96" height="96" />
</p>

<p align="center">
  <strong>The Flagship Luxury Desktop Media Suite for Windows</strong><br>
  Universal Converter • Custom Video Watermark Studio • Web Stream Downloader • AI Creative Tools
</p>

<p align="center">
  <a href="https://github.com/<YOUR_USERNAME>/AudioMorph/releases/latest">
    <img src="https://img.shields.io/badge/Download_for_Windows-v2.1_Installer-7C3AED?style=for-the-badge&logo=windows&logoColor=white" alt="Download for Windows" />
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows_10_%2F_11_x64-09090D?style=flat-square&logo=windows" alt="Platform" />
  <img src="https://img.shields.io/badge/UI_Design-Obsidian_%26_Royal_Amethyst-13131C?style=flat-square" alt="Theme" />
  <img src="https://img.shields.io/badge/Engine-FFmpeg_7_Hardware_Accelerated-6D28D9?style=flat-square" alt="Engine" />
  <img src="https://img.shields.io/badge/License-MIT-10B981?style=flat-square" alt="License" />
</p>

---

## ⚡ Quick Install (For Regular Users)

No Python, coding knowledge, or command-line setup is required!

1. **Download:** Click the button above or visit [Releases Latest](https://github.com/<YOUR_USERNAME>/AudioMorph/releases/latest) and download **`AudioMorph_Setup_v2.1.exe`**.
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
│  CREATIVE & AI  │ • Cinema Video Preview & Scrubber Stage  │ • Destination Chip     │
│  PRO STUDIO     │ • Modern Interactive File Queue Cards    │ • Pinned Action CTA    │
└─────────────────┴──────────────────────────────────────────┴────────────────────────┘
```

---

## ✨ Features Breakdown

### 💎 1. Custom Video Watermark Studio
- **3-Tab Modular Inspector:**
  - **Content:** Text signature or custom logo upload (`PNG`, `JPG`, `WebP` with transparent alpha support), font families, weights, and live typography sizing.
  - **Effects:** Progressive disclosure controls for drop shadow (intensity/offset), outer stroke/outline, and frosted background badge box.
  - **Layout:** Live opacity slider (`0%` to `100%`), free rotation (`-180°` to `+180°`), 9-point quick snap grid, and edge-safe margins.
- **Interactive Cinema Stage:** Drag the watermark directly on the video canvas to position it with real-time coordinate syncing.
- **Video Playback Scrubber:** Multi-threaded frame streamer with interactive timeline seek slider, play/pause transport, and timestamp readouts.
- **1:1 WYSIWYG Rendering:** Guaranteed pixel-identical watermark placement on exports matching the live preview across `16:9`, `9:16` (Reels/TikTok), and `1:1` formats.
- **Preset Management:** Save, recall, update, and delete branded signature templates (includes default `@evoless.editor` preset).

### 🔄 2. Universal Media Converter
- **Audio:** MP3, WAV, AAC, FLAC (with lossless metadata preservation and loudness balance).
- **Video:** MP4, MKV, MOV, AVI (H.264/AAC with CRF quality presets).
- **Image:** JPG, PNG, WEBP, ICO (smart multi-resolution icon scaling).
- **Archive:** ZIP, TAR packaging with instant compression.
- **Modern Queue List:** Individual file cards with format badges, file size readouts, per-file mini progress bars, and emerald completion pills.

### ⬇️ 3. Multi-Platform Web Stream Downloader
- **Supported Platforms:** YouTube (up to 4K + playlists), TikTok, Instagram (Reels & Stories), Twitch, Kick, and X (Twitter).
- **Audio Extraction:** High-fidelity conversion to MP3, M4A, FLAC, or WAV.
- **Visual Feedback:** Real-time transfer speed, ETA countdown, and clean task cancellation.

### 🤖 4. Creative AI Tools
- **AI Background Remover:** Fast cutout tool for images.
- **AI Subtitles:** Automated speech-to-text subtitle generator for video and audio.
- **Vocal Isolator:** Split musical tracks into isolated vocals and backing stems with integrated waveform preview player.
- **Audio Trimmer & Cutter:** Precise audio clipping tool with millisecond timeline scrubbing.

---

## 🎨 Luxury Obsidian Design System

AudioMorph Studio incorporates modern design principles inspired by Linear, Raycast, and DaVinci Resolve:
- **Obsidian & Royal Amethyst Palette:** Deep matte background (`#09090D`), panel surfaces (`#13131C`), card elevation (`#1A1A26`), and royal purple highlights (`#6D28D9` / `#7C3AED`).
- **Crisp Supersampled Vector Icons:** 23 programmatic anti-aliased vector icons rendered at 2x resolution with `Image.LANCZOS` downsampling.
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
git clone https://github.com/<YOUR_USERNAME>/AudioMorph.git
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
AudioMorph_Setup_v2.1.exe
```

---

## 📂 Repository Structure

```
AudioMorph/
├── core/                        # Background processing & engines
│   ├── ai_worker.py             # Multi-threaded AI workflow queue
│   ├── download_worker.py       # Stream download queue worker
│   ├── downloader.py            # yt-dlp core wrapper & sanitizers
│   ├── universal_engine.py      # Core conversion router
│   ├── video_preview.py         # Streaming frame decoder & seek engine
│   ├── watermark_renderer.py    # 1:1 WYSIWYG watermark compositing engine
│   ├── watermark_worker.py      # Batch video watermark export worker
│   └── worker.py                # Multi-threaded conversion worker
├── ffmpeg_engine/               # FFmpeg wrapper & presets
│   ├── bin/                     # Bundled binaries (ignored in git)
│   ├── presets/                 # VPX & video encoding presets
│   └── engine.py                # Process execution & duration parsing
├── gui/                         # Presentation layer (CustomTkinter)
│   ├── app_window.py            # Master 3-column studio layout & navigation
│   ├── watermark_widget.py      # Watermark Studio (Inspector, Stage, Queue)
│   ├── queue_cards.py           # ModernQueueList & EmptyDropzoneHero
│   ├── icons.py                 # Supersampled programmatic vector icons
│   ├── theme.py                 # Obsidian & Royal Amethyst design tokens
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

Created with passion by **Evoless**.
