import os
import subprocess
import threading
import tempfile
import customtkinter as ctk
from tkinter import filedialog, messagebox

try:
    from PIL import Image, ImageTk, ImageDraw
except ImportError:
    Image, ImageTk, ImageDraw = None, None, None

class BgRemoverWidget(ctk.CTkFrame):
    def __init__(self, master, bg_color="#0D0D10", panel_color="#15151A", accent_color="#4B197A", **kwargs):
        super().__init__(master, fg_color=bg_color, **kwargs)
        self.bg_color = bg_color
        self.panel_color = panel_color
        self.accent_color = accent_color
        
        self.filepath = None
        self.output_path = None
        self.temp_dir = tempfile.mkdtemp(prefix="audiomorph_bg_")
        
        # Slider state
        self.slider_pos = 0.5  # 0.0 to 1.0
        self.img_before_pil = None
        self.img_after_pil = None
        self.canvas_w = 800
        self.canvas_h = 500
        self.photo_cache = None
        
        self._build_ui()

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # ── Top Toolbar ──────────────────────────────────────────────
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        
        self.btn_load = ctk.CTkButton(top_bar, text="UPLOAD IMAGE", command=self.load_file, fg_color=self.panel_color, hover_color=self.accent_color)
        self.btn_load.pack(side="left")
        
        self.lbl_file = ctk.CTkLabel(top_bar, text="No file selected (Drag & drop file here)", text_color="#888890")
        self.lbl_file.pack(side="left", padx=15)
        
        self.btn_generate = ctk.CTkButton(top_bar, text="REMOVE BACKGROUND (AI)", command=self.generate_mask, fg_color=self.accent_color, state="disabled")
        self.btn_generate.pack(side="right")
        
        self.lbl_status = ctk.CTkLabel(top_bar, text="", text_color="#FFFFFF")
        self.lbl_status.pack(side="right", padx=15)
        
        # ── Slider Preview Area ──────────────────────────────────────
        self.canvas_frame = ctk.CTkFrame(self, fg_color=self.panel_color)
        self.canvas_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        self.canvas_frame.grid_rowconfigure(0, weight=1)
        self.canvas_frame.grid_columnconfigure(0, weight=1)
        
        import tkinter as tk
        self.canvas = tk.Canvas(self.canvas_frame, bg="#0D0D10", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<Button-1>", self._on_drag)
        
        # ── Bottom Toolbar ───────────────────────────────────────────
        bottom_bar = ctk.CTkFrame(self, fg_color="transparent")
        bottom_bar.grid(row=2, column=0, sticky="ew", padx=20, pady=20)
        
        self.btn_export = ctk.CTkButton(bottom_bar, text="DOWNLOAD HIGH-RES PNG", command=self.export_png, width=200, state="disabled", fg_color="#FF3366")
        self.btn_export.pack(side="right")

    def load_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
        if not filepath: return
        self.load_file_from_path(filepath)

    def load_file_from_path(self, filepath):
        if not filepath or not os.path.exists(filepath): return
        try:
            if not Image:
                raise Exception("Pillow not installed.")
            with Image.open(filepath) as img:
                img.verify()
            self.img_before_pil = Image.open(filepath).convert("RGBA")
        except Exception:
            messagebox.showerror("Invalid Image", f"The selected file is not a valid image format:\n{os.path.basename(filepath)}")
            return

        self.filepath = filepath
        self.output_path = None
        self.img_after_pil = None
        self.slider_pos = 0.5
        
        self.lbl_file.configure(text=os.path.basename(filepath))
        self.btn_generate.configure(state="normal")
        self.btn_export.configure(state="disabled")
        self._render_slider()

    # ── AI Generation ────────────────────────────────────────────────

    def generate_mask(self):
        if not self.filepath: return
        self.btn_generate.configure(state="disabled", text="PROCESSING...")
        self.lbl_status.configure(text="Running Rembg...")
        
        out_filename = "bg_removed.png"
        self.output_path = os.path.join(self.temp_dir, out_filename)
            
        threading.Thread(target=self._run_rembg_backend, daemon=True).start()

    def _run_rembg_backend(self):
        try:
            from rembg import remove
            from PIL import Image
            
            input_img = Image.open(self.filepath)
            output_img = remove(input_img)
            output_img.save(self.output_path)

            if not os.path.exists(self.output_path):
                raise Exception("Generation completed but PNG not found.")
                
            self.img_after_pil = output_img.convert("RGBA")
            self.after(0, self._on_generation_success)
            
        except ImportError:
            self.after(0, self._on_generation_error, "rembg not found. Please run 'pip install rembg'")
        except Exception as e:
            self.after(0, self._on_generation_error, str(e))

    def _on_generation_success(self):
        self.btn_generate.configure(state="normal", text="RE-GENERATE")
        self.lbl_status.configure(text="Finished!")
        self.btn_export.configure(state="normal")
        self._render_slider()

    def _on_generation_error(self, err_msg):
        self.btn_generate.configure(state="normal", text="REMOVE BACKGROUND (AI)")
        self.lbl_status.configure(text="Error!")
        messagebox.showerror("AI Error", f"Offline BG Removal failed:\n{err_msg}")

    # ── Slider Canvas Logic ──────────────────────────────────────────

    def _on_resize(self, event):
        self.canvas_w = event.width
        self.canvas_h = event.height
        self._render_slider()
        
    def _on_drag(self, event):
        if not self.img_before_pil: return
        w = self.canvas.winfo_width()
        pos = event.x / w
        self.slider_pos = max(0.01, min(0.99, pos))
        self._render_slider()

    def _render_slider(self):
        if not self.img_before_pil or self.canvas_w <= 1 or self.canvas_h <= 1:
            return
            
        w, h = self.canvas_w, self.canvas_h
        
        # Calculate aspect ratio scaling
        img_w, img_h = self.img_before_pil.size
        scale = min(w / img_w, h / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        
        if new_w <= 0 or new_h <= 0: return
        
        # Create an offset so the image is centered
        x_off = (w - new_w) // 2
        y_off = (h - new_h) // 2
        
        before_resized = self.img_before_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
        checkers = self._create_checkboard(w, h)

        if not self.img_after_pil:
            final = checkers.copy()
            final.paste(before_resized, (x_off, y_off), before_resized if before_resized.mode == "RGBA" else None)
        else:
            after_resized = self.img_after_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            canvas_before = checkers.copy()
            canvas_before.paste(before_resized, (x_off, y_off), before_resized if before_resized.mode == "RGBA" else None)
            
            canvas_after = checkers.copy()
            canvas_after.paste(after_resized, (x_off, y_off), after_resized if after_resized.mode == "RGBA" else None)
            
            split_x = int(w * self.slider_pos)
            
            if split_x <= 0:
                final = canvas_after
            elif split_x >= w:
                final = canvas_before
            else:
                left_part = canvas_before.crop((0, 0, split_x, h))
                right_part = canvas_after.crop((split_x, 0, w, h))
                final = Image.new("RGBA", (w, h))
                final.paste(left_part, (0, 0))
                final.paste(right_part, (split_x, 0))
        
        # Draw slider line
        draw = ImageDraw.Draw(final)
        split_x = int(w * self.slider_pos)
        draw.line([(split_x, 0), (split_x, h)], fill="white", width=3)
        draw.polygon([(split_x - 10, h//2 - 10), (split_x - 10, h//2 + 10), (split_x - 15, h//2)], fill="white")
        draw.polygon([(split_x + 10, h//2 - 10), (split_x + 10, h//2 + 10), (split_x + 15, h//2)], fill="white")
        
        self.photo_cache = ImageTk.PhotoImage(final)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo_cache)
        
    def _create_checkboard(self, w, h, size=20):
        img = Image.new('RGBA', (w, h), color=(30, 30, 30, 255))
        draw = ImageDraw.Draw(img)
        for y in range(0, h, size):
            for x in range(0, w, size):
                if (x // size + y // size) % 2 == 0:
                    draw.rectangle([x, y, x + size, y + size], fill=(45, 45, 45, 255))
        return img
        
    # ── Exporting ────────────────────────────────────────────────────

    def export_png(self):
        if not self.output_path or not os.path.exists(self.output_path):
            return
            
        save_path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG Image", "*.png")])
        if not save_path: return
        
        try:
            import shutil
            shutil.copy2(self.output_path, save_path)
            messagebox.showinfo("Success", "Transparent PNG successfully exported!")
        except Exception as e:
            messagebox.showerror("Error", str(e))
