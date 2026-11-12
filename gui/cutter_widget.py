import os
import subprocess
import struct
import math
import customtkinter as ctk
from tkinter import filedialog, messagebox, Canvas
import threading
import time

try:
    import pygame
    pygame.mixer.init()
except ImportError:
    pass

from utils.config import get_ffmpeg_path

class AudioCutterWidget(ctk.CTkFrame):
    def __init__(self, master, bg_color="#0D0D10", panel_color="#15151A", accent_color="#4B197A", **kwargs):
        super().__init__(master, fg_color=bg_color, **kwargs)
        self.ffmpeg_exe = get_ffmpeg_path()
        self.bg_color = bg_color
        self.panel_color = panel_color
        self.accent_color = accent_color
        
        self.filepath = None
        self.duration = 0.0
        self.waveform_data = []
        
        self.playing = False
        self.play_start_time = 0.0 # Global time when play started
        self.last_mixer_time = -1
        
        self.trim_start = 0.0
        self.trim_end = 1.0 # Will scale to duration later
        
        self.zoom = 1.0
        self.scroll_x = 0.0
        
        # UI State variables
        self.is_dragging_start = False
        self.is_dragging_end = False
        self.is_scrubbing = False
        self.current_time_var = ctk.StringVar(value="00:00 / 00:00")
        
        self._build_ui()
        self.update_timer()

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # ── Top Toolbar ──────────────────────────────────────────────
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        
        self.btn_load = ctk.CTkButton(top_bar, text="LOAD AUDIO", command=self.load_audio, fg_color=self.panel_color, hover_color=self.accent_color)
        self.btn_load.pack(side="left")
        
        self.lbl_file = ctk.CTkLabel(top_bar, text="No file selected (Drag & drop file here)", text_color="#888890")
        self.lbl_file.pack(side="left", padx=15)
        
        self.btn_export = ctk.CTkButton(top_bar, text="EXPORT CUT", command=self.export_audio, fg_color=self.accent_color, state="disabled")
        self.btn_export.pack(side="right")
        
        self.btn_zoom_in = ctk.CTkButton(top_bar, text="+", width=30, command=self.zoom_in, fg_color=self.panel_color, hover_color=self.accent_color)
        self.btn_zoom_in.pack(side="right", padx=(5, 15))
        
        self.btn_zoom_out = ctk.CTkButton(top_bar, text="-", width=30, command=self.zoom_out, fg_color=self.panel_color, hover_color=self.accent_color)
        self.btn_zoom_out.pack(side="right")
        
        # ── Waveform Area ────────────────────────────────────────────
        self.canvas_frame = ctk.CTkFrame(self, fg_color=self.panel_color)
        self.canvas_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        
        # We use a standard tkinter canvas for drawing performance
        self.canvas = Canvas(self.canvas_frame, bg=self.panel_color, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=20)
        
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Configure>", lambda e: [self._clip_scroll(), self.draw_waveform()])
        self.canvas.bind("<MouseWheel>", self.on_scroll)
        
        # ── Bottom Controls ──────────────────────────────────────────
        bottom_bar = ctk.CTkFrame(self, fg_color="transparent")
        bottom_bar.grid(row=2, column=0, sticky="ew", padx=20, pady=20)
        
        self.btn_play = ctk.CTkButton(bottom_bar, text="PLAY / PAUSE", command=self.toggle_playback, width=120, state="disabled")
        self.btn_play.pack(side="left")
        
        self.lbl_time = ctk.CTkLabel(bottom_bar, textvariable=self.current_time_var, font=("Segoe UI", 12))
        self.lbl_time.pack(side="left", padx=(20, 40))
        
        self.btn_set_start = ctk.CTkButton(bottom_bar, text="[ SET START", command=self.set_start_to_playhead, width=100, state="disabled", fg_color=self.panel_color, hover_color=self.accent_color, border_width=1, border_color="#3A3A40")
        self.btn_set_start.pack(side="left", padx=5)
        
        self.btn_set_end = ctk.CTkButton(bottom_bar, text="SET END ]", command=self.set_end_to_playhead, width=100, state="disabled", fg_color=self.panel_color, hover_color=self.accent_color, border_width=1, border_color="#3A3A40")
        self.btn_set_end.pack(side="left", padx=5)
        
        # Bind spacebar to play/pause globally if frame has focus
        if hasattr(self.master, "bind"):
            self.master.bind("<space>", self.on_space_pressed)
            
    def on_space_pressed(self, event):
        if self.winfo_ismapped():
            # Avoid toggling if typing in an entry
            if "entry" not in str(self.master.focus_get()).lower():
                self.toggle_playback()
                
    def load_audio(self):
        filepath = filedialog.askopenfilename(filetypes=[("Audio Files", "*.mp3 *.wav *.ogg *.m4a *.flac *.aac")])
        if not filepath:
            return
        self.load_audio_from_path(filepath)
            
    def load_audio_from_path(self, filepath):
        self.filepath = filepath
        self.lbl_file.configure(text=os.path.basename(filepath))
        
        # Stop existing playback
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
        self.playing = False
        
        # Get duration using ffprobe
        self._get_duration()
        
        # Extract waveform async
        self.lbl_time.configure(text="Generating waveform...")
        threading.Thread(target=self._extract_waveform, daemon=True).start()

    def _get_duration(self):
        try:
            ffprobe = os.path.join(os.path.dirname(self.ffmpeg_exe), "ffprobe.exe")
            cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", self.filepath]
            out = subprocess.check_output(cmd, creationflags=subprocess.CREATE_NO_WINDOW).decode().strip()
            self.duration = float(out)
        except Exception as e:
            self.duration = 100.0 # Fallback
            
        self.trim_start = 0.0
        self.trim_end = self.duration
        self.play_start_time = 0.0
        self.zoom = 1.0
        self.scroll_x = 0.0

    def _extract_waveform(self):
        try:
            num_points = 800
            cmd = [
                self.ffmpeg_exe, "-i", self.filepath, 
                "-ac", "1", "-filter:a", "aresample=8000",
                "-map", "0:a?", "-c:a", "pcm_s16le", "-f", "s16le", "-"
            ]
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            raw_data, _ = p.communicate()
            
            samples = struct.unpack(f"<{len(raw_data)//2}h", raw_data[:(len(raw_data)//2)*2])
            
            if not samples:
                self.waveform_data = [0]*num_points
            else:
                chunk_size = max(1, len(samples) // num_points)
                waveform = []
                for i in range(num_points):
                    chunk = samples[i*chunk_size : (i+1)*chunk_size]
                    waveform.append(max(abs(x) for x in chunk) if chunk else 0)
                
                max_val = max(waveform) if waveform else 1
                if max_val == 0: max_val = 1
                self.waveform_data = [x / max_val for x in waveform]
                
        except Exception as e:
            self.waveform_data = [0.1]*800
            
        self.after(0, self._on_waveform_ready)

    def _on_waveform_ready(self):
        self.btn_play.configure(state="normal")
        self.btn_export.configure(state="normal")
        self.btn_set_start.configure(state="normal")
        self.btn_set_end.configure(state="normal")
        
        # Load into pygame. Pygame mixer music load only supports mp3, ogg, wav reliably.
        # If it's m4a, we might need to convert it, but let's try direct load first.
        try:
            pygame.mixer.music.load(self.filepath)
        except Exception:
            # Fallback: create temporary wav
            temp_wav = os.path.join(os.path.dirname(self.filepath), "temp_audiomorph_playback.wav")
            # Clear it if exists
            if os.path.exists(temp_wav): os.remove(temp_wav)
            subprocess.run([self.ffmpeg_exe, "-i", self.filepath, "-y", temp_wav], 
                           creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            pygame.mixer.music.load(temp_wav)
            
        self.draw_waveform()

    # ── Drawing ──────────────────────────────────────────────────────────

    def draw_waveform(self):
        if not self.waveform_data:
            return
            
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        
        logical_w = w * self.zoom
        num_points = len(self.waveform_data)
        bar_width = logical_w / num_points
        
        # Calculate pixel x positions
        x_start = (self.trim_start / self.duration) * logical_w - self.scroll_x if self.duration > 0 else 0
        x_end = (self.trim_end / self.duration) * logical_w - self.scroll_x if self.duration > 0 else w
        x_play = (self.get_current_time() / self.duration) * logical_w - self.scroll_x if self.duration > 0 else 0

        # Draw bars
        for i, val in enumerate(self.waveform_data):
            x = i * bar_width - self.scroll_x
            if x + bar_width < 0 or x > w:
                continue
                
            bar_h = val * h * 0.9
            y1 = h/2 - bar_h/2
            y2 = h/2 + bar_h/2
            
            # Color logic based on selection
            if x_start <= x <= x_end:
                color = self.accent_color if x >= x_play else "#7B39CA" # brighter if passed
            else:
                color = "#3A3A40" # dim unselected
                
            self.canvas.create_rectangle(x, y1, x + bar_width, y2, fill=color, outline="", tags="wave")

        # Draw Selection Overlay
        self.canvas.create_rectangle(0, 0, x_start, h, fill="#000000", stipple="gray50", outline="")
        self.canvas.create_rectangle(x_end, 0, w, h, fill="#000000", stipple="gray50", outline="")
        
        # Draw Handles
        self.canvas.create_line(x_start, 0, x_start, h, fill="#FFFFFF", width=3, tags="handle_start")
        self.canvas.create_polygon(x_start-8, 0, x_start+8, 0, x_start, 12, fill="#FFFFFF", tags="handle_start_top")
        self.canvas.create_polygon(x_start-8, h, x_start+8, h, x_start, h-12, fill="#FFFFFF", tags="handle_start_bot")
        
        self.canvas.create_line(x_end, 0, x_end, h, fill="#FFFFFF", width=3, tags="handle_end")
        self.canvas.create_polygon(x_end-8, 0, x_end+8, 0, x_end, 12, fill="#FFFFFF", tags="handle_end_top")
        self.canvas.create_polygon(x_end-8, h, x_end+8, h, x_end, h-12, fill="#FFFFFF", tags="handle_end_bot")
        
        # Show exact timestamps of selection
        start_m, start_s = divmod(self.trim_start, 60)
        end_m, end_s = divmod(self.trim_end, 60)
        
        # Adjust anchors so they don't clip outside canvas
        start_anchor = "sw" if x_start < w - 40 else "se"
        start_offsetX = 5 if x_start < w - 40 else -5
        
        end_anchor = "se" if x_end > 40 else "sw"
        end_offsetX = -5 if x_end > 40 else 5
        
        self.canvas.create_text(x_start + start_offsetX, h - 10, text=f"{int(start_m):02d}:{start_s:04.1f}", fill="#FFFFFF", anchor=start_anchor, tags="handle_start_text")
        self.canvas.create_text(x_end + end_offsetX, h - 10, text=f"{int(end_m):02d}:{end_s:04.1f}", fill="#FFFFFF", anchor=end_anchor, tags="handle_end_text")
        
        # Draw Playhead
        self.canvas.create_line(x_play, 0, x_play, h, fill="#FF3366", width=2, tags="playhead")

    # ── Mouse Interaction & Zoom ─────────────────────────────────────────

    def zoom_in(self):
        if self.duration <= 0: return
        self.zoom *= 1.5
        self._clip_scroll()
        self.draw_waveform()

    def zoom_out(self):
        if self.duration <= 0: return
        self.zoom /= 1.5
        if self.zoom <= 1.0:
            self.zoom = 1.0
        self._clip_scroll()
        self.draw_waveform()

    def on_scroll(self, event):
        if self.zoom <= 1.0: return
        self.scroll_x -= event.delta * 0.5
        self._clip_scroll()
        self.draw_waveform()
        
    def _clip_scroll(self):
        w = self.canvas.winfo_width()
        max_scroll = (w * self.zoom) - w
        if max_scroll < 0: max_scroll = 0
        self.scroll_x = max(0, min(self.scroll_x, max_scroll))

    def _x_to_time(self, x):
        w = self.canvas.winfo_width()
        logical_w = w * self.zoom
        lx = x + self.scroll_x
        return max(0, min(self.duration, (lx / logical_w) * self.duration))

    def on_canvas_click(self, event):
        if not self.waveform_data: return
        w = self.canvas.winfo_width()
        logical_w = w * self.zoom
        x_start = (self.trim_start / self.duration) * logical_w - self.scroll_x
        x_end = (self.trim_end / self.duration) * logical_w - self.scroll_x
        
        # Tolerance for grabbing handles
        tol = 20
        if abs(event.x - x_start) < tol:
            self.is_dragging_start = True
        elif abs(event.x - x_end) < tol:
            self.is_dragging_end = True
        else:
            # Scrub
            self.is_scrubbing = True
            self.seek(self._x_to_time(event.x))
            
    def on_canvas_drag(self, event):
        if self.is_dragging_start:
            t = self._x_to_time(event.x)
            if t < self.trim_end - 0.1: # Min 0.1s gap
                self.trim_start = t
                if self.get_current_time() < self.trim_start:
                    self.seek(self.trim_start)
                self.draw_waveform()
        elif self.is_dragging_end:
            t = self._x_to_time(event.x)
            if t > self.trim_start + 0.1:
                self.trim_end = t
                if self.get_current_time() > self.trim_end:
                    self.seek(self.trim_end)
                self.draw_waveform()
        elif self.is_scrubbing:
            self.seek(self._x_to_time(event.x))
            
    def on_canvas_release(self, event):
        self.is_dragging_start = False
        self.is_dragging_end = False
        self.is_scrubbing = False

    def set_start_to_playhead(self):
        t = self.get_current_time()
        if t < self.trim_end - 0.1:
            self.trim_start = t
            self.draw_waveform()

    def set_end_to_playhead(self):
        t = self.get_current_time()
        if t > self.trim_start + 0.1:
            self.trim_end = t
            self.draw_waveform()

    # ── Playback ─────────────────────────────────────────────────────────

    def get_current_time(self):
        if not self.playing:
            return self.play_start_time
            
        mixer_time = pygame.mixer.music.get_pos()
        if mixer_time == -1:
            return self.play_start_time
            
        # Mixer pos goes back to 0 if track ended or played through
        t = self.play_start_time + (mixer_time / 1000.0)
        
        # Stop at selection end
        if t >= self.trim_end:
            self.playing = False
            pygame.mixer.music.pause()
            self.play_start_time = self.trim_start
            return self.trim_start
            
        return t

    def seek(self, t):
        self.play_start_time = t
        if self.playing:
            try:
                pygame.mixer.music.set_pos(t)
            except pygame.error:
                # Some formats like raw mp3 don't support set_pos smoothly,
                # we restart the track
                pygame.mixer.music.play(start=t)
        self.draw_waveform()

    def toggle_playback(self):
        if not self.filepath: return
        
        if self.playing:
            pygame.mixer.music.pause()
            self.play_start_time = self.get_current_time()
            self.playing = False
        else:
            if self.get_current_time() >= self.trim_end:
                self.play_start_time = self.trim_start
            
            try:
                if pygame.mixer.music.get_pos() == -1:
                    pygame.mixer.music.play(start=self.play_start_time)
                else:
                    try:
                        pygame.mixer.music.set_pos(self.play_start_time)
                    except pygame.error:
                        pygame.mixer.music.play(start=self.play_start_time)
                    pygame.mixer.music.unpause()
            except Exception as e:
                print("Play start fallback:", e)
                pygame.mixer.music.play()
                
            self.playing = True

    def stop_audio(self):
        if self.playing:
            pygame.mixer.music.stop()
            self.playing = False

    def update_timer(self):
        t = self.get_current_time()
        m1, s1 = divmod(t, 60)
        m2, s2 = divmod(self.duration, 60)
        self.current_time_var.set(f"{int(m1):02d}:{s1:04.1f} / {int(m2):02d}:{s2:04.1f}")
        
        if self.playing:
            self.draw_waveform()
            
        self.after(50, self.update_timer)

    # ── Export ───────────────────────────────────────────────────────────

    def export_audio(self):
        if not self.filepath: return
        
        save_path = filedialog.asksaveasfilename(
            defaultextension=".mp3",
            filetypes=[("MP3 Audio", "*.mp3"), ("WAV Audio", "*.wav")],
            title="Export Edited Audio"
        )
        if not save_path: return
        
        self.btn_export.configure(text="EXPORTING...", state="disabled")
        
        def _do_export():
            try:
                cmd = [
                    self.ffmpeg_exe, "-y", 
                    "-ss", str(self.trim_start), 
                    "-to", str(self.trim_end), 
                    "-i", self.filepath, 
                    "-c:a", "libmp3lame" if save_path.endswith(".mp3") else "pcm_s16le", 
                    save_path
                ]
                subprocess.run(cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                self.after(0, lambda: messagebox.showinfo("Success", "Audio exported securely!"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", f"Failed to export: {e}"))
            finally:
                self.after(0, lambda: self.btn_export.configure(text="EXPORT CUT", state="normal"))
                
        threading.Thread(target=_do_export, daemon=True).start()
