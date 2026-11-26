import os
import shutil
import subprocess
import tempfile
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk
import pygame

from core.ai_worker import check_ai_backend_available
from utils.config import get_ffmpeg_path

_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class VocalIsolationWidget(ctk.CTkFrame):
    def __init__(self, master, bg_color="#0D0D10", panel_color="#15151A", accent_color="#4B197A", **kwargs):
        super().__init__(master, fg_color=bg_color, **kwargs)
        self.bg_color = bg_color
        self.panel_color = panel_color
        self.accent_color = accent_color

        self.filepath = None
        self.temp_dir = None

        self.vocals_path = None
        self.instrumental_path = None
        self.is_playing = None  # "vocals" or "instrumental"

        if not pygame.mixer.get_init():
            pygame.mixer.init()
        self._build_ui()

    def _ensure_temp_dir(self) -> str:
        if not self.temp_dir or not os.path.isdir(self.temp_dir):
            self.temp_dir = tempfile.mkdtemp(prefix="audiomorph_vocals_")
        return self.temp_dir

    def cleanup(self) -> None:
        self.stop_audio()
        if self.temp_dir and os.path.isdir(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Top Toolbar ──────────────────────────────────────────────
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", padx=20, pady=20)

        self.btn_load = ctk.CTkButton(top_bar, text="UPLOAD AUDIO", command=self.load_file, fg_color=self.panel_color, hover_color=self.accent_color)
        self.btn_load.pack(side="left")

        self.lbl_file = ctk.CTkLabel(top_bar, text="No file selected (Drag & drop file here)", text_color="#888890")
        self.lbl_file.pack(side="left", padx=15)

        self.btn_generate = ctk.CTkButton(top_bar, text="ISOLATE VOCALS (AI)", command=self.generate_stems, fg_color=self.accent_color, state="disabled")
        self.btn_generate.pack(side="right")

        self.lbl_status = ctk.CTkLabel(top_bar, text="", text_color="#FFFFFF")
        self.lbl_status.pack(side="right", padx=15)

        # ── Playback Area ───────────────────────────────────────────
        self.preview_frame = ctk.CTkFrame(self, fg_color=self.panel_color)
        self.preview_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        self.preview_frame.grid_rowconfigure(0, weight=1)
        self.preview_frame.grid_rowconfigure(3, weight=1)
        self.preview_frame.grid_columnconfigure(0, weight=1)

        self.lbl_wait = ctk.CTkLabel(self.preview_frame, text="Upload or drag & drop an audio file to separate vocals and instrumentals.", text_color="#888890")
        self.lbl_wait.grid(row=1, column=0, pady=40)

        # Vocals UI (hidden initially)
        self.vocals_frame = ctk.CTkFrame(self.preview_frame, fg_color="#1F1F26")
        self.lbl_vocals = ctk.CTkLabel(self.vocals_frame, text="🎤 Vocals Track", font=("Segoe UI Black", 14), text_color="#FFFFFF")
        self.lbl_vocals.pack(side="left", padx=15)
        self.btn_play_v = ctk.CTkButton(self.vocals_frame, text="▶ PLAY", width=80, command=lambda: self.toggle_play("vocals"), fg_color=self.accent_color)
        self.btn_play_v.pack(side="left", padx=10, pady=10)
        self.btn_export_v = ctk.CTkButton(self.vocals_frame, text="⬇ DOWNLOAD", width=100, command=lambda: self.export_track("vocals"), fg_color="#2A2A35", hover_color=self.accent_color)
        self.btn_export_v.pack(side="right", padx=15, pady=10)

        # Instrumental UI (hidden initially)
        self.inst_frame = ctk.CTkFrame(self.preview_frame, fg_color="#1F1F26")
        self.lbl_inst = ctk.CTkLabel(self.inst_frame, text="🎸 Instrumental Track", font=("Segoe UI Black", 14), text_color="#FFFFFF")
        self.lbl_inst.pack(side="left", padx=15)
        self.btn_play_i = ctk.CTkButton(self.inst_frame, text="▶ PLAY", width=80, command=lambda: self.toggle_play("instrumental"), fg_color=self.accent_color)
        self.btn_play_i.pack(side="left", padx=10, pady=10)
        self.btn_export_i = ctk.CTkButton(self.inst_frame, text="⬇ DOWNLOAD", width=100, command=lambda: self.export_track("instrumental"), fg_color="#2A2A35", hover_color=self.accent_color)
        self.btn_export_i.pack(side="right", padx=15, pady=10)

    def load_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Audio Files", "*.mp3 *.wav *.m4a *.ogg *.flac *.mp4")])
        if not filepath:
            return
        self.load_file_from_path(filepath)

    def load_file_from_path(self, filepath):
        if not filepath or not os.path.exists(filepath):
            return
        self.filepath = filepath
        self.vocals_path = None
        self.instrumental_path = None
        self.stop_audio()

        self.lbl_file.configure(text=os.path.basename(filepath))
        self.btn_generate.configure(state="normal", text="ISOLATE VOCALS (AI)")

        self.vocals_frame.grid_remove()
        self.inst_frame.grid_remove()
        self.lbl_wait.grid(row=1, column=0, pady=40)
        self.lbl_status.configure(text="Ready.")

    # ── AI Generation ────────────────────────────────────────────────

    def generate_stems(self):
        if not self.filepath:
            return
        self.stop_audio()

        self.btn_generate.configure(state="disabled", text="PROCESSING...")
        self.lbl_status.configure(text="Running AI Separation...")
        self.lbl_wait.configure(text="Splitting track into 2 stems... (Might take 1-2 mins)")

        threading.Thread(target=self._run_ai_backend, daemon=True).start()

    def _run_ai_backend(self):
        try:
            tdir = self._ensure_temp_dir()
            for item in os.listdir(tdir):
                item_path = os.path.join(tdir, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path, ignore_errors=True)
                else:
                    os.remove(item_path)

            env = os.environ.copy()
            env["PATH"] = f"{os.path.dirname(get_ffmpeg_path())}{os.pathsep}{env.get('PATH', '')}"

            p_vocals = None
            p_inst = None

            ok_demucs, cmd_demucs, msg_demucs = check_ai_backend_available("demucs", cli_name="demucs")
            ok_spleeter, cmd_spleeter, _ = check_ai_backend_available("spleeter", cli_name="spleeter")

            if ok_demucs and cmd_demucs:
                cmd = [*cmd_demucs, "-n", "htdemucs", self.filepath, "--out", tdir]
                subprocess.run(cmd, env=env, check=True, creationflags=_CREATE_NO_WINDOW)

                base_name = os.path.splitext(os.path.basename(self.filepath))[0]
                target_dir = os.path.join(tdir, "htdemucs", base_name)
                p_vocals = os.path.join(target_dir, "vocals.wav")
                p_inst = os.path.join(target_dir, "no_vocals.wav")
            elif ok_spleeter and cmd_spleeter:
                cmd = [*cmd_spleeter, "separate", "-p", "spleeter:2stems", "-o", tdir, self.filepath]
                subprocess.run(cmd, env=env, check=True, creationflags=_CREATE_NO_WINDOW)

                base_name = os.path.splitext(os.path.basename(self.filepath))[0]
                target_dir = os.path.join(tdir, base_name)
                p_vocals = os.path.join(target_dir, "vocals.wav")
                p_inst = os.path.join(target_dir, "accompaniment.wav")
            else:
                raise RuntimeError(msg_demucs)

            if not p_vocals or not os.path.exists(p_vocals):
                for root, _, files in os.walk(tdir):
                    for f in files:
                        if "vocals" in f.lower():
                            p_vocals = os.path.join(root, f)
                            break
                    if p_vocals and os.path.exists(p_vocals):
                        break

            if p_vocals and os.path.exists(p_vocals):
                self.vocals_path = p_vocals
                self.instrumental_path = p_inst if p_inst and os.path.exists(p_inst) else None
                self.after(0, self._on_generation_success)
            else:
                raise RuntimeError("AI finished but track files not found.")

        except Exception as e:
            self.after(0, self._on_generation_error, str(e))

    def _on_generation_success(self):
        self.btn_generate.configure(state="normal", text="RE-ISOLATE")
        self.lbl_status.configure(text="Finished!")
        self.lbl_wait.grid_remove()

        self.vocals_frame.grid(row=1, column=0, sticky="ew", padx=40, pady=10)
        self.inst_frame.grid(row=2, column=0, sticky="ew", padx=40, pady=10)

    def _on_generation_error(self, err_msg):
        self.btn_generate.configure(state="normal", text="ISOLATE VOCALS (AI)")
        self.lbl_status.configure(text="Error!")
        self.lbl_wait.configure(text="Upload an audio file to separate vocals and instrumentals.")
        messagebox.showerror("AI Error", f"Offline Vocal Isolation failed:\n{err_msg}")

    # ── Playback ─────────────────────────────────────────────────────

    def stop_audio(self):
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        self.is_playing = None
        self.btn_play_v.configure(text="▶ PLAY")
        self.btn_play_i.configure(text="▶ PLAY")

    def toggle_play(self, track_type):
        was_playing = self.is_playing
        self.stop_audio()

        if was_playing == track_type:
            return

        try:
            if track_type == "vocals" and self.vocals_path:
                pygame.mixer.music.load(self.vocals_path)
                pygame.mixer.music.play()
                self.btn_play_v.configure(text="⏸ STOP")
                self.is_playing = "vocals"
            elif track_type == "instrumental" and self.instrumental_path:
                pygame.mixer.music.load(self.instrumental_path)
                pygame.mixer.music.play()
                self.btn_play_i.configure(text="⏸ STOP")
                self.is_playing = "instrumental"
        except Exception as e:
            messagebox.showerror("Playback Error", f"Could not play audio:\n{e}")

    # ── Exporting ────────────────────────────────────────────────────

    def export_track(self, track_type):
        target_path = self.vocals_path if track_type == "vocals" else self.instrumental_path
        if not target_path or not os.path.exists(target_path):
            return

        default_name = f"{os.path.splitext(os.path.basename(self.filepath))[0]}_{track_type}.wav"
        save_path = filedialog.asksaveasfilename(
            initialfile=default_name,
            defaultextension=".wav",
            filetypes=[("WAV Audio", "*.wav"), ("MP3 Audio", "*.mp3")],
        )
        if not save_path:
            return

        try:
            if save_path.lower().endswith(".wav"):
                shutil.copy2(target_path, save_path)
            else:
                subprocess.run([get_ffmpeg_path(), "-y", "-i", target_path, "-q:a", "0", save_path], creationflags=_CREATE_NO_WINDOW)

            messagebox.showinfo("Success", f"{track_type.capitalize()} track successfully exported!")
        except Exception as e:
            messagebox.showerror("Error", str(e))
