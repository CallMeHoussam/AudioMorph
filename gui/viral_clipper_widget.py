"""
AI Viral Stream Clipper Studio Widget for AudioMorph Studio.
Unified 3-column layout:
- Left Inspector: Source, Transcript/SRT, AI Director settings, Engine configs.
- Center Stage: Interactive Video Preview (with 9:16 & watermark overlay) + Detected Clips Cards.
- Right Panel: 1-Click Viral Reel Packaging (Framing, Dynamic Subtitles, Watermark, Export).
"""

from __future__ import annotations

import copy
import os
import queue
import re
import threading
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from core.online_trimmer import StreamMetadata, fetch_stream_info, format_seconds, parse_timestamp_str
from core.video_preview import VideoInfo, extract_preview_frame, probe_video
from core.viral_clipper import (
    SubtitleBlock,
    ViralClip,
    analyze_stream_for_viral_clips,
    fetch_stream_subtitles,
    parse_srt_content,
)
from core.viral_export_worker import ViralExportWorker
from core.watermark_renderer import compute_watermark_xy, render_watermark_rgba
from gui.icons import get_icon
from gui.theme import (
    ACCENT_GLOW,
    ACCENT_HOVER,
    ACCENT_PRIMARY,
    ACCENT_SOFT_BG,
    ACCENT_TEXT,
    BG_CARD,
    BG_CARD_HOVER,
    BG_INPUT,
    BG_PANEL,
    BG_ROOT,
    BG_STAGE,
    BORDER_SUBTLE,
    CANCEL_BG,
    CANCEL_HOVER,
    FONT_FAMILY,
    FONT_MONO,
    RADIUS_BTN,
    RADIUS_CARD,
    RADIUS_PANEL,
    STATUS_ERROR,
    STATUS_SUCCESS,
    STATUS_SUCCESS_BG,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from utils.config import load_settings, save_settings
from utils.logger import get_logger

log = get_logger(__name__)


class ViralClipperWidget(ctk.CTkFrame):
    """Flagship AI Viral Stream Clipper Studio Widget."""

    def __init__(
        self,
        master,
        settings: Optional[dict] = None,
        on_queue_changed: Optional[Callable[[int], None]] = None,
        bg_color: Optional[str] = None,
        panel_color: Optional[str] = None,
        accent_color: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color=bg_color or BG_ROOT, **kwargs)
        self.settings = settings or load_settings()
        self.on_queue_changed = on_queue_changed

        # State
        self.source_path: str = ""
        self.is_url_source: bool = False
        self.stream_metadata: Optional[StreamMetadata] = None
        self.video_info: Optional[VideoInfo] = None
        self.subtitle_blocks: list[SubtitleBlock] = []
        self.detected_clips: list[ViralClip] = []
        self.active_clip: Optional[ViralClip] = None

        self.current_preview_sec: float = 0.0
        self.total_duration_sec: float = 0.0
        self.is_playing: bool = False

        self._active_worker: Optional[ViralExportWorker] = None
        self._last_output_dir: str = ""
        self._ui_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._preview_photo: Optional[ImageTk.PhotoImage] = None

        self._build_ui()
        self._poll_ui_queue()

    def _poll_ui_queue(self) -> None:
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception as ex:
                    log.debug("UI queue error: %s", ex)
        except queue.Empty:
            pass
        self.after(50, self._poll_ui_queue)

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)  # Left Inspector (~310px)
        self.grid_columnconfigure(1, weight=1)  # Center Stage + Clips List
        self.grid_columnconfigure(2, weight=0)  # Right Packaging Panel (~290px)

        self._build_left_inspector()
        self._build_center_stage()
        self._build_right_packaging_panel()

    # ══════════════════════════════════════════════════════════════════
    #  1. LEFT INSPECTOR PANEL
    # ══════════════════════════════════════════════════════════════════

    def _build_left_inspector(self) -> None:
        left_shell = ctk.CTkFrame(
            self,
            width=315,
            fg_color=BG_PANEL,
            corner_radius=RADIUS_PANEL,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        left_shell.grid(row=0, column=0, padx=(0, 14), pady=0, sticky="nsew")
        left_shell.grid_propagate(False)
        left_shell.grid_rowconfigure(0, weight=1)
        left_shell.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(
            left_shell,
            fg_color="transparent",
            scrollbar_button_color=BORDER_SUBTLE,
            scrollbar_button_hover_color=ACCENT_PRIMARY,
        )
        scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=8)

        # ── Card A: Video / Stream Source ─────────────────────────────
        card_src = self._make_card(scroll, "1. STREAM / VIDEO SOURCE")

        btn_box = ctk.CTkFrame(card_src, fg_color="transparent")
        btn_box.pack(fill="x", padx=10, pady=(6, 4))

        ctk.CTkButton(
            btn_box,
            text=" Select Video File",
            image=get_icon("video", size=14, color=TEXT_PRIMARY),
            compound="left",
            height=30,
            font=(FONT_FAMILY, 11, "bold"),
            fg_color=BG_CARD_HOVER,
            hover_color=ACCENT_PRIMARY,
            command=self._select_local_video,
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        # URL entry row
        url_row = ctk.CTkFrame(card_src, fg_color="transparent")
        url_row.pack(fill="x", padx=10, pady=(4, 6))

        self.entry_stream_url = ctk.CTkEntry(
            url_row,
            placeholder_text="Or paste stream URL…",
            height=30,
            font=(FONT_FAMILY, 11),
            fg_color=BG_INPUT,
            border_color=BORDER_SUBTLE,
        )
        self.entry_stream_url.pack(side="left", fill="x", expand=True, padx=(0, 4))

        ctk.CTkButton(
            url_row,
            text="Load",
            width=48,
            height=30,
            font=(FONT_FAMILY, 11, "bold"),
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            command=self._load_stream_url,
        ).pack(side="left")

        self.lbl_source_status = ctk.CTkLabel(
            card_src,
            text="No video or stream loaded",
            font=(FONT_FAMILY, 10),
            text_color=TEXT_MUTED,
            wraplength=270,
            anchor="w",
            justify="left",
        )
        self.lbl_source_status.pack(fill="x", padx=12, pady=(0, 8))

        # ── Card B: Transcript / Subtitles (.srt) ───────────────────────
        card_sub = self._make_card(scroll, "2. TRANSCRIPT / SUBTITLES (.SRT)")

        sub_btns = ctk.CTkFrame(card_sub, fg_color="transparent")
        sub_btns.pack(fill="x", padx=10, pady=(6, 4))

        ctk.CTkButton(
            sub_btns,
            text=" Upload .SRT",
            image=get_icon("upload", size=13, color=TEXT_PRIMARY),
            compound="left",
            height=30,
            font=(FONT_FAMILY, 11, "bold"),
            fg_color=BG_CARD_HOVER,
            hover_color=ACCENT_PRIMARY,
            command=self._upload_srt_file,
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_fetch_subs = ctk.CTkButton(
            sub_btns,
            text="Auto-Fetch",
            image=get_icon("download", size=13, color=TEXT_PRIMARY),
            compound="left",
            height=30,
            font=(FONT_FAMILY, 11, "bold"),
            fg_color=BG_CARD_HOVER,
            hover_color=ACCENT_PRIMARY,
            command=self._auto_fetch_subs,
        )
        self.btn_fetch_subs.pack(side="left", fill="x", expand=True)

        self.lbl_srt_status = ctk.CTkLabel(
            card_sub,
            text="Upload .srt/.vtt or fetch YouTube captions",
            font=(FONT_FAMILY, 10),
            text_color=TEXT_MUTED,
            wraplength=270,
            anchor="w",
            justify="left",
        )
        self.lbl_srt_status.pack(fill="x", padx=12, pady=(0, 8))

        # ── Card C: AI Viral Director Controls ─────────────────────────
        card_ai = self._make_card(scroll, "3. AI VIRAL DIRECTOR")

        ctk.CTkLabel(
            card_ai,
            text="Custom Focus Instructions (Optional):",
            font=(FONT_FAMILY, 10, "bold"),
            text_color=TEXT_SECONDARY,
        ).pack(anchor="w", padx=12, pady=(4, 2))

        self.txt_focus = ctk.CTkTextbox(
            card_ai,
            height=55,
            font=(FONT_FAMILY, 11),
            fg_color=BG_INPUT,
            border_color=BORDER_SUBTLE,
            border_width=1,
            corner_radius=8,
        )
        self.txt_focus.pack(fill="x", padx=10, pady=(0, 8))
        self.txt_focus.insert("1.0", "Highlight funny moments, heated debates, actionable tips, or high-emotion stories...")

        # Clip Count
        cnt_row = ctk.CTkFrame(card_ai, fg_color="transparent")
        cnt_row.pack(fill="x", padx=10, pady=(2, 2))
        ctk.CTkLabel(
            cnt_row, text="Target Clip Count:", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT_SECONDARY
        ).pack(side="left")
        self.lbl_clip_count = ctk.CTkLabel(
            cnt_row, text="5 Clips", font=(FONT_MONO, 10, "bold"), text_color=ACCENT_TEXT
        )
        self.lbl_clip_count.pack(side="right")

        self.slider_clip_count = ctk.CTkSlider(
            card_ai,
            from_=1,
            to=30,
            number_of_steps=29,
            height=14,
            progress_color=ACCENT_PRIMARY,
            button_color=ACCENT_HOVER,
            command=self._on_count_slider,
        )
        self.slider_clip_count.pack(fill="x", padx=10, pady=(0, 8))
        self.slider_clip_count.set(self.settings.get("viral_clip_count", 5))

        # Target Duration Segmented
        ctk.CTkLabel(
            card_ai, text="Target Clip Duration:", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT_SECONDARY
        ).pack(anchor="w", padx=12, pady=(2, 2))

        self.seg_duration = ctk.CTkSegmentedButton(
            card_ai,
            values=["Short (15–30s)", "Reel/TikTok (30–60s)", "Long (60–90s)"],
            font=(FONT_FAMILY, 10, "bold"),
            height=28,
            selected_color=ACCENT_PRIMARY,
            selected_hover_color=ACCENT_HOVER,
            unselected_color=BG_CARD_HOVER,
        )
        self.seg_duration.pack(fill="x", padx=10, pady=(0, 8))
        self.seg_duration.set(self.settings.get("viral_target_duration", "Reel/TikTok (30–60s)"))

        # Sentence completion guard
        self.var_sentence_guard = ctk.BooleanVar(value=self.settings.get("viral_sentence_guard", True))
        self.chk_sentence_guard = ctk.CTkCheckBox(
            card_ai,
            text="Sentence-Completion Guard",
            variable=self.var_sentence_guard,
            font=(FONT_FAMILY, 11),
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
        )
        self.chk_sentence_guard.pack(anchor="w", padx=12, pady=(2, 10))

        # ── Card D: AI Engine Settings ─────────────────────────────────
        card_eng = self._make_card(scroll, "4. AI ENGINE & API KEYS")

        self.opt_ai_provider = ctk.CTkOptionMenu(
            card_eng,
            values=["Google Gemini API (Recommended)", "OpenAI-Compatible / Local Ollama"],
            font=(FONT_FAMILY, 10, "bold"),
            height=30,
            fg_color=BG_INPUT,
            button_color=BG_CARD_HOVER,
            button_hover_color=ACCENT_PRIMARY,
            command=self._on_provider_change,
        )
        self.opt_ai_provider.pack(fill="x", padx=10, pady=(6, 4))
        self.opt_ai_provider.set(self.settings.get("ai_provider", "Google Gemini API (Recommended)"))

        # API Key entry
        self.entry_api_key = ctk.CTkEntry(
            card_eng,
            placeholder_text="Enter API Key (Masked)…",
            show="•",
            height=30,
            font=(FONT_FAMILY, 11),
            fg_color=BG_INPUT,
            border_color=BORDER_SUBTLE,
        )
        self.entry_api_key.pack(fill="x", padx=10, pady=(4, 4))
        if self.settings.get("ai_api_key"):
            self.entry_api_key.insert(0, self.settings.get("ai_api_key"))

        # Model Selector
        self.opt_ai_model = ctk.CTkOptionMenu(
            card_eng,
            values=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gpt-4o-mini", "llama3"],
            font=(FONT_FAMILY, 10),
            height=28,
            fg_color=BG_INPUT,
            button_color=BG_CARD_HOVER,
            button_hover_color=ACCENT_PRIMARY,
        )
        self.opt_ai_model.pack(fill="x", padx=10, pady=(4, 8))
        self.opt_ai_model.set(self.settings.get("ai_model", "gemini-2.5-flash"))

        # Primary Run Button
        self.btn_find_clips = ctk.CTkButton(
            scroll,
            text="FIND VIRAL CLIPS (AI)",
            image=get_icon("clipper", size=16, color=TEXT_PRIMARY, accent=ACCENT_TEXT),
            compound="left",
            height=44,
            corner_radius=RADIUS_BTN,
            font=(FONT_FAMILY, 12, "bold"),
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            command=self.start_ai_clip_analysis,
        )
        self.btn_find_clips.pack(fill="x", padx=4, pady=(12, 10))

        self.lbl_analysis_progress = ctk.CTkLabel(
            scroll,
            text="",
            font=(FONT_FAMILY, 10),
            text_color=TEXT_MUTED,
            wraplength=270,
        )
        self.lbl_analysis_progress.pack(fill="x", padx=6, pady=(0, 6))

    def _make_card(self, parent, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent,
            fg_color=BG_CARD,
            corner_radius=RADIUS_CARD,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        card.pack(fill="x", padx=4, pady=6)
        ctk.CTkLabel(
            card,
            text=title,
            font=(FONT_FAMILY, 10, "bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=12, pady=(10, 4))
        return card

    # ══════════════════════════════════════════════════════════════════
    #  2. CENTER STAGE & DETECTED CLIPS LIST
    # ══════════════════════════════════════════════════════════════════

    def _build_center_stage(self) -> None:
        center_shell = ctk.CTkFrame(self, fg_color="transparent")
        center_shell.grid(row=0, column=1, sticky="nsew")
        center_shell.grid_rowconfigure(0, weight=3)  # Video Preview
        center_shell.grid_rowconfigure(1, weight=4)  # Detected Clips List
        center_shell.grid_columnconfigure(0, weight=1)

        # ── Top Preview Stage ──────────────────────────────────────────
        stage_frame = ctk.CTkFrame(
            center_shell,
            fg_color=BG_STAGE,
            corner_radius=RADIUS_PANEL,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        stage_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        stage_frame.grid_rowconfigure(0, weight=1)
        stage_frame.grid_columnconfigure(0, weight=1)

        self.canvas_preview = ctk.CTkCanvas(
            stage_frame,
            bg=BG_STAGE,
            highlightthickness=0,
        )
        self.canvas_preview.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 6))
        self.canvas_preview.bind("<Configure>", lambda _e: self._redraw_preview())

        # Transport Bar
        transport = ctk.CTkFrame(stage_frame, fg_color="transparent", height=38)
        transport.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))

        self.btn_play_pause = ctk.CTkButton(
            transport,
            text="",
            image=get_icon("play", size=14, color=TEXT_PRIMARY),
            width=32,
            height=30,
            fg_color=BG_CARD,
            hover_color=ACCENT_PRIMARY,
            command=self._toggle_playback,
        )
        self.btn_play_pause.pack(side="left", padx=(0, 8))

        self.lbl_time_cur = ctk.CTkLabel(
            transport, text="00:00:00", font=(FONT_MONO, 10), text_color=TEXT_SECONDARY
        )
        self.lbl_time_cur.pack(side="left", padx=(0, 8))

        self.seek_slider = ctk.CTkSlider(
            transport,
            from_=0.0,
            to=100.0,
            height=14,
            progress_color=ACCENT_PRIMARY,
            button_color=ACCENT_HOVER,
            command=self._on_seek_slider,
        )
        self.seek_slider.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.seek_slider.set(0)

        self.lbl_time_tot = ctk.CTkLabel(
            transport, text="00:00:00", font=(FONT_MONO, 10), text_color=TEXT_MUTED
        )
        self.lbl_time_tot.pack(side="left")

        # ── Bottom: Detected Clips List ────────────────────────────────
        clips_frame = ctk.CTkFrame(
            center_shell,
            fg_color=BG_PANEL,
            corner_radius=RADIUS_PANEL,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        clips_frame.grid(row=1, column=0, sticky="nsew")
        clips_frame.grid_rowconfigure(1, weight=1)
        clips_frame.grid_columnconfigure(0, weight=1)

        # Header for clips section
        clips_hdr = ctk.CTkFrame(clips_frame, fg_color="transparent")
        clips_hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))

        self.lbl_clips_count = ctk.CTkLabel(
            clips_hdr,
            text="Detected Viral Clips (0)",
            font=(FONT_FAMILY, 12, "bold"),
            text_color=TEXT_PRIMARY,
        )
        self.lbl_clips_count.pack(side="left")

        ctk.CTkButton(
            clips_hdr,
            text="Select All",
            font=(FONT_FAMILY, 10),
            height=24,
            width=68,
            fg_color=BG_CARD,
            hover_color=BG_CARD_HOVER,
            command=self._select_all_clips,
        ).pack(side="right", padx=(4, 0))

        ctk.CTkButton(
            clips_hdr,
            text="Deselect All",
            font=(FONT_FAMILY, 10),
            height=24,
            width=76,
            fg_color=BG_CARD,
            hover_color=BG_CARD_HOVER,
            command=self._deselect_all_clips,
        ).pack(side="right")

        self.clips_scroll = ctk.CTkScrollableFrame(
            clips_frame,
            fg_color="transparent",
            scrollbar_button_color=BORDER_SUBTLE,
            scrollbar_button_hover_color=ACCENT_PRIMARY,
        )
        self.clips_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        self.lbl_empty_clips = ctk.CTkLabel(
            self.clips_scroll,
            text="Load a stream video and click 'FIND VIRAL CLIPS' to generate AI moments",
            font=(FONT_FAMILY, 12),
            text_color=TEXT_MUTED,
        )
        self.lbl_empty_clips.pack(pady=40)

    # ══════════════════════════════════════════════════════════════════
    #  3. RIGHT PACKAGING PANEL (1-Click Viral Reel Delivery)
    # ══════════════════════════════════════════════════════════════════

    def _build_right_packaging_panel(self) -> None:
        right_shell = ctk.CTkFrame(
            self,
            width=290,
            fg_color=BG_PANEL,
            corner_radius=RADIUS_PANEL,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        right_shell.grid(row=0, column=2, padx=(14, 0), pady=0, sticky="nsew")
        right_shell.grid_propagate(False)
        right_shell.grid_rowconfigure(0, weight=1)
        right_shell.grid_rowconfigure(1, weight=0)
        right_shell.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(
            right_shell,
            fg_color="transparent",
            scrollbar_button_color=BORDER_SUBTLE,
            scrollbar_button_hover_color=ACCENT_PRIMARY,
        )
        scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=8)

        ctk.CTkLabel(
            scroll,
            text="VIRAL EXPORT & PACKAGING",
            font=(FONT_FAMILY, 11, "bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=10, pady=(6, 8))

        # A. Framing & Aspect Ratio
        card_reframe = self._make_card(scroll, "ASPECT RATIO & FRAMING")

        self.opt_reframe_mode = ctk.CTkOptionMenu(
            card_reframe,
            values=[
                "Smart Speaker Center (9:16 Crop)",
                "Blurred Background Fit (9:16)",
                "Split-Screen (Top Screen / Bottom Cam)",
                "Original (16:9 Landscape)",
            ],
            font=(FONT_FAMILY, 10, "bold"),
            height=32,
            fg_color=BG_INPUT,
            button_color=BG_CARD_HOVER,
            button_hover_color=ACCENT_PRIMARY,
            command=lambda _e: self._redraw_preview(),
        )
        self.opt_reframe_mode.pack(fill="x", padx=10, pady=(6, 10))
        self.opt_reframe_mode.set(self.settings.get("viral_reframe_mode", "Smart Speaker Center (9:16 Crop)"))

        # B. Dynamic Captions
        card_caps = self._make_card(scroll, "DYNAMIC BURNED-IN SUBTITLES")

        self.var_burn_caps = ctk.BooleanVar(value=self.settings.get("viral_burn_captions", True))
        self.chk_burn_caps = ctk.CTkCheckBox(
            card_caps,
            text="Burn Dynamic Captions",
            variable=self.var_burn_caps,
            font=(FONT_FAMILY, 11, "bold"),
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
        )
        self.chk_burn_caps.pack(anchor="w", padx=12, pady=(6, 4))

        ctk.CTkLabel(
            card_caps, text="Caption Visual Style:", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY
        ).pack(anchor="w", padx=12, pady=(2, 2))

        self.opt_caption_style = ctk.CTkOptionMenu(
            card_caps,
            values=["Viral Purple Highlight", "Modern Bold White", "Yellow Pop"],
            font=(FONT_FAMILY, 10, "bold"),
            height=30,
            fg_color=BG_INPUT,
            button_color=BG_CARD_HOVER,
            button_hover_color=ACCENT_PRIMARY,
        )
        self.opt_caption_style.pack(fill="x", padx=10, pady=(0, 10))
        self.opt_caption_style.set(self.settings.get("viral_caption_style", "Viral Purple Highlight"))

        # C. Watermark Preset Overlay
        card_wm = self._make_card(scroll, "WATERMARK STUDIO PRESET")

        app_cfg = load_settings()
        wm_presets = list(app_cfg.get("watermark_presets", {}).keys())
        presets_opts = ["None"] + wm_presets

        self.opt_wm_preset = ctk.CTkOptionMenu(
            card_wm,
            values=presets_opts,
            font=(FONT_FAMILY, 10, "bold"),
            height=30,
            fg_color=BG_INPUT,
            button_color=BG_CARD_HOVER,
            button_hover_color=ACCENT_PRIMARY,
            command=lambda _e: self._redraw_preview(),
        )
        self.opt_wm_preset.pack(fill="x", padx=10, pady=(6, 10))
        default_wm = self.settings.get("viral_watermark_preset", "Evoless Signature")
        self.opt_wm_preset.set(default_wm if default_wm in presets_opts else "None")

        # D. Destination Folder
        card_dest = self._make_card(scroll, "EXPORT DESTINATION")

        self.lbl_dest_chip = ctk.CTkLabel(
            card_dest,
            text=" ~/Videos/AudioMorph_Clips",
            image=get_icon("folder", size=13, color=TEXT_SECONDARY),
            compound="left",
            font=(FONT_MONO, 10),
            text_color=TEXT_SECONDARY,
            anchor="w",
        )
        self.lbl_dest_chip.pack(fill="x", padx=10, pady=(6, 4))

        ctk.CTkButton(
            card_dest,
            text="Choose Folder",
            height=28,
            font=(FONT_FAMILY, 10, "bold"),
            fg_color=BG_CARD_HOVER,
            hover_color=ACCENT_PRIMARY,
            command=self._choose_output_dir,
        ).pack(fill="x", padx=10, pady=(0, 8))

        # ── Pinned Bottom Action Footer ─────────────────────────────────
        footer = ctk.CTkFrame(right_shell, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 12))

        self.completion_banner = ctk.CTkFrame(
            footer,
            fg_color=STATUS_SUCCESS_BG,
            corner_radius=RADIUS_CARD,
            border_width=1,
            border_color=STATUS_SUCCESS,
        )
        b_hdr = ctk.CTkFrame(self.completion_banner, fg_color="transparent")
        b_hdr.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(
            b_hdr,
            text=" Clips Export Complete",
            image=get_icon("check", size=14, color=STATUS_SUCCESS),
            compound="left",
            font=(FONT_FAMILY, 11, "bold"),
            text_color=STATUS_SUCCESS,
        ).pack(side="left")

        ctk.CTkButton(
            self.completion_banner,
            text="Open Clips Folder",
            image=get_icon("folder", size=13, color=TEXT_PRIMARY),
            compound="left",
            font=(FONT_FAMILY, 10, "bold"),
            fg_color="#163F33",
            hover_color="#1D5444",
            height=28,
            corner_radius=7,
            command=self._open_output_folder,
        ).pack(fill="x", padx=8, pady=(2, 6))

        self.lbl_export_status = ctk.CTkLabel(
            footer,
            text="Ready",
            font=(FONT_FAMILY, 10, "bold"),
            text_color=TEXT_MUTED,
            wraplength=260,
        )
        self.lbl_export_status.pack(fill="x", pady=(4, 4))

        self.export_progress = ctk.CTkProgressBar(
            footer,
            height=6,
            corner_radius=3,
            progress_color=ACCENT_PRIMARY,
            fg_color=BG_CARD,
        )
        self.export_progress.pack(fill="x", pady=(2, 8))
        self.export_progress.set(0)

        self.btn_export_all = ctk.CTkButton(
            footer,
            text="EXPORT VIRAL REELS",
            image=get_icon("export", size=16, color=TEXT_PRIMARY, accent=ACCENT_TEXT),
            compound="left",
            height=44,
            corner_radius=RADIUS_BTN,
            font=(FONT_FAMILY, 12, "bold"),
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            command=self.start_batch_export,
        )
        self.btn_export_all.pack(fill="x")

        self.btn_cancel_export = ctk.CTkButton(
            footer,
            text="CANCEL EXPORT",
            image=get_icon("close", size=14, color=TEXT_PRIMARY),
            compound="left",
            height=44,
            corner_radius=RADIUS_BTN,
            font=(FONT_FAMILY, 12, "bold"),
            fg_color=CANCEL_BG,
            hover_color=CANCEL_HOVER,
            command=self.cancel_export,
        )

    # ══════════════════════════════════════════════════════════════════
    #  Actions & Event Handlers
    # ══════════════════════════════════════════════════════════════════

    def _on_count_slider(self, val: float) -> None:
        cnt = int(round(val))
        self.lbl_clip_count.configure(text=f"{cnt} Clips")

    def _on_provider_change(self, choice: str) -> None:
        if "gemini" in choice.lower():
            self.opt_ai_model.configure(values=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash"])
            self.opt_ai_model.set("gemini-2.5-flash")
        else:
            self.opt_ai_model.configure(values=["gpt-4o-mini", "gpt-4o", "llama3", "qwen2.5"])
            self.opt_ai_model.set("gpt-4o-mini")

    def _choose_output_dir(self) -> None:
        from tkinter import filedialog
        d = filedialog.askdirectory(title="Select Clips Output Directory")
        if d:
            self.settings["viral_output_dir"] = d
            save_settings(self.settings)
            name = os.path.basename(d) or d
            self.lbl_dest_chip.configure(text=f" {name}", text_color=ACCENT_TEXT)

    def _open_output_folder(self) -> None:
        target = self._last_output_dir or self.settings.get("viral_output_dir") or str(Path.home() / "Videos" / "AudioMorph_Clips")
        if target and os.path.isdir(target):
            try:
                if os.name == "nt":
                    os.startfile(target)
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", target])
            except Exception as ex:
                log.warning("Could not open clips folder: %s", ex)

    def _select_local_video(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select Stream or Video File",
            filetypes=[("Video Files", "*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.ts"), ("All Files", "*.*")],
        )
        if path:
            self.load_local_video(path)

    def load_source(self, path_or_url: str) -> None:
        """Load a video file, stream URL, or subtitle file dynamically."""
        item = (path_or_url or "").strip().strip("{}").strip('"').strip("'")
        if not item:
            return
        if item.startswith("http://") or item.startswith("https://"):
            self.entry_stream_url.delete(0, "end")
            self.entry_stream_url.insert(0, item)
            self._load_stream_url()
        elif os.path.isfile(item):
            ext = os.path.splitext(item)[1].lower()
            if ext in (".srt", ".vtt"):
                try:
                    with open(item, "r", encoding="utf-8", errors="replace") as fh:
                        raw = fh.read()
                    self.subtitle_blocks = parse_srt_content(raw)
                    self.lbl_srt_status.configure(
                        text=f"✓ Loaded {len(self.subtitle_blocks)} subtitle cues", text_color=STATUS_SUCCESS
                    )
                except Exception as ex:
                    self.lbl_srt_status.configure(text=f"Error: {ex}", text_color=STATUS_ERROR)
            else:
                self.load_local_video(item)

    def load_local_video(self, path: str) -> None:
        self.source_path = path
        self.is_url_source = False
        info = probe_video(path)
        self.video_info = info
        self.total_duration_sec = info.duration or 60.0

        title = os.path.basename(path)
        self.lbl_source_status.configure(
            text=f"✓ Local: {title} ({format_seconds(self.total_duration_sec)} • {info.width}x{info.height})",
            text_color=TEXT_PRIMARY,
        )

        self.seek_slider.configure(from_=0.0, to=self.total_duration_sec)
        self.lbl_time_tot.configure(text=format_seconds(self.total_duration_sec))

        # Check for matching subtitle file in same directory
        srt_candidate = os.path.splitext(path)[0] + ".srt"
        if os.path.isfile(srt_candidate):
            try:
                with open(srt_candidate, "r", encoding="utf-8", errors="replace") as fh:
                    raw = fh.read()
                self.subtitle_blocks = parse_srt_content(raw)
                self.lbl_srt_status.configure(
                    text=f"✓ Auto-loaded {len(self.subtitle_blocks)} subtitle cues from .srt",
                    text_color=STATUS_SUCCESS,
                )
            except Exception as ex:
                log.debug("Auto SRT load error: %s", ex)

        self.current_preview_sec = 0.0
        self._redraw_preview()

    def _load_stream_url(self) -> None:
        url = self.entry_stream_url.get().strip()
        if not url:
            return

        self.lbl_source_status.configure(text="Fetching remote stream info…", text_color=TEXT_SECONDARY)

        def _worker():
            meta = fetch_stream_info(url)
            self._ui_queue.put(lambda: self._on_stream_info_loaded(meta))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stream_info_loaded(self, meta: StreamMetadata) -> None:
        self.stream_metadata = meta
        if not meta.valid:
            self.lbl_source_status.configure(text=f"Error: {meta.error[:45]}", text_color=STATUS_ERROR)
            return

        self.source_path = meta.url
        self.is_url_source = True
        self.total_duration_sec = meta.duration or 300.0

        dur_str = format_seconds(self.total_duration_sec)
        title = meta.title[:40] + "…" if len(meta.title) > 40 else meta.title
        self.lbl_source_status.configure(
            text=f"✓ URL: {title} ({dur_str})", text_color=TEXT_PRIMARY
        )

        self.seek_slider.configure(from_=0.0, to=self.total_duration_sec)
        self.lbl_time_tot.configure(text=dur_str)

        self.current_preview_sec = 0.0
        self._redraw_preview()

    def _upload_srt_file(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Upload Subtitles File",
            filetypes=[("Subtitle Files", "*.srt *.vtt"), ("All Files", "*.*")],
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    raw = fh.read()
                self.subtitle_blocks = parse_srt_content(raw)
                self.lbl_srt_status.configure(
                    text=f"✓ Loaded {len(self.subtitle_blocks)} subtitle cues", text_color=STATUS_SUCCESS
                )
            except Exception as ex:
                self.lbl_srt_status.configure(text=f"Error: {ex}", text_color=STATUS_ERROR)

    def _auto_fetch_subs(self) -> None:
        url = self.entry_stream_url.get().strip() or (self.stream_metadata.url if self.stream_metadata else "")
        if not url:
            self.lbl_srt_status.configure(text="Enter a stream URL first", text_color=STATUS_ERROR)
            return

        self.lbl_srt_status.configure(text="Fetching captions via yt-dlp…", text_color=TEXT_SECONDARY)

        def _worker():
            raw = fetch_stream_subtitles(url)
            self._ui_queue.put(lambda: self._on_subs_fetched(raw))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_subs_fetched(self, raw: Optional[str]) -> None:
        if not raw:
            self.lbl_srt_status.configure(text="No subtitles found on URL. Upload .srt instead.", text_color=STATUS_ERROR)
            return

        self.subtitle_blocks = parse_srt_content(raw)
        self.lbl_srt_status.configure(
            text=f"✓ Auto-fetched {len(self.subtitle_blocks)} subtitle cues", text_color=STATUS_SUCCESS
        )

    # ══════════════════════════════════════════════════════════════════
    #  AI Highlight Analysis Execution
    # ══════════════════════════════════════════════════════════════════

    def start_ai_clip_analysis(self) -> None:
        if not self.source_path:
            self.lbl_analysis_progress.configure(text="Please select a video file or enter a stream URL first.", text_color=STATUS_ERROR)
            return

        if not self.subtitle_blocks:
            self.lbl_analysis_progress.configure(text="Please upload or auto-fetch subtitles (.srt) first.", text_color=STATUS_ERROR)
            return

        # Save AI settings
        ai_cfg = {
            "ai_provider": self.opt_ai_provider.get(),
            "ai_api_key": self.entry_api_key.get().strip(),
            "ai_model": self.opt_ai_model.get().strip(),
            "ai_custom_endpoint": self.settings.get("ai_custom_endpoint", "http://localhost:11434/v1/chat/completions"),
        }
        self.settings.update(ai_cfg)
        save_settings(self.settings)

        focus_txt = self.txt_focus.get("1.0", "end").strip()
        count = int(round(self.slider_clip_count.get()))
        dur_preset = self.seg_duration.get()
        sent_guard = self.var_sentence_guard.get()

        self.btn_find_clips.configure(state="disabled", text="ANALYZING STREAM...")
        self.lbl_analysis_progress.configure(text="Initializing AI viral detection…", text_color=TEXT_SECONDARY)

        def _prog(msg: str, _pct: float):
            self._ui_queue.put(lambda m=msg: self.lbl_analysis_progress.configure(text=m, text_color=ACCENT_TEXT))

        def _worker():
            try:
                clips = analyze_stream_for_viral_clips(
                    blocks=self.subtitle_blocks,
                    settings=ai_cfg,
                    focus_instructions=focus_txt,
                    target_count=count,
                    duration_preset=dur_preset,
                    sentence_guard=sent_guard,
                    progress_callback=_prog,
                )
                self._ui_queue.put(lambda: self._on_analysis_complete(clips))
            except Exception as exc:
                log.exception("Viral clip analysis failed: %s", exc)
                self._ui_queue.put(lambda e=str(exc): self._on_analysis_error(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_analysis_complete(self, clips: list[ViralClip]) -> None:
        self.btn_find_clips.configure(state="normal", text="FIND VIRAL CLIPS (AI)")
        self.detected_clips = clips
        self.lbl_analysis_progress.configure(text=f"✓ Generated {len(clips)} viral clips!", text_color=STATUS_SUCCESS)
        self._populate_clips_cards()

    def _on_analysis_error(self, err_msg: str) -> None:
        self.btn_find_clips.configure(state="normal", text="FIND VIRAL CLIPS (AI)")
        short = err_msg if len(err_msg) <= 60 else err_msg[:57] + "…"
        self.lbl_analysis_progress.configure(text=f"Error: {short}", text_color=STATUS_ERROR)

    # ══════════════════════════════════════════════════════════════════
    #  Detected Clips Cards Presentation
    # ══════════════════════════════════════════════════════════════════

    def _populate_clips_cards(self) -> None:
        for widget in self.clips_scroll.winfo_children():
            widget.destroy()

        self.lbl_clips_count.configure(text=f"Detected Viral Clips ({len(self.detected_clips)})")

        if not self.detected_clips:
            self.lbl_empty_clips = ctk.CTkLabel(
                self.clips_scroll,
                text="No viral clips found in this transcript range.",
                font=(FONT_FAMILY, 12),
                text_color=TEXT_MUTED,
            )
            self.lbl_empty_clips.pack(pady=40)
            return

        for idx, clip in enumerate(self.detected_clips):
            self._render_clip_card(idx, clip)

    def _render_clip_card(self, idx: int, clip: ViralClip) -> None:
        card = ctk.CTkFrame(
            self.clips_scroll,
            fg_color=BG_CARD,
            corner_radius=RADIUS_CARD,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        card.pack(fill="x", padx=4, pady=5)
        card.grid_columnconfigure(1, weight=1)

        # 1. Left Checkbox + Rank Badge
        left_box = ctk.CTkFrame(card, fg_color="transparent")
        left_box.grid(row=0, column=0, padx=10, pady=10, sticky="ns")

        chk_var = ctk.BooleanVar(value=clip.included)

        def _on_toggle():
            clip.included = chk_var.get()

        ctk.CTkCheckBox(
            left_box,
            text="",
            variable=chk_var,
            width=20,
            command=_on_toggle,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
        ).pack(side="left", padx=(0, 6))

        score_color = STATUS_SUCCESS if clip.viral_score >= 85 else ACCENT_TEXT
        ctk.CTkLabel(
            left_box,
            text=f"#{clip.rank} • {clip.viral_score}/100",
            font=(FONT_MONO, 10, "bold"),
            text_color=score_color,
            fg_color=ACCENT_SOFT_BG,
            corner_radius=6,
            padx=8,
            pady=3,
        ).pack(side="left")

        # 2. Center Content: Editable Title, Timestamp Range with +/-1s, Quote
        center_box = ctk.CTkFrame(card, fg_color="transparent")
        center_box.grid(row=0, column=1, padx=6, pady=8, sticky="ew")

        # Editable Title
        title_entry = ctk.CTkEntry(
            center_box,
            height=26,
            font=(FONT_FAMILY, 11, "bold"),
            fg_color="transparent",
            border_width=0,
            text_color=TEXT_PRIMARY,
        )
        title_entry.pack(fill="x")
        title_entry.insert(0, clip.title)
        title_entry.bind("<FocusOut>", lambda _e, c=clip, te=title_entry: setattr(c, "title", te.get()))

        # Timestamps row with +/-1s fine tuning
        time_row = ctk.CTkFrame(center_box, fg_color="transparent")
        time_row.pack(fill="x", pady=(2, 2))

        lbl_range = ctk.CTkLabel(
            time_row,
            text=f"{clip.time_range_str} ({int(clip.duration_sec)}s)",
            font=(FONT_MONO, 10),
            text_color=TEXT_SECONDARY,
        )
        lbl_range.pack(side="left", padx=(0, 8))

        def _nudge_start(delta: float):
            clip.start_sec = max(0.0, clip.start_sec + delta)
            lbl_range.configure(text=f"{clip.time_range_str} ({int(clip.duration_sec)}s)")

        def _nudge_end(delta: float):
            clip.end_sec = max(clip.start_sec + 2.0, clip.end_sec + delta)
            lbl_range.configure(text=f"{clip.time_range_str} ({int(clip.duration_sec)}s)")

        # Fine tune buttons
        ctk.CTkButton(
            time_row, text="-1s Start", width=52, height=20, font=(FONT_FAMILY, 9),
            fg_color=BG_CARD_HOVER, hover_color=ACCENT_PRIMARY, command=lambda: _nudge_start(-1.0)
        ).pack(side="left", padx=1)
        ctk.CTkButton(
            time_row, text="+1s Start", width=52, height=20, font=(FONT_FAMILY, 9),
            fg_color=BG_CARD_HOVER, hover_color=ACCENT_PRIMARY, command=lambda: _nudge_start(1.0)
        ).pack(side="left", padx=1)
        ctk.CTkButton(
            time_row, text="-1s End", width=50, height=20, font=(FONT_FAMILY, 9),
            fg_color=BG_CARD_HOVER, hover_color=ACCENT_PRIMARY, command=lambda: _nudge_end(-1.0)
        ).pack(side="left", padx=(6, 1))
        ctk.CTkButton(
            time_row, text="+1s End", width=50, height=20, font=(FONT_FAMILY, 9),
            fg_color=BG_CARD_HOVER, hover_color=ACCENT_PRIMARY, command=lambda: _nudge_end(1.0)
        ).pack(side="left", padx=1)

        # Quote excerpt
        if clip.hook_quote:
            ctk.CTkLabel(
                center_box,
                text=f'"{clip.hook_quote[:80]}..."',
                font=(FONT_FAMILY, 10, "italic"),
                text_color=TEXT_MUTED,
                anchor="w",
            ).pack(fill="x")

        # 3. Right Action Buttons: Preview & Export Single
        act_box = ctk.CTkFrame(card, fg_color="transparent")
        act_box.grid(row=0, column=2, padx=10, pady=10, sticky="e")

        ctk.CTkButton(
            act_box,
            text="Preview",
            image=get_icon("play", size=12, color=TEXT_PRIMARY),
            compound="left",
            width=76,
            height=28,
            font=(FONT_FAMILY, 10, "bold"),
            fg_color=BG_CARD_HOVER,
            hover_color=ACCENT_PRIMARY,
            command=lambda c=clip: self._preview_clip(c),
        ).pack(side="top", pady=(0, 4))

        ctk.CTkButton(
            act_box,
            text="Export",
            image=get_icon("export", size=12, color=TEXT_PRIMARY),
            compound="left",
            width=76,
            height=28,
            font=(FONT_FAMILY, 10, "bold"),
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            command=lambda c=clip: self._export_single_clip(c),
        ).pack(side="top")

    def _select_all_clips(self) -> None:
        for c in self.detected_clips:
            c.included = True
        self._populate_clips_cards()

    def _deselect_all_clips(self) -> None:
        for c in self.detected_clips:
            c.included = False
        self._populate_clips_cards()

    # ══════════════════════════════════════════════════════════════════
    #  Video Preview & Overlay Stage
    # ══════════════════════════════════════════════════════════════════

    def _preview_clip(self, clip: ViralClip) -> None:
        self.active_clip = clip
        self.current_preview_sec = clip.start_sec
        self.seek_slider.set(self.current_preview_sec)
        self.lbl_time_cur.configure(text=format_seconds(self.current_preview_sec))
        self._redraw_preview()

    def stop_playback(self) -> None:
        self.is_playing = False
        if hasattr(self, "btn_play_pause"):
            self.btn_play_pause.configure(image=get_icon("play", size=14, color=TEXT_PRIMARY))

    def _toggle_playback(self) -> None:
        self.is_playing = not self.is_playing
        icon_name = "pause" if self.is_playing else "play"
        self.btn_play_pause.configure(image=get_icon(icon_name, size=14, color=TEXT_PRIMARY))
        if self.is_playing:
            self._playback_loop()

    def _playback_loop(self) -> None:
        if not self.is_playing:
            return

        step = 0.5
        self.current_preview_sec += step
        if self.active_clip and self.current_preview_sec > self.active_clip.end_sec:
            self.current_preview_sec = self.active_clip.start_sec

        self.seek_slider.set(self.current_preview_sec)
        self.lbl_time_cur.configure(text=format_seconds(self.current_preview_sec))
        self._redraw_preview()

        self.after(500, self._playback_loop)

    def _on_seek_slider(self, val: float) -> None:
        self.current_preview_sec = float(val)
        self.lbl_time_cur.configure(text=format_seconds(self.current_preview_sec))
        self._redraw_preview()

    def _redraw_preview(self) -> None:
        cw = self.canvas_preview.winfo_width()
        ch = self.canvas_preview.winfo_height()
        if cw < 50 or ch < 50:
            return

        # Fetch frame
        frame = None
        if self.is_url_source and self.stream_metadata and self.stream_metadata.stream_url:
            from core.online_trimmer import extract_remote_frame
            frame = extract_remote_frame(self.stream_metadata.stream_url, self.current_preview_sec, cw, ch)
        elif not self.is_url_source and self.source_path and os.path.isfile(self.source_path):
            frame = extract_preview_frame(self.source_path, self.current_preview_sec, cw, ch)

        if frame is None:
            # Placeholder dark canvas
            frame = Image.new("RGB", (cw, ch), (15, 15, 23))
            d = ImageDraw.Draw(frame)
            d.text((cw // 2 - 60, ch // 2 - 10), "Video Preview", fill=(100, 116, 139))

        # Check reframe mode for live 9:16 guidelines overlay
        reframe = self.opt_reframe_mode.get()
        if "9:16" in reframe:
            # Draw vertical 9:16 guidelines on the preview
            d = ImageDraw.Draw(frame)
            crop_w = int(round(ch * (9.0 / 16.0)))
            x0 = (cw - crop_w) // 2
            x1 = x0 + crop_w
            # Dim outside regions
            d.rectangle([0, 0, x0, ch], fill=(0, 0, 0, 140))
            d.rectangle([x1, 0, cw, ch], fill=(0, 0, 0, 140))
            # Border guideline
            d.rectangle([x0, 1, x1, ch - 1], outline=(109, 40, 217), width=2)

        # Check watermark preview
        wm_name = self.opt_wm_preset.get()
        if wm_name != "None":
            app_cfg = load_settings()
            presets = app_cfg.get("watermark_presets", {})
            if wm_name in presets:
                wm_cfg = presets[wm_name]
                wm_img = render_watermark_rgba(wm_cfg, cw, ch)
                if wm_img and wm_img.width > 0 and wm_img.height > 0:
                    wx, wy = compute_watermark_xy(cw, ch, wm_img.width, wm_img.height, wm_cfg)
                    frame.paste(wm_img, (wx, wy), wm_img)

        self._preview_photo = ImageTk.PhotoImage(frame)
        self.canvas_preview.delete("all")
        self.canvas_preview.create_image(cw // 2, ch // 2, image=self._preview_photo)

    # ══════════════════════════════════════════════════════════════════
    #  Batch & Single Export Pipeline Execution
    # ══════════════════════════════════════════════════════════════════

    def start_batch_export(self) -> None:
        selected = [c for c in self.detected_clips if c.included]
        if not selected:
            self.lbl_export_status.configure(text="No clips selected for export", text_color=STATUS_ERROR)
            return

        self._execute_export(selected)

    def _export_single_clip(self, clip: ViralClip) -> None:
        self._execute_export([clip])

    def _execute_export(self, clips_to_export: list[ViralClip]) -> None:
        if self._active_worker is not None and self._active_worker.is_alive():
            return

        self.completion_banner.pack_forget()

        # Build packaging settings
        pkg_settings = {
            "reframe_mode": self.opt_reframe_mode.get(),
            "burn_captions": self.var_burn_caps.get(),
            "caption_style": self.opt_caption_style.get(),
            "watermark_preset": self.opt_wm_preset.get(),
            "output_dir": self.settings.get("viral_output_dir") or str(Path.home() / "Videos" / "AudioMorph_Clips"),
        }

        # Swap action button to Cancel
        self.btn_export_all.pack_forget()
        self.btn_cancel_export.pack(fill="x")
        self.export_progress.set(0)
        self.lbl_export_status.configure(text=f"Starting export of {len(clips_to_export)} clips…", text_color=TEXT_PRIMARY)

        def _on_start(idx: int, clip: ViralClip):
            self._ui_queue.put(
                lambda i=idx, c=clip: self.lbl_export_status.configure(
                    text=f"Rendering clip {i+1}/{len(clips_to_export)}: {c.title[:25]}…",
                    text_color=TEXT_PRIMARY,
                )
            )

        def _on_prog(idx: int, pct: int):
            self._ui_queue.put(
                lambda i=idx, p=pct: self.lbl_export_status.configure(
                    text=f"Rendering clip {i+1}/{len(clips_to_export)} ({p}%)",
                    text_color=TEXT_PRIMARY,
                )
            )

        def _on_done(idx: int, path: str):
            log.info("Finished clip %d -> %s", idx, path)

        def _on_err(idx: int, err: str):
            log.warning("Clip %d failed: %s", idx, err)

        def _on_tot_prog(p: int):
            self._ui_queue.put(lambda val=p: self.export_progress.set(val / 100.0))

        def _on_complete(summary: dict):
            self._ui_queue.put(lambda s=summary: self._handle_export_complete(s))

        callbacks = {
            "on_clip_start": _on_start,
            "on_clip_progress": _on_prog,
            "on_clip_done": _on_done,
            "on_clip_error": _on_err,
            "on_total_progress": _on_tot_prog,
            "on_complete": _on_complete,
        }

        self._active_worker = ViralExportWorker(
            source_media=self.source_path,
            clips=clips_to_export,
            subtitle_blocks=self.subtitle_blocks,
            packaging_settings=pkg_settings,
            ui_callbacks=callbacks,
            is_url_source=self.is_url_source,
        )
        self._active_worker.start()

    def cancel_export(self) -> None:
        if self._active_worker is not None:
            self._active_worker.cancel()
            self.lbl_export_status.configure(text="Cancelling export…", text_color=STATUS_ERROR)

    def _handle_export_complete(self, summary: dict) -> None:
        self.btn_cancel_export.pack_forget()
        self.btn_export_all.pack(fill="x")

        succeeded = summary.get("succeeded", 0)
        failed = summary.get("failed", 0)
        cancelled = summary.get("cancelled", False)
        dirs = summary.get("output_dirs", [])
        if dirs:
            self._last_output_dir = dirs[0]

        if cancelled:
            self.lbl_export_status.configure(text="Export cancelled", text_color=STATUS_ERROR)
            return

        if failed == 0:
            self.lbl_export_status.configure(
                text=f"✓ Exported {succeeded} viral reel(s) successfully!", text_color=STATUS_SUCCESS
            )
            self.completion_banner.pack(fill="x", pady=(0, 6), before=self.lbl_export_status)
        else:
            self.lbl_export_status.configure(
                text=f"Done: {succeeded} succeeded, {failed} failed", text_color=STATUS_ERROR
            )
            if succeeded > 0:
                self.completion_banner.pack(fill="x", pady=(0, 6), before=self.lbl_export_status)
