# 🌐 AudioMorph Web Application

**AudioMorph Web** is a universal, multi-platform web version of AudioMorph. It allows users on **Windows, macOS, Linux, iOS, and Android** to convert, download, trim, and generate subtitles without downloading or installing desktop software.

---

## 🚀 Quick Start

### Running on Windows
Double-click `run_web.bat` inside the `web_app` folder, or run:
```cmd
.venv\Scripts\python.exe web_app\run_web.py
```

### Running on macOS / Linux
Open Terminal in the project root and run:
```bash
chmod +x web_app/run_web.sh
./web_app/run_web.sh
```

---

## 📱 Accessing from Mac / iPhone / Android on Local Wi-Fi
When you run `run_web.py`, it will output a local network address like:
```text
http://192.168.1.15:8000
```
Simply enter that URL into Safari or Chrome on your **Mac, iPhone, iPad, or Android phone** connected to the same Wi-Fi network!

---

## ☁️ Deploying Online for the Public (Zero Download)

You can host AudioMorph Web online so anyone in the world can use it via a website link:

1. **Render.com / Railway.app (Free / Low-Cost Hosting)**:
   - Connect your GitHub repository.
   - Choose **Docker** as the runtime environment.
   - Point to `web_app/Dockerfile`.

2. **HuggingFace Spaces**:
   - Create a new **Docker Space**.
   - Push this codebase to HuggingFace.
   - Public users get a free public URL (`https://huggingface.co/spaces/...`).

---

## ✨ Web App Features
- **🔄 Transcoder**: Convert MP3, WAV, FLAC, M4A, MP4, MKV.
- **📥 URL Downloader**: YouTube, Vecteezy, TikTok, Instagram, Kick.
- **✂️ Audio Cutter**: Precise start/end timestamp trimming.
- **📝 AI Subtitles**: Whisper AI automatic SRT caption generator.
- **🎤 Vocal Isolator**: Vocal and instrumental stem extractor.
