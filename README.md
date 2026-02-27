# AudioMorph 🎵🎬

AudioMorph is a powerful, user-friendly desktop application built with Python and CustomTkinter for downloading videos and audio from the web. It is fully integrated with `yt-dlp` and `ffmpeg` to support downloading media in high quality and automatically merging or converting files.

## Features ✨
* **High-Quality Video Downloads**: Support for downloading up to 4K resolutions (when available).
* **Audio Extraction**: Easily download "Audio Only" versions and automatically convert them to the highest quality `mp3` or `m4a`.
* **Smart Format Selection**: Prioritizes `mp4` and `m4a` streams to ensure 100% compatibility with standard video players and flawless audio merging.
* **Modern GUI**: A beautiful, fluid dark/light mode desktop user interface powered by CustomTkinter. 
* **Built-in FFmpeg**: Integrates a seamless FFmpeg engine so users never have to deal with installing it themselves to merge video/audio streams.

## Installation 🛠️

### **Option 1: The Portable ZIP (For Users)**
If you were provided the `AudioMorph_Portable.zip` file, you don't need to install Python!
1. Right-click the `.zip` file and select **Extract All**.
2. Open the newly extracted folder.
3. Double-click on `AudioMorph.exe` to launch the app!
4. *(Optional)* You can right-click `AudioMorph.exe` and select **Send to > Desktop (create shortcut)** for easier access.

### **Option 2: Running from Source**
If you want to view, edit, or run the source code directly:
1. Ensure you have Python 3.1x installed.
2. Clone this repository or download the source code files.
3. Open a terminal/command prompt in the `AudioMorph` folder.
4. Install all dependencies from the `requirements.txt` file:
   ```bash
   pip install -r requirements.txt
   ```
5. Run the application:
   ```bash
   python main.py
   ```

### **Building it yourself (Pyinstaller)**
To pack the application into your own standalone version:
```bash
pyinstaller --noconfirm --onedir --windowed --add-data "ffmpeg_engine;ffmpeg_engine/" --collect-all customtkinter --collect-all tkinterdnd2 --collect-all PIL --name "AudioMorph" main.py
```
This will generate a `./dist/AudioMorph/` folder containing the executable.

## How to use 🚀
1. Go to any supported streaming website (like YouTube). 
2. Copy the video URL.
3. Open **AudioMorph** and paste the URL.
4. Select your desired Quality (e.g., 4K, 1080p, Audio Only).
5. Ensure your desired output format is selected.
6. Click Download! The file will be processed and saved into your `Downloads` directory (or your custom specified folder).

### Disclaimer
This application uses `yt-dlp`. Ensure you comply with the Terms of Service of the sites you are downloading from.
