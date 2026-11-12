import os
import subprocess
import threading
import tempfile
import shutil
import re
import customtkinter as ctk
from tkinter import filedialog, messagebox

from utils.config import get_ffmpeg_path

class SubtitleWidget(ctk.CTkFrame):
    def __init__(self, master, bg_color="#0D0D10", panel_color="#15151A", accent_color="#4B197A", **kwargs):
        super().__init__(master, fg_color=bg_color, **kwargs)
        self.ffmpeg_exe = get_ffmpeg_path()
        self.bg_color = bg_color
        self.panel_color = panel_color
        self.accent_color = accent_color
        
        self.filepath = None
        self.subs_data = [] # List of dicts: {'id': int, 'start': str, 'end': str, 'text': StringVar}
        self.temp_dir = tempfile.mkdtemp(prefix="audiomorph_subs_")
        
        self._build_ui()

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # ── Top Toolbar ──────────────────────────────────────────────
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        
        self.btn_load = ctk.CTkButton(top_bar, text="UPLOAD VIDEO/AUDIO", command=self.load_file, fg_color=self.panel_color, hover_color=self.accent_color)
        self.btn_load.pack(side="left")
        
        self.lbl_file = ctk.CTkLabel(top_bar, text="No file selected (Drag & drop file here)", text_color="#888890")
        self.lbl_file.pack(side="left", padx=15)
        
        self.btn_generate = ctk.CTkButton(top_bar, text="GENERATE SUBTITLES", command=self.generate_subtitles, fg_color=self.accent_color, state="disabled")
        self.btn_generate.pack(side="right")
        
        # Model selection dropdown
        self.model_menu = ctk.CTkOptionMenu(
            top_bar,
            values=["small (Recommended)", "medium (Better Darija)", "large-v3 (Best)", "base", "tiny"],
            fg_color="#1F1F26",
            width=165
        )
        self.model_menu.pack(side="right", padx=4)
        
        # Language selection dropdown
        self.lang_menu = ctk.CTkOptionMenu(
            top_bar,
            values=["Moroccan Darija (الدارجة)", "Arabic (العربية الفصحى)", "Auto-Detect", "English", "French", "Spanish", "German", "Russian", "Turkish"],
            fg_color="#1F1F26",
            width=175
        )
        self.lang_menu.pack(side="right", padx=4)

        # Task selection dropdown (Transcribe vs Translate to English)
        self.task_menu = ctk.CTkOptionMenu(
            top_bar,
            values=["Transcribe (النسخ)", "Translate to English (الترجمة)"],
            fg_color="#1F1F26",
            width=150
        )
        self.task_menu.pack(side="right", padx=4)
        
        self.lbl_status = ctk.CTkLabel(top_bar, text="", text_color="#FFFFFF")
        self.lbl_status.pack(side="right", padx=5)
        
        # ── Subtitle Editor Area ─────────────────────────────────────
        self.editor_frame = ctk.CTkScrollableFrame(self, fg_color=self.panel_color)
        self.editor_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        
        ctk.CTkLabel(self.editor_frame, text="Upload or drag & drop a file to generate subtitles.", text_color="#888890").pack(pady=40)
        
        # ── Bottom Toolbar ───────────────────────────────────────────
        bottom_bar = ctk.CTkFrame(self, fg_color="transparent")
        bottom_bar.grid(row=2, column=0, sticky="ew", padx=20, pady=20)
        
        self.btn_export_srt = ctk.CTkButton(bottom_bar, text="EXPORT .SRT", command=self.export_srt, width=150, state="disabled", fg_color=self.panel_color)
        self.btn_export_srt.pack(side="left")
        
        self.btn_burn_video = ctk.CTkButton(bottom_bar, text="BURN INTO VIDEO", command=self.burn_video, width=150, state="disabled", fg_color="#FF3366")
        self.btn_burn_video.pack(side="right")

    def load_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Media Files", "*.mp4 *.mkv *.avi *.mov *.mp3 *.wav *.m4a")])
        if not filepath: return
        self.load_from_path(filepath)

    def load_from_path(self, filepath):
        self.filepath = filepath
        self.lbl_file.configure(text=os.path.basename(filepath))
        self.btn_generate.configure(state="normal")
        self.subs_data.clear()
        self._render_timeline()

    # ── AI Generation ────────────────────────────────────────────────

    def generate_subtitles(self):
        if not self.filepath: return
        self.btn_generate.configure(state="disabled", text="PROCESSING (Local AI)...")
        self.lbl_status.configure(text="Running Whisper AI...")
        
        # Ensure older files are cleaned
        for f in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, f))
            
        threading.Thread(target=self._run_whisper_backend, daemon=True).start()

    def _run_whisper_backend(self):
        try:
            import sys, shutil, importlib.util
            env = os.environ.copy()
            env["PATH"] = f"{os.path.dirname(self.ffmpeg_exe)};{env.get('PATH', '')}"
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            
            raw_model = self.model_menu.get().split()[0]
            raw_lang = self.lang_menu.get()
            raw_task = self.task_menu.get()
            
            lang_code_map = {
                "Moroccan Darija (الدارجة)": "ar",
                "Arabic (العربية الفصحى)": "ar",
                "English": "en",
                "French": "fr",
                "Spanish": "es",
                "German": "de",
                "Russian": "ru",
                "Turkish": "tr",
            }
            lang_code = lang_code_map.get(raw_lang, None)
            
            whisper_args = [
                self.filepath,
                "--model", raw_model,
                "--output_dir", self.temp_dir,
                "--output_format", "srt"
            ]

            if "Translate" in raw_task:
                whisper_args.extend(["--task", "translate"])
            
            if lang_code:
                whisper_args.extend(["--language", lang_code])
                if raw_lang == "Moroccan Darija (الدارجة)":
                    whisper_args.extend(["--initial_prompt", "حوار بالدارجة المغربية: كيفاش، ديال، بزاف، دابا، غادي، مزيان، شكون، فين، بغيت، واحد، خاي، خويا."])
                elif raw_lang == "Arabic (العربية الفصحى)":
                    whisper_args.extend(["--initial_prompt", "نصوص عربية دقيقة بأسلوب فصيح وواضح."])

            if importlib.util.find_spec("whisper") is not None:
                cmd = [sys.executable, "-m", "whisper"] + whisper_args
            elif shutil.which("whisper"):
                cmd = ["whisper"] + whisper_args
            else:
                raise FileNotFoundError("Whisper module not found")

            p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW, text=True, encoding="utf-8", errors="replace")
            
            # Simple progress log intercept
            for line in p.stdout:
                if "]" in line and "-->" in line: # e.g. [00:00.000 --> 00:02.000] Transcribing...
                    self.after(0, self.lbl_status.configure, {"text": "Transcribing... " + line[1:13]})
            p.wait()
            
            if p.returncode != 0:
                raise Exception("Whisper failed. Are you sure you ran `pip install openai-whisper`?")
                
            # Find the output .srt
            srt_file = None
            for f in os.listdir(self.temp_dir):
                if f.endswith(".srt"):
                    srt_file = os.path.join(self.temp_dir, f)
                    break
                    
            if not srt_file:
                raise Exception("Generation completed but .srt not found.")
                
            self._parse_srt(srt_file)
            self.after(0, self._on_generation_success)
            
        except FileNotFoundError:
            self.after(0, self._on_generation_error, "Whisper CLI not found. Please run 'pip install openai-whisper'")
        except Exception as e:
            self.after(0, self._on_generation_error, str(e))

    def _on_generation_success(self):
        self.btn_generate.configure(state="normal", text="RE-GENERATE")
        self.lbl_status.configure(text="Finished!")
        self.btn_export_srt.configure(state="normal")
        self.btn_burn_video.configure(state="normal")
        self._render_timeline()

    def _on_generation_error(self, err_msg):
        self.btn_generate.configure(state="normal", text="GENERATE SUBTITLES")
        self.lbl_status.configure(text="Error!")
        messagebox.showerror("AI Error", f"Offline Subtitle Generation failed:\n{err_msg}")

    # ── SRT Parsing & Rendering ──────────────────────────────────────

    def _parse_srt(self, srt_path):
        self.subs_data = []
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            
        # SRT block: id \n start --> end \n text
        blocks = content.split('\n\n')
        for b in blocks:
            lines = b.split('\n')
            if len(lines) >= 3:
                try:
                    idx = int(lines[0].strip())
                    time_line = lines[1]
                    text = "\n".join(lines[2:])
                    
                    if " --> " in time_line:
                        start_time, end_time = time_line.split(" --> ")
                        
                        var = ctk.StringVar(value=text)
                        
                        self.subs_data.append({
                            "id": idx,
                            "start": start_time.strip(),
                            "end": end_time.strip(),
                            "text_var": var
                        })
                except Exception:
                    pass

    def _render_timeline(self):
        # Clear frame
        for widget in self.editor_frame.winfo_children():
            widget.destroy()
            
        if not self.subs_data:
            ctk.CTkLabel(self.editor_frame, text="Generate subtitles to preview the text timeline here.", text_color="#888890").pack(pady=40)
            return

        for i, sub in enumerate(self.subs_data):
            row_frame = ctk.CTkFrame(self.editor_frame, fg_color="#1F1F26")
            row_frame.pack(fill="x", pady=2, padx=5)
            
            # Timestamp label
            ts_label = ctk.CTkLabel(row_frame, text=f"{sub['start'].split(',')[0]} → {sub['end'].split(',')[0]}", width=140, font=("Consolas", 11), text_color="#888890")
            ts_label.pack(side="left", padx=10)
            
            text_val = sub['text_var'].get()
            is_arabic = any('\u0600' <= char <= '\u06FF' for char in text_val)
            justify_mode = "right" if is_arabic else "left"
            
            # Text entry
            entry = ctk.CTkEntry(row_frame, textvariable=sub['text_var'], fg_color="#0D0D10", border_width=0, justify=justify_mode, font=("Segoe UI", 12))
            entry.pack(side="left", fill="x", expand=True, padx=10, pady=5)
            
    # ── Exporting ────────────────────────────────────────────────────

    def _get_current_srt_content(self):
        lines = []
        for i, sub in enumerate(self.subs_data):
            lines.append(str(i + 1))
            lines.append(f"{sub['start']} --> {sub['end']}")
            lines.append(sub['text_var'].get())
            lines.append("")
        return "\n".join(lines)

    def export_srt(self):
        save_path = filedialog.asksaveasfilename(defaultextension=".srt", filetypes=[("Subtitle File", "*.srt")])
        if not save_path: return
        
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(self._get_current_srt_content())
            messagebox.showinfo("Success", "Subtitles successfully exported!")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def burn_video(self):
        if not self.filepath: return
        
        save_path = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4 Video", "*.mp4"), ("MKV Video", "*.mkv")])
        if not save_path: return
        
        # Save temporary reliable SRT, ffmpeg subtitle filter needs normalized paths
        temp_srt = os.path.join(self.temp_dir, "burn_target.srt")
        with open(temp_srt, 'w', encoding='utf-8') as f:
            f.write(self._get_current_srt_content())
            
        def _do_burn():
            self.after(0, self.lbl_status.configure, {"text": "Burning subtitles into video..."})
            try:
                # ffmpeg requires escaped paths for subtitle filter
                escaped_srt = temp_srt.replace('\\', '/').replace(':', '\\:')
                cmd = [
                    self.ffmpeg_exe, "-y", "-i", self.filepath,
                    "-vf", f"subtitles='{escaped_srt}'",
                    "-c:a", "copy",
                    save_path
                ]
                subprocess.run(cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                self.after(0, lambda: messagebox.showinfo("Success", "Video with burned subtitles exported!"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Render Error", f"Failed to burn subtitles: {e}"))
            finally:
                self.after(0, self.lbl_status.configure, {"text": "Idle."})
                
        self.btn_burn_video.configure(state="disabled")
        threading.Thread(target=_do_burn, daemon=True).start()
        self.after(2000, lambda: self.btn_burn_video.configure(state="normal"))
