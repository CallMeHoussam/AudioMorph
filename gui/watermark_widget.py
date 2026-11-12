"""
Interactive Custom Video Watermark Studio widget for AudioMorph.

Features a 3-tab luxury inspector (``Content & Font``, ``Style & Effects`` with
progressive disclosure, ``Position & Layout``), a dark cinema preview stage with
floating resolution pill and unified transport bar, an interactive dashed-border
dropzone when empty, and modern dark video queue cards (replacing Treeview).
"""

from __future__ import annotations

import copy
import os
import queue
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Callable, Optional

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from core.video_preview import (
    VideoInfo,
    VideoPlaybackStream,
    extract_preview_frame,
    format_duration,
    probe_video,
)
from core.watermark_renderer import (
    ANCHOR_KEYS,
    appearance_cache_key,
    compute_watermark_xy,
    get_available_font_families,
    parse_hex_color,
    render_watermark_rgba,
    xy_to_normalized_center,
)
from gui.icons import get_icon
from gui.queue_cards import EmptyDropzoneHero, ModernQueueList
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
    CANCEL_HOVER,
    FONT_FAMILY,
    FONT_MONO,
    RADIUS_BTN,
    RADIUS_CARD,
    RADIUS_PANEL,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from utils.config import DEFAULT_EVOLESS_PRESET, save_settings
from utils.logger import get_logger

log = get_logger(__name__)

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".flv", ".wmv", ".ts", ".mts",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class _FontPickerDialog(ctk.CTkToplevel):
    """Searchable modal dialog listing all installed system fonts."""

    def __init__(
        self,
        master,
        families: list[str],
        current_family: str,
        on_select: Callable[[str], None],
    ) -> None:
        super().__init__(master)
        self.title("Choose System Font")
        self.geometry("380x460")
        self.configure(fg_color=BG_ROOT)
        self.transient(master)
        self.grab_set()

        self._all_families = families
        self._on_select = on_select

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._populate())
        search_entry = ctk.CTkEntry(
            self,
            textvariable=self._search_var,
            placeholder_text="Search system fonts…",
            fg_color=BG_CARD,
            border_color=BORDER_SUBTLE,
            corner_radius=RADIUS_BTN,
            height=36,
        )
        search_entry.grid(row=0, column=0, padx=16, pady=(16, 10), sticky="ew")

        list_frame = ctk.CTkFrame(
            self, fg_color=BG_PANEL, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER_SUBTLE
        )
        list_frame.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        self._listbox = tk.Listbox(
            list_frame,
            bg=BG_PANEL,
            fg=TEXT_PRIMARY,
            selectbackground=ACCENT_PRIMARY,
            selectforeground="#FFFFFF",
            borderwidth=0,
            highlightthickness=0,
            font=(FONT_FAMILY, 10),
        )
        self._listbox.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self._listbox.bind("<Double-Button-1>", lambda _e: self._confirm())

        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self._listbox.yview)
        sb.grid(row=0, column=1, sticky="ns", pady=6, padx=(0, 4))
        self._listbox.configure(yscrollcommand=sb.set)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="ew")
        ctk.CTkButton(
            btn_row, text="Cancel", fg_color=BG_CARD, hover_color=BG_CARD_HOVER,
            corner_radius=RADIUS_BTN, width=90, command=self.destroy,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            btn_row, text="Select Font", fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER,
            corner_radius=RADIUS_BTN, width=115, command=self._confirm,
        ).pack(side="right")

        self._populate(select_target=current_family)
        search_entry.focus_set()

    def _populate(self, select_target: str | None = None) -> None:
        q = self._search_var.get().strip().lower()
        self._listbox.delete(0, tk.END)
        filtered = [f for f in self._all_families if q in f.lower()] if q else self._all_families
        for fam in filtered:
            self._listbox.insert(tk.END, fam)
        if select_target and select_target in filtered:
            idx = filtered.index(select_target)
            self._listbox.selection_set(idx)
            self._listbox.see(idx)

    def _confirm(self) -> None:
        sel = self._listbox.curselection()
        if sel:
            self._on_select(self._listbox.get(sel[0]))
        self.destroy()


class WatermarkEditorWidget(ctk.CTkFrame):
    """Luxury Watermark Studio: 3-tab inspector + cinema preview stage + card queue."""

    def __init__(
        self,
        master,
        settings: dict,
        on_queue_changed: Optional[Callable[[int], None]] = None,
        bg_color: str = BG_ROOT,
        panel_color: str = BG_PANEL,
        accent_color: str = ACCENT_PRIMARY,
        text_main: str = TEXT_PRIMARY,
        text_muted: str = TEXT_SECONDARY,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color=bg_color, **kwargs)
        self.settings = settings
        self.on_queue_changed = on_queue_changed
        self.bg_color = bg_color
        self.panel_color = panel_color
        self.accent_color = accent_color
        self.text_main = text_main
        self.text_muted = text_muted

        # Preset & watermark config state
        self.presets: dict[str, dict] = self.settings.setdefault(
            "watermark_presets",
            {"Evoless Signature": copy.deepcopy(DEFAULT_EVOLESS_PRESET)},
        )
        active_name = self.settings.get("watermark_active_preset", "Evoless Signature")
        if active_name not in self.presets:
            active_name = next(iter(self.presets))
        self.active_preset_name: str = active_name
        self.wm_config: dict = copy.deepcopy(self.presets[active_name])

        # Queue & active video state
        self.video_queue: list[str] = []
        self.video_infos: dict[str, VideoInfo] = {}
        self.active_video_path: Optional[str] = None
        self.active_video_info: Optional[VideoInfo] = None

        # Preview frame & playback state
        self.current_time: float = 0.0
        self.is_playing: bool = False
        self._playback_stream: Optional[VideoPlaybackStream] = None
        self._raw_frame_pil: Optional[Image.Image] = None
        self._preview_photo: Optional[ImageTk.PhotoImage] = None
        self._display_rect: tuple[int, int, int, int] = (0, 0, 640, 360)

        # Watermark render cache
        self._wm_cache_key: Optional[tuple] = None
        self._wm_cached_full: Optional[Image.Image] = None
        self._wm_cached_preview_key: Optional[tuple] = None
        self._wm_cached_preview: Optional[Image.Image] = None

        # Drag & debounce state
        self._is_dragging_wm: bool = False
        self._drag_offset_x: float = 0.0
        self._drag_offset_y: float = 0.0
        self._last_wm_preview_box: Optional[tuple[int, int, int, int]] = None
        self._render_after_id: Optional[str] = None
        self._scrub_after_id: Optional[str] = None
        self._resize_after_id: Optional[str] = None
        self._suppress_updates: bool = False
        self._is_scrubbing_slider: bool = False
        self._export_locked: bool = False

        self._curated_fonts = get_available_font_families(curated_only=True)
        self._anchor_buttons: dict[str, ctk.CTkButton] = {}
        self._active_inspector_tab: str = "Content"

        # Icons for transport
        self._icon_play = get_icon("play", size=14, color=TEXT_PRIMARY)
        self._icon_pause = get_icon("pause", size=14, color=TEXT_PRIMARY)

        self._build_ui()
        self._apply_config_to_ui(self.wm_config)
        self._refresh_queue_visibility()
        self._schedule_composite_render(immediate=True)
        self._ui_dispatch_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._drain_ui_queue()

    # ══════════════════════════════════════════════════════════════════
    #  UI Construction
    # ══════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        # ── 1. LEFT INSPECTOR PANEL (3 Sub-Tabs) ─────────────────────
        inspector_shell = ctk.CTkFrame(
            self,
            width=300,
            fg_color=BG_PANEL,
            corner_radius=RADIUS_PANEL,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        inspector_shell.grid(row=0, column=0, padx=(0, 14), pady=0, sticky="nsew")
        inspector_shell.grid_propagate(False)
        inspector_shell.grid_rowconfigure(1, weight=1)
        inspector_shell.grid_columnconfigure(0, weight=1)

        tab_wrap = ctk.CTkFrame(inspector_shell, fg_color="transparent")
        tab_wrap.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))

        self.inspector_tabs = ctk.CTkSegmentedButton(
            tab_wrap,
            values=["Content", "Effects", "Layout"],
            selected_color=ACCENT_PRIMARY,
            selected_hover_color=ACCENT_HOVER,
            unselected_color=BG_CARD,
            unselected_hover_color=BG_CARD_HOVER,
            fg_color=BG_INPUT,
            font=(FONT_FAMILY, 11, "bold"),
            height=32,
            command=self._on_inspector_tab_change,
        )
        self.inspector_tabs.set("Content")
        self.inspector_tabs.pack(fill="x")

        self.inspector_scroll = ctk.CTkScrollableFrame(
            inspector_shell,
            fg_color="transparent",
            scrollbar_button_color=BORDER_SUBTLE,
            scrollbar_button_hover_color=ACCENT_PRIMARY,
        )
        self.inspector_scroll.grid(row=1, column=0, sticky="nsew", padx=6, pady=(2, 10))

        self.tab_content = ctk.CTkFrame(self.inspector_scroll, fg_color="transparent")
        self.tab_effects = ctk.CTkFrame(self.inspector_scroll, fg_color="transparent")
        self.tab_layout = ctk.CTkFrame(self.inspector_scroll, fg_color="transparent")

        self._build_content_tab()
        self._build_effects_tab()
        self._build_layout_tab()
        self.tab_content.pack(fill="x", expand=True)

        # ── 2. CENTER VIDEO STAGE + QUEUE ────────────────────────────
        center = ctk.CTkFrame(self, fg_color="transparent")
        center.grid(row=0, column=1, sticky="nsew")
        center.grid_rowconfigure(0, weight=4)
        center.grid_rowconfigure(1, weight=0)
        center.grid_rowconfigure(2, weight=0)
        center.grid_columnconfigure(0, weight=1)

        # Cinema preview stage
        stage_card = ctk.CTkFrame(
            center,
            fg_color=BG_STAGE,
            corner_radius=RADIUS_PANEL,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        stage_card.grid(row=0, column=0, sticky="nsew")
        stage_card.grid_rowconfigure(0, weight=1)
        stage_card.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            stage_card, bg=BG_STAGE, highlightthickness=0, cursor="arrow"
        )
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Motion>", self._on_canvas_hover)

        # Floating resolution pill in top-right of stage
        self.lbl_res_badge = ctk.CTkLabel(
            stage_card,
            text="16:9 • Blank Preview",
            font=(FONT_MONO, 10, "bold"),
            text_color=ACCENT_TEXT,
            fg_color=BG_PANEL,
            corner_radius=8,
            padx=10,
            pady=4,
        )
        self.lbl_res_badge.place(relx=0.985, rely=0.03, anchor="ne")

        # Unified Transport Bar
        playback_bar = ctk.CTkFrame(
            center,
            fg_color=BG_PANEL,
            corner_radius=RADIUS_CARD,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        playback_bar.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        playback_bar.grid_columnconfigure(1, weight=1)

        self.btn_play = ctk.CTkButton(
            playback_bar,
            text="",
            image=self._icon_play,
            width=34,
            height=34,
            corner_radius=17,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            state="disabled",
            command=self.toggle_playback,
        )
        self.btn_play.grid(row=0, column=0, padx=(10, 8), pady=7)

        self.timeline_var = ctk.DoubleVar(value=0.0)
        self.timeline_slider = ctk.CTkSlider(
            playback_bar,
            from_=0.0,
            to=1.0,
            variable=self.timeline_var,
            progress_color=ACCENT_PRIMARY,
            button_color=TEXT_PRIMARY,
            button_hover_color=ACCENT_HOVER,
            fg_color=BG_CARD,
            state="disabled",
            command=self._on_timeline_scrub,
        )
        self.timeline_slider.grid(row=0, column=1, padx=6, pady=7, sticky="ew")
        self.timeline_slider.bind("<ButtonRelease-1>", self._on_timeline_release)

        self.lbl_timecode = ctk.CTkLabel(
            playback_bar,
            text="00:00 / 00:00",
            font=(FONT_MONO, 11, "bold"),
            text_color=TEXT_PRIMARY,
            width=112,
        )
        self.lbl_timecode.grid(row=0, column=2, padx=(8, 12), pady=7)

        # Bottom Queue Area (Dropzone Hero when empty <-> Modern Card List when populated)
        self._queue_area = ctk.CTkFrame(center, fg_color="transparent", height=162)
        self._queue_area.grid(row=2, column=0, sticky="ew")
        self._queue_area.grid_propagate(False)
        self._queue_area.grid_rowconfigure(0, weight=1)
        self._queue_area.grid_columnconfigure(0, weight=1)

        self.empty_hero = EmptyDropzoneHero(
            self._queue_area,
            title="Drop your videos here",
            subtitle="or click to browse • MP4, MOV, MKV, AVI, WebM (drop a PNG/JPG to set logo)",
            button_text="Add Videos",
            on_browse=self.add_videos,
            icon_name="video",
            compact=True,
            canvas_bg=BG_ROOT,
        )

        self.queue_list = ModernQueueList(
            self._queue_area,
            on_remove_index=self._remove_at_index,
            on_select_index=self._on_card_selected,
            compact=True,
        )

    def _make_card(self, parent, pady=(0, 10)) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent,
            fg_color=BG_CARD,
            corner_radius=RADIUS_CARD,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        card.pack(fill="x", padx=6, pady=pady)
        return card

    def _card_label(self, parent, title: str) -> ctk.CTkLabel:
        lbl = ctk.CTkLabel(
            parent,
            text=title,
            font=(FONT_FAMILY, 10, "bold"),
            text_color=TEXT_MUTED,
        )
        lbl.pack(anchor="w", padx=12, pady=(10, 4))
        return lbl

    def _build_content_tab(self) -> None:
        # Presets card
        p_card = self._make_card(self.tab_content, pady=(4, 10))
        hdr = ctk.CTkFrame(p_card, fg_color="transparent")
        hdr.pack(fill="x", padx=12, pady=(10, 6))
        ctk.CTkLabel(
            hdr,
            text=" PRESET SIGNATURE",
            image=get_icon("preset", size=14, color=ACCENT_TEXT),
            compound="left",
            font=(FONT_FAMILY, 10, "bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left")

        self.preset_menu = ctk.CTkOptionMenu(
            p_card,
            values=list(self.presets.keys()),
            fg_color=BG_INPUT,
            button_color=BG_CARD_HOVER,
            button_hover_color=ACCENT_PRIMARY,
            corner_radius=RADIUS_BTN,
            command=self._on_preset_selected,
        )
        self.preset_menu.pack(fill="x", padx=12, pady=(0, 8))

        p_btns = ctk.CTkFrame(p_card, fg_color="transparent")
        p_btns.pack(fill="x", padx=12, pady=(0, 10))
        p_btns.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(
            p_btns, text="+ Save", height=28, corner_radius=8,
            font=(FONT_FAMILY, 11, "bold"), fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER,
            command=self._save_new_preset,
        ).grid(row=0, column=0, padx=(0, 4), sticky="ew")
        ctk.CTkButton(
            p_btns, text="Update", height=28, corner_radius=8,
            font=(FONT_FAMILY, 11), fg_color=BG_CARD_HOVER, hover_color=ACCENT_PRIMARY,
            command=self._update_active_preset,
        ).grid(row=0, column=1, padx=4, sticky="ew")
        ctk.CTkButton(
            p_btns, text="Delete", height=28, corner_radius=8,
            font=(FONT_FAMILY, 11), fg_color=BG_CARD_HOVER, hover_color=CANCEL_HOVER,
            command=self._delete_active_preset,
        ).grid(row=0, column=2, padx=(4, 0), sticky="ew")

        # Type Switcher
        type_card = self._make_card(self.tab_content, pady=(0, 10))
        self._card_label(type_card, "WATERMARK MODE")
        self.type_switcher = ctk.CTkSegmentedButton(
            type_card,
            values=["Text", "Image / Logo"],
            selected_color=ACCENT_PRIMARY,
            selected_hover_color=ACCENT_HOVER,
            unselected_color=BG_INPUT,
            fg_color=BG_INPUT,
            corner_radius=8,
            command=self._on_type_switch,
        )
        self.type_switcher.pack(fill="x", padx=12, pady=(0, 12))

        # Text section
        self.text_section = ctk.CTkFrame(self.tab_content, fg_color="transparent")
        self.text_section.pack(fill="x")

        txt_card = self._make_card(self.text_section, pady=(0, 10))
        self._card_label(txt_card, "TEXT CONTENT")
        self.txt_content = ctk.CTkTextbox(
            txt_card, height=62, fg_color=BG_INPUT, border_width=1, border_color=BORDER_SUBTLE, corner_radius=8
        )
        self.txt_content.pack(fill="x", padx=12, pady=(0, 12))
        self.txt_content.bind("<KeyRelease>", lambda _e: self._on_text_changed())

        font_card = self._make_card(self.text_section, pady=(0, 10))
        self._card_label(font_card, "TYPOGRAPHY")

        font_row = ctk.CTkFrame(font_card, fg_color="transparent")
        font_row.pack(fill="x", padx=12, pady=(0, 8))
        font_row.grid_columnconfigure(0, weight=1)
        self.font_menu = ctk.CTkOptionMenu(
            font_row,
            values=self._curated_fonts,
            fg_color=BG_INPUT,
            button_color=BG_CARD_HOVER,
            button_hover_color=ACCENT_PRIMARY,
            command=self._on_font_family_change,
        )
        self.font_menu.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            font_row, text="All…", width=48, height=28, corner_radius=8,
            fg_color=BG_CARD_HOVER, hover_color=ACCENT_PRIMARY,
            command=self._open_all_fonts_dialog,
        ).grid(row=0, column=1)

        self.weight_seg = ctk.CTkSegmentedButton(
            font_card,
            values=["Regular", "Medium", "Bold", "ExtraBold"],
            selected_color=ACCENT_PRIMARY,
            selected_hover_color=ACCENT_HOVER,
            unselected_color=BG_INPUT,
            fg_color=BG_INPUT,
            command=self._on_weight_change,
        )
        self.weight_seg.pack(fill="x", padx=12, pady=(0, 10))

        sz_hdr = ctk.CTkFrame(font_card, fg_color="transparent")
        sz_hdr.pack(fill="x", padx=12)
        ctk.CTkLabel(
            sz_hdr, text="FONT SIZE (% WIDTH)", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT_MUTED
        ).pack(side="left")
        self.font_size_entry = ctk.CTkEntry(
            sz_hdr, width=54, height=24, fg_color=BG_INPUT, border_color=BORDER_SUBTLE, justify="right"
        )
        self.font_size_entry.pack(side="right")
        self.font_size_entry.bind("<Return>", lambda _e: self._on_font_size_entry())
        self.font_size_entry.bind("<FocusOut>", lambda _e: self._on_font_size_entry())

        self.font_size_slider = ctk.CTkSlider(
            font_card, from_=0.6, to=15.0, number_of_steps=144,
            progress_color=ACCENT_PRIMARY, button_color=TEXT_PRIMARY, button_hover_color=ACCENT_HOVER,
            command=self._on_font_size_slider,
        )
        self.font_size_slider.pack(fill="x", padx=12, pady=(6, 12))

        # Color & Alignment card
        ca_card = self._make_card(self.text_section, pady=(0, 8))
        self._card_label(ca_card, "COLOR & ALIGNMENT")
        ca_row = ctk.CTkFrame(ca_card, fg_color="transparent")
        ca_row.pack(fill="x", padx=12, pady=(0, 12))

        self.btn_text_swatch = ctk.CTkButton(
            ca_row, text="", width=32, height=30, corner_radius=8,
            fg_color="#FFFFFF", hover_color="#FFFFFF",
            border_width=1, border_color=BORDER_SUBTLE,
            command=lambda: self._pick_color("text_color", self.text_color_entry, self.btn_text_swatch),
        )
        self.btn_text_swatch.pack(side="left", padx=(0, 6))

        self.text_color_entry = ctk.CTkEntry(
            ca_row, width=82, height=30, fg_color=BG_INPUT, border_color=BORDER_SUBTLE, font=(FONT_MONO, 11)
        )
        self.text_color_entry.pack(side="left", padx=(0, 8))
        self.text_color_entry.bind(
            "<KeyRelease>",
            lambda _e: self._on_hex_entry("text_color", self.text_color_entry, self.btn_text_swatch),
        )

        self.align_seg = ctk.CTkSegmentedButton(
            ca_row,
            values=["Left", "Center", "Right"],
            selected_color=ACCENT_PRIMARY,
            selected_hover_color=ACCENT_HOVER,
            unselected_color=BG_INPUT,
            fg_color=BG_INPUT,
            command=self._on_align_change,
        )
        self.align_seg.pack(side="left", fill="x", expand=True)

        # Image section (shown when Image / Logo selected)
        self.image_section = ctk.CTkFrame(self.tab_content, fg_color="transparent")
        img_card = self._make_card(self.image_section, pady=(0, 10))
        self._card_label(img_card, "LOGO / IMAGE FILE")
        ctk.CTkButton(
            img_card,
            text="Upload Logo / Image",
            image=get_icon("upload", size=16, color=TEXT_PRIMARY, accent=ACCENT_TEXT),
            compound="left",
            height=36,
            corner_radius=RADIUS_BTN,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            font=(FONT_FAMILY, 12, "bold"),
            command=self._upload_logo_image,
        ).pack(fill="x", padx=12, pady=(0, 6))

        self.lbl_logo_name = ctk.CTkLabel(
            img_card,
            text="No image selected (.png, .jpg, .webp)",
            font=(FONT_FAMILY, 10),
            text_color=TEXT_MUTED,
            wraplength=260,
        )
        self.lbl_logo_name.pack(anchor="w", padx=12, pady=(0, 10))

        sc_hdr = ctk.CTkFrame(img_card, fg_color="transparent")
        sc_hdr.pack(fill="x", padx=12)
        ctk.CTkLabel(
            sc_hdr, text="LOGO SCALE (% WIDTH)", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT_MUTED
        ).pack(side="left")
        self.lbl_img_scale = ctk.CTkLabel(
            sc_hdr, text="18%", font=(FONT_MONO, 10, "bold"), text_color=ACCENT_TEXT,
            fg_color=ACCENT_SOFT_BG, corner_radius=6, padx=7, pady=1,
        )
        self.lbl_img_scale.pack(side="right")

        self.img_scale_slider = ctk.CTkSlider(
            img_card, from_=5, to=80, number_of_steps=75,
            progress_color=ACCENT_PRIMARY, button_color=TEXT_PRIMARY, button_hover_color=ACCENT_HOVER,
            command=self._on_img_scale_slider,
        )
        self.img_scale_slider.pack(fill="x", padx=12, pady=(6, 12))

    def _build_effects_tab(self) -> None:
        # Opacity card
        op_card = self._make_card(self.tab_effects, pady=(4, 10))
        op_hdr = ctk.CTkFrame(op_card, fg_color="transparent")
        op_hdr.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(op_hdr, text="MASTER OPACITY", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT_MUTED).pack(side="left")
        self.lbl_opacity_val = ctk.CTkLabel(
            op_hdr, text="35%", font=(FONT_MONO, 10, "bold"), text_color=ACCENT_TEXT,
            fg_color=ACCENT_SOFT_BG, corner_radius=6, padx=8, pady=2,
        )
        self.lbl_opacity_val.pack(side="right")
        self.opacity_slider = ctk.CTkSlider(
            op_card, from_=0, to=100, number_of_steps=100,
            progress_color=ACCENT_PRIMARY, button_color=TEXT_PRIMARY, button_hover_color=ACCENT_HOVER,
            command=self._on_opacity_slider,
        )
        self.opacity_slider.pack(fill="x", padx=12, pady=(4, 12))

        # Letter Spacing card
        sp_card = self._make_card(self.tab_effects, pady=(0, 10))
        sp_hdr = ctk.CTkFrame(sp_card, fg_color="transparent")
        sp_hdr.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(sp_hdr, text="LETTER SPACING", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT_MUTED).pack(side="left")
        self.lbl_spacing_val = ctk.CTkLabel(
            sp_hdr, text="+2 px", font=(FONT_MONO, 10, "bold"), text_color=ACCENT_TEXT,
            fg_color=ACCENT_SOFT_BG, corner_radius=6, padx=8, pady=2,
        )
        self.lbl_spacing_val.pack(side="right")
        self.spacing_slider = ctk.CTkSlider(
            sp_card, from_=-5.0, to=30.0, number_of_steps=70,
            progress_color=ACCENT_PRIMARY, button_color=TEXT_PRIMARY, button_hover_color=ACCENT_HOVER,
            command=self._on_spacing_slider,
        )
        self.spacing_slider.pack(fill="x", padx=12, pady=(4, 12))

        # Drop Shadow toggle card (progressive disclosure)
        sh_card = self._make_card(self.tab_effects, pady=(0, 10))
        self.shadow_var = ctk.BooleanVar(value=False)
        self.sw_shadow = ctk.CTkSwitch(
            sh_card, text="Drop Shadow", variable=self.shadow_var,
            font=(FONT_FAMILY, 12, "bold"), text_color=TEXT_PRIMARY,
            progress_color=ACCENT_PRIMARY, command=self._on_shadow_toggle,
        )
        self.sw_shadow.pack(anchor="w", padx=12, pady=10)

        self.shadow_box = ctk.CTkFrame(sh_card, fg_color=BG_INPUT, corner_radius=8)
        sh_r1 = ctk.CTkFrame(self.shadow_box, fg_color="transparent")
        sh_r1.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(sh_r1, text="Intensity", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).pack(side="left")
        self.lbl_shadow_int = ctk.CTkLabel(sh_r1, text="60%", font=(FONT_MONO, 10), text_color=TEXT_PRIMARY)
        self.lbl_shadow_int.pack(side="right")
        self.shadow_int_slider = ctk.CTkSlider(
            self.shadow_box, from_=0, to=100, number_of_steps=100,
            progress_color=ACCENT_PRIMARY, command=self._on_shadow_int,
        )
        self.shadow_int_slider.pack(fill="x", padx=10, pady=(4, 6))

        sh_r2 = ctk.CTkFrame(self.shadow_box, fg_color="transparent")
        sh_r2.pack(fill="x", padx=10)
        ctk.CTkLabel(sh_r2, text="Offset", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).pack(side="left")
        self.lbl_shadow_off = ctk.CTkLabel(sh_r2, text="4 px", font=(FONT_MONO, 10), text_color=TEXT_PRIMARY)
        self.lbl_shadow_off.pack(side="right")
        self.shadow_off_slider = ctk.CTkSlider(
            self.shadow_box, from_=1, to=30, number_of_steps=29,
            progress_color=ACCENT_PRIMARY, command=self._on_shadow_off,
        )
        self.shadow_off_slider.pack(fill="x", padx=10, pady=(4, 10))

        # Outline / Stroke toggle card (progressive disclosure)
        ol_card = self._make_card(self.tab_effects, pady=(0, 10))
        self.outline_var = ctk.BooleanVar(value=False)
        self.sw_outline = ctk.CTkSwitch(
            ol_card, text="Outline / Stroke", variable=self.outline_var,
            font=(FONT_FAMILY, 12, "bold"), text_color=TEXT_PRIMARY,
            progress_color=ACCENT_PRIMARY, command=self._on_outline_toggle,
        )
        self.sw_outline.pack(anchor="w", padx=12, pady=10)

        self.outline_box = ctk.CTkFrame(ol_card, fg_color=BG_INPUT, corner_radius=8)
        ol_r1 = ctk.CTkFrame(self.outline_box, fg_color="transparent")
        ol_r1.pack(fill="x", padx=10, pady=(8, 6))
        self.btn_outline_swatch = ctk.CTkButton(
            ol_r1, text="", width=26, height=24, corner_radius=6, fg_color="#000000",
            border_width=1, border_color=BORDER_SUBTLE,
            command=lambda: self._pick_color("outline_color", self.outline_color_entry, self.btn_outline_swatch),
        )
        self.btn_outline_swatch.pack(side="left", padx=(0, 6))
        self.outline_color_entry = ctk.CTkEntry(
            ol_r1, width=82, height=24, fg_color=BG_CARD, border_color=BORDER_SUBTLE, font=(FONT_MONO, 10)
        )
        self.outline_color_entry.pack(side="left")
        self.outline_color_entry.bind(
            "<KeyRelease>",
            lambda _e: self._on_hex_entry("outline_color", self.outline_color_entry, self.btn_outline_swatch),
        )
        self.lbl_outline_w = ctk.CTkLabel(ol_r1, text="2.0 px", font=(FONT_MONO, 10), text_color=TEXT_PRIMARY)
        self.lbl_outline_w.pack(side="right")
        self.outline_w_slider = ctk.CTkSlider(
            self.outline_box, from_=1, to=12, number_of_steps=22,
            progress_color=ACCENT_PRIMARY, command=self._on_outline_width,
        )
        self.outline_w_slider.pack(fill="x", padx=10, pady=(0, 10))

        # Background Pill / Box toggle card (progressive disclosure)
        bg_card = self._make_card(self.tab_effects, pady=(0, 8))
        self.bg_var = ctk.BooleanVar(value=False)
        self.sw_bg = ctk.CTkSwitch(
            bg_card, text="Background Pill / Box", variable=self.bg_var,
            font=(FONT_FAMILY, 12, "bold"), text_color=TEXT_PRIMARY,
            progress_color=ACCENT_PRIMARY, command=self._on_bg_toggle,
        )
        self.sw_bg.pack(anchor="w", padx=12, pady=10)

        self.bg_box = ctk.CTkFrame(bg_card, fg_color=BG_INPUT, corner_radius=8)
        bg_r1 = ctk.CTkFrame(self.bg_box, fg_color="transparent")
        bg_r1.pack(fill="x", padx=10, pady=(8, 6))
        self.btn_bg_swatch = ctk.CTkButton(
            bg_r1, text="", width=26, height=24, corner_radius=6, fg_color="#000000",
            border_width=1, border_color=BORDER_SUBTLE,
            command=lambda: self._pick_color("bg_color", self.bg_color_entry, self.btn_bg_swatch),
        )
        self.btn_bg_swatch.pack(side="left", padx=(0, 6))
        self.bg_color_entry = ctk.CTkEntry(
            bg_r1, width=82, height=24, fg_color=BG_CARD, border_color=BORDER_SUBTLE, font=(FONT_MONO, 10)
        )
        self.bg_color_entry.pack(side="left")
        self.bg_color_entry.bind(
            "<KeyRelease>",
            lambda _e: self._on_hex_entry("bg_color", self.bg_color_entry, self.btn_bg_swatch),
        )

        bg_r2 = ctk.CTkFrame(self.bg_box, fg_color="transparent")
        bg_r2.pack(fill="x", padx=10)
        ctk.CTkLabel(bg_r2, text="Padding", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).pack(side="left")
        self.lbl_bg_pad = ctk.CTkLabel(bg_r2, text="14 px", font=(FONT_MONO, 10), text_color=TEXT_PRIMARY)
        self.lbl_bg_pad.pack(side="right")
        self.bg_pad_slider = ctk.CTkSlider(
            self.bg_box, from_=4, to=60, number_of_steps=56,
            progress_color=ACCENT_PRIMARY, command=self._on_bg_pad,
        )
        self.bg_pad_slider.pack(fill="x", padx=10, pady=(4, 6))

        bg_r3 = ctk.CTkFrame(self.bg_box, fg_color="transparent")
        bg_r3.pack(fill="x", padx=10)
        ctk.CTkLabel(bg_r3, text="Box Opacity", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).pack(side="left")
        self.lbl_bg_op = ctk.CTkLabel(bg_r3, text="55%", font=(FONT_MONO, 10), text_color=TEXT_PRIMARY)
        self.lbl_bg_op.pack(side="right")
        self.bg_op_slider = ctk.CTkSlider(
            self.bg_box, from_=0, to=100, number_of_steps=100,
            progress_color=ACCENT_PRIMARY, command=self._on_bg_op,
        )
        self.bg_op_slider.pack(fill="x", padx=10, pady=(4, 10))

    def _build_layout_tab(self) -> None:
        # 9-Point Position Grid Card
        pos_card = self._make_card(self.tab_layout, pady=(4, 10))
        pos_hdr = ctk.CTkFrame(pos_card, fg_color="transparent")
        pos_hdr.pack(fill="x", padx=12, pady=(10, 8))
        ctk.CTkLabel(pos_hdr, text="9-POINT ANCHOR", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT_MUTED).pack(side="left")
        self.lbl_coords = ctk.CTkLabel(
            pos_hdr, text="Bottom-Right", font=(FONT_MONO, 10, "bold"), text_color=ACCENT_TEXT,
            fg_color=ACCENT_SOFT_BG, corner_radius=6, padx=8, pady=2,
        )
        self.lbl_coords.pack(side="right")

        grid_frame = ctk.CTkFrame(pos_card, fg_color=BG_INPUT, corner_radius=10, border_width=1, border_color=BORDER_SUBTLE)
        grid_frame.pack(fill="x", padx=12, pady=(0, 12))
        grid_frame.grid_columnconfigure((0, 1, 2), weight=1)

        symbols = {
            "top_left": "↖", "top_center": "↑", "top_right": "↗",
            "center_left": "←", "center": "•", "center_right": "→",
            "bottom_left": "↙", "bottom_center": "↓", "bottom_right": "↘",
        }
        for idx, key in enumerate(ANCHOR_KEYS):
            r, c = divmod(idx, 3)
            btn = ctk.CTkButton(
                grid_frame,
                text=symbols[key],
                height=34,
                corner_radius=8,
                font=(FONT_FAMILY, 13, "bold"),
                fg_color=BG_CARD,
                hover_color=ACCENT_HOVER,
                command=lambda k=key: self._on_anchor_clicked(k),
            )
            btn.grid(row=r, column=c, padx=5, pady=5, sticky="ew")
            self._anchor_buttons[key] = btn

        # Rotation Card
        rot_card = self._make_card(self.tab_layout, pady=(0, 10))
        rot_hdr = ctk.CTkFrame(rot_card, fg_color="transparent")
        rot_hdr.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(rot_hdr, text="ROTATION", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT_MUTED).pack(side="left")
        ctk.CTkButton(
            rot_hdr, text="0°", width=34, height=22, corner_radius=6, font=(FONT_MONO, 10),
            fg_color=BG_CARD_HOVER, hover_color=ACCENT_PRIMARY,
            command=self._reset_rotation,
        ).pack(side="right", padx=(6, 0))
        self.lbl_rot_val = ctk.CTkLabel(
            rot_hdr, text="0°", font=(FONT_MONO, 10, "bold"), text_color=ACCENT_TEXT,
            fg_color=ACCENT_SOFT_BG, corner_radius=6, padx=8, pady=2,
        )
        self.lbl_rot_val.pack(side="right")
        self.rot_slider = ctk.CTkSlider(
            rot_card, from_=-180, to=180, number_of_steps=360,
            progress_color=ACCENT_PRIMARY, button_color=TEXT_PRIMARY, button_hover_color=ACCENT_HOVER,
            command=self._on_rotation_slider,
        )
        self.rot_slider.pack(fill="x", padx=12, pady=(4, 12))

        # Safe Margins Card
        mg_card = self._make_card(self.tab_layout, pady=(0, 8))
        mg_hdr = ctk.CTkFrame(mg_card, fg_color="transparent")
        mg_hdr.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(mg_hdr, text="SAFE MARGINS", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT_MUTED).pack(side="left")
        self.lbl_margin_val = ctk.CTkLabel(
            mg_hdr, text="4.0%", font=(FONT_MONO, 10, "bold"), text_color=ACCENT_TEXT,
            fg_color=ACCENT_SOFT_BG, corner_radius=6, padx=8, pady=2,
        )
        self.lbl_margin_val.pack(side="right")
        self.margin_slider = ctk.CTkSlider(
            mg_card, from_=0.0, to=15.0, number_of_steps=60,
            progress_color=ACCENT_PRIMARY, button_color=TEXT_PRIMARY, button_hover_color=ACCENT_HOVER,
            command=self._on_margin_slider,
        )
        self.margin_slider.pack(fill="x", padx=12, pady=(4, 12))

    def _on_inspector_tab_change(self, choice: str) -> None:
        self._active_inspector_tab = choice
        self.tab_content.pack_forget()
        self.tab_effects.pack_forget()
        self.tab_layout.pack_forget()
        if choice == "Content":
            self.tab_content.pack(fill="x", expand=True)
        elif choice == "Effects":
            self.tab_effects.pack(fill="x", expand=True)
        else:
            self.tab_layout.pack(fill="x", expand=True)

    # ══════════════════════════════════════════════════════════════════
    #  Preset Management
    # ══════════════════════════════════════════════════════════════════

    def _refresh_preset_menu(self) -> None:
        names = list(self.presets.keys())
        self.preset_menu.configure(values=names)
        if self.active_preset_name in names:
            self.preset_menu.set(self.active_preset_name)

    def _on_preset_selected(self, name: str) -> None:
        if name not in self.presets:
            return
        self.active_preset_name = name
        self.wm_config = copy.deepcopy(self.presets[name])
        self.settings["watermark_active_preset"] = name
        save_settings(self.settings)
        self._apply_config_to_ui(self.wm_config)
        self._schedule_composite_render(immediate=True)

    def _save_new_preset(self) -> None:
        dialog = ctk.CTkInputDialog(text="Enter a name for the new preset:", title="Save Watermark Preset")
        name = (dialog.get_input() or "").strip()
        if not name:
            return
        if name in self.presets:
            if not messagebox.askyesno("Overwrite Preset?", f"Preset '{name}' already exists. Overwrite it?"):
                return
        self.presets[name] = copy.deepcopy(self.wm_config)
        self.active_preset_name = name
        self.settings["watermark_presets"] = self.presets
        self.settings["watermark_active_preset"] = name
        save_settings(self.settings)
        self._refresh_preset_menu()

    def _update_active_preset(self) -> None:
        name = self.active_preset_name
        self.presets[name] = copy.deepcopy(self.wm_config)
        self.settings["watermark_presets"] = self.presets
        self.settings["watermark_active_preset"] = name
        save_settings(self.settings)
        messagebox.showinfo("Preset Updated", f"Saved changes to '{name}'.")

    def _delete_active_preset(self) -> None:
        name = self.active_preset_name
        if name == "Evoless Signature":
            messagebox.showinfo(
                "Built-in Preset",
                "'Evoless Signature' is the built-in default preset and cannot be deleted.\n"
                "You can still customize it or save your own presets.",
            )
            return
        if len(self.presets) <= 1:
            return
        if not messagebox.askyesno("Delete Preset", f"Delete preset '{name}'?"):
            return
        del self.presets[name]
        fallback = "Evoless Signature" if "Evoless Signature" in self.presets else next(iter(self.presets))
        self.active_preset_name = fallback
        self.wm_config = copy.deepcopy(self.presets[fallback])
        self.settings["watermark_presets"] = self.presets
        self.settings["watermark_active_preset"] = fallback
        save_settings(self.settings)
        self._refresh_preset_menu()
        self._apply_config_to_ui(self.wm_config)
        self._schedule_composite_render(immediate=True)

    # ══════════════════════════════════════════════════════════════════
    #  Sync Config <-> Inspector UI
    # ══════════════════════════════════════════════════════════════════

    def _apply_config_to_ui(self, cfg: dict) -> None:
        self._suppress_updates = True
        try:
            wm_type = "Image / Logo" if cfg.get("type") == "image" else "Text"
            self.type_switcher.set(wm_type)
            self._toggle_type_sections(wm_type)

            self.txt_content.delete("1.0", "end")
            self.txt_content.insert("1.0", cfg.get("text", ""))

            fam = cfg.get("font_family", "Segoe UI")
            cur_vals = list(self.font_menu.cget("values"))
            if fam and fam not in cur_vals:
                cur_vals.append(fam)
                self.font_menu.configure(values=cur_vals)
            self.font_menu.set(fam)

            self.weight_seg.set(cfg.get("font_weight", "Regular"))

            f_pct = float(cfg.get("font_size_pct", 2.2))
            self.font_size_slider.set(max(0.6, min(15.0, f_pct)))
            self.font_size_entry.delete(0, "end")
            self.font_size_entry.insert(0, f"{f_pct:.1f}")

            t_hex = cfg.get("text_color", "#FFFFFF")
            self.text_color_entry.delete(0, "end")
            self.text_color_entry.insert(0, t_hex)
            self.btn_text_swatch.configure(
                fg_color=self._safe_tk_hex(t_hex, "#FFFFFF"),
                hover_color=self._safe_tk_hex(t_hex, "#FFFFFF"),
            )

            self.align_seg.set(cfg.get("text_align", "Center"))

            sp = float(cfg.get("letter_spacing", 2.0))
            self.spacing_slider.set(max(-5.0, min(30.0, sp)))
            self.lbl_spacing_val.configure(text=f"{sp:+.0f} px" if sp != 0 else "0 px")

            # Shadow (progressive disclosure)
            sh_on = bool(cfg.get("shadow_enabled", False))
            self.shadow_var.set(sh_on)
            self.shadow_int_slider.set(float(cfg.get("shadow_intensity", 60)))
            self.lbl_shadow_int.configure(text=f"{int(round(cfg.get('shadow_intensity', 60)))}%")
            self.shadow_off_slider.set(float(cfg.get("shadow_offset", 4.0)))
            self.lbl_shadow_off.configure(text=f"{int(round(cfg.get('shadow_offset', 4.0)))} px")
            self._pack_optional_box(self.shadow_box, sh_on)

            # Outline (progressive disclosure)
            ol_on = bool(cfg.get("outline_enabled", False))
            self.outline_var.set(ol_on)
            ol_hex = cfg.get("outline_color", "#000000")
            self.outline_color_entry.delete(0, "end")
            self.outline_color_entry.insert(0, ol_hex)
            self.btn_outline_swatch.configure(
                fg_color=self._safe_tk_hex(ol_hex, "#000000"),
                hover_color=self._safe_tk_hex(ol_hex, "#000000"),
            )
            ol_w = float(cfg.get("outline_width", 2.0))
            self.outline_w_slider.set(max(1.0, min(12.0, ol_w)))
            self.lbl_outline_w.configure(text=f"{ol_w:.1f} px")
            self._pack_optional_box(self.outline_box, ol_on)

            # Background Box (progressive disclosure)
            bg_on = bool(cfg.get("bg_enabled", False))
            self.bg_var.set(bg_on)
            bg_hex = cfg.get("bg_color", "#000000")
            self.bg_color_entry.delete(0, "end")
            self.bg_color_entry.insert(0, bg_hex)
            self.btn_bg_swatch.configure(
                fg_color=self._safe_tk_hex(bg_hex, "#000000"),
                hover_color=self._safe_tk_hex(bg_hex, "#000000"),
            )
            bg_pad = float(cfg.get("bg_padding", 14.0))
            self.bg_pad_slider.set(max(4.0, min(60.0, bg_pad)))
            self.lbl_bg_pad.configure(text=f"{int(round(bg_pad))} px")
            bg_op = float(cfg.get("bg_opacity", 55))
            self.bg_op_slider.set(max(0.0, min(100.0, bg_op)))
            self.lbl_bg_op.configure(text=f"{int(round(bg_op))}%")
            self._pack_optional_box(self.bg_box, bg_on)

            # Image fields
            self._update_logo_label(cfg.get("image_path", ""))
            img_sc = float(cfg.get("image_scale_pct", 18.0))
            self.img_scale_slider.set(max(5.0, min(80.0, img_sc)))
            self.lbl_img_scale.configure(text=f"{int(round(img_sc))}%")

            # Shared fields
            op = float(cfg.get("opacity", 35))
            self.opacity_slider.set(max(0.0, min(100.0, op)))
            self.lbl_opacity_val.configure(text=f"{int(round(op))}%")

            rot = float(cfg.get("rotation", 0.0))
            self.rot_slider.set(max(-180.0, min(180.0, rot)))
            self.lbl_rot_val.configure(text=f"{int(round(rot))}°")

            mg = float(cfg.get("margin_pct", 4.0))
            self.margin_slider.set(max(0.0, min(15.0, mg)))
            self.lbl_margin_val.configure(text=f"{mg:.1f}%")

            self._refresh_anchor_buttons(cfg.get("anchor", "bottom_right"))
        finally:
            self._suppress_updates = False

    def _safe_tk_hex(self, val: str, fallback: str) -> str:
        r, g, b = parse_hex_color(val, parse_hex_color(fallback))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _pack_optional_box(self, box: ctk.CTkFrame, visible: bool) -> None:
        if visible:
            box.pack(fill="x", padx=10, pady=(0, 10))
        else:
            box.pack_forget()

    def _toggle_type_sections(self, wm_type_label: str) -> None:
        if wm_type_label == "Image / Logo":
            self.text_section.pack_forget()
            self.image_section.pack(fill="x")
        else:
            self.image_section.pack_forget()
            self.text_section.pack(fill="x")

    def _refresh_anchor_buttons(self, active_anchor: str) -> None:
        for k, btn in self._anchor_buttons.items():
            btn.configure(fg_color=ACCENT_PRIMARY if k == active_anchor else BG_CARD)
        if active_anchor in ANCHOR_KEYS:
            self.lbl_coords.configure(text=active_anchor.replace("_", "-").title())
        else:
            nx = self.wm_config.get("norm_x", 0.5)
            ny = self.wm_config.get("norm_y", 0.5)
            self.lbl_coords.configure(text=f"Custom ({nx:.2f}, {ny:.2f})")

    def _update_logo_label(self, img_path: str) -> None:
        if img_path and os.path.isfile(img_path):
            try:
                with Image.open(img_path) as im:
                    self.lbl_logo_name.configure(
                        text=f"{os.path.basename(img_path)} ({im.width}×{im.height})",
                        text_color=TEXT_PRIMARY,
                    )
                    return
            except Exception:
                pass
        self.lbl_logo_name.configure(
            text="No image selected (.png, .jpg, .webp)",
            text_color=TEXT_MUTED,
        )

    # ══════════════════════════════════════════════════════════════════
    #  Inspector Callbacks
    # ══════════════════════════════════════════════════════════════════

    def _on_type_switch(self, choice: str) -> None:
        if self._suppress_updates:
            return
        self.wm_config["type"] = "image" if choice == "Image / Logo" else "text"
        self._toggle_type_sections(choice)
        self._schedule_composite_render(immediate=True)

    def _on_text_changed(self) -> None:
        if self._suppress_updates:
            return
        self.wm_config["text"] = self.txt_content.get("1.0", "end-1c")
        self._schedule_composite_render()

    def _on_font_family_change(self, choice: str) -> None:
        if self._suppress_updates:
            return
        self.wm_config["font_family"] = choice
        self._schedule_composite_render(immediate=True)

    def _open_all_fonts_dialog(self) -> None:
        all_families = get_available_font_families(curated_only=False)

        def _picked(fam: str) -> None:
            vals = list(self.font_menu.cget("values"))
            if fam not in vals:
                vals.append(fam)
                self.font_menu.configure(values=vals)
            self.font_menu.set(fam)
            self.wm_config["font_family"] = fam
            self._schedule_composite_render(immediate=True)

        _FontPickerDialog(
            self,
            families=all_families,
            current_family=self.wm_config.get("font_family", "Segoe UI"),
            on_select=_picked,
        )

    def _on_weight_change(self, choice: str) -> None:
        if self._suppress_updates:
            return
        self.wm_config["font_weight"] = choice
        self._schedule_composite_render(immediate=True)

    def _on_font_size_slider(self, value: float) -> None:
        if self._suppress_updates:
            return
        val = round(float(value), 1)
        self.wm_config["font_size_pct"] = val
        self.font_size_entry.delete(0, "end")
        self.font_size_entry.insert(0, f"{val:.1f}")
        self._schedule_composite_render()

    def _on_font_size_entry(self) -> None:
        if self._suppress_updates:
            return
        try:
            val = max(0.5, min(25.0, float(self.font_size_entry.get().strip().rstrip("%"))))
        except ValueError:
            return
        self.wm_config["font_size_pct"] = val
        self.font_size_slider.set(max(0.6, min(15.0, val)))
        self._schedule_composite_render(immediate=True)

    def _pick_color(self, key: str, entry: ctk.CTkEntry, swatch: ctk.CTkButton) -> None:
        initial = self._safe_tk_hex(self.wm_config.get(key, "#FFFFFF"), "#FFFFFF")
        _, hex_code = colorchooser.askcolor(color=initial, title="Pick Color", parent=self)
        if not hex_code:
            return
        hex_code = hex_code.upper()
        self.wm_config[key] = hex_code
        entry.delete(0, "end")
        entry.insert(0, hex_code)
        swatch.configure(fg_color=hex_code, hover_color=hex_code)
        self._schedule_composite_render(immediate=True)

    def _on_hex_entry(self, key: str, entry: ctk.CTkEntry, swatch: ctk.CTkButton) -> None:
        if self._suppress_updates:
            return
        txt = entry.get().strip()
        if not txt.startswith("#"):
            txt = "#" + txt
        if len(txt) in (4, 7):
            try:
                r, g, b = parse_hex_color(txt)
                norm_hex = f"#{r:02x}{g:02x}{b:02x}".upper()
                self.wm_config[key] = norm_hex
                swatch.configure(fg_color=norm_hex, hover_color=norm_hex)
                self._schedule_composite_render()
            except Exception:
                pass

    def _on_align_change(self, choice: str) -> None:
        if self._suppress_updates:
            return
        self.wm_config["text_align"] = choice
        self._schedule_composite_render(immediate=True)

    def _on_spacing_slider(self, value: float) -> None:
        if self._suppress_updates:
            return
        val = round(float(value), 1)
        self.wm_config["letter_spacing"] = val
        self.lbl_spacing_val.configure(text=f"{val:+.0f} px" if val != 0 else "0 px")
        self._schedule_composite_render()

    def _on_shadow_toggle(self) -> None:
        if self._suppress_updates:
            return
        on = bool(self.shadow_var.get())
        self.wm_config["shadow_enabled"] = on
        self._pack_optional_box(self.shadow_box, on)
        self._schedule_composite_render(immediate=True)

    def _on_shadow_int(self, value: float) -> None:
        if self._suppress_updates:
            return
        val = int(round(value))
        self.wm_config["shadow_intensity"] = val
        self.lbl_shadow_int.configure(text=f"{val}%")
        self._schedule_composite_render()

    def _on_shadow_off(self, value: float) -> None:
        if self._suppress_updates:
            return
        val = int(round(value))
        self.wm_config["shadow_offset"] = float(val)
        self.lbl_shadow_off.configure(text=f"{val} px")
        self._schedule_composite_render()

    def _on_outline_toggle(self) -> None:
        if self._suppress_updates:
            return
        on = bool(self.outline_var.get())
        self.wm_config["outline_enabled"] = on
        self._pack_optional_box(self.outline_box, on)
        self._schedule_composite_render(immediate=True)

    def _on_outline_width(self, value: float) -> None:
        if self._suppress_updates:
            return
        val = round(float(value), 1)
        self.wm_config["outline_width"] = val
        self.lbl_outline_w.configure(text=f"{val:.1f} px")
        self._schedule_composite_render()

    def _on_bg_toggle(self) -> None:
        if self._suppress_updates:
            return
        on = bool(self.bg_var.get())
        self.wm_config["bg_enabled"] = on
        self._pack_optional_box(self.bg_box, on)
        self._schedule_composite_render(immediate=True)

    def _on_bg_pad(self, value: float) -> None:
        if self._suppress_updates:
            return
        val = int(round(value))
        self.wm_config["bg_padding"] = float(val)
        self.lbl_bg_pad.configure(text=f"{val} px")
        self._schedule_composite_render()

    def _on_bg_op(self, value: float) -> None:
        if self._suppress_updates:
            return
        val = int(round(value))
        self.wm_config["bg_opacity"] = val
        self.lbl_bg_op.configure(text=f"{val}%")
        self._schedule_composite_render()

    def _upload_logo_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Watermark Logo / Image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")],
        )
        if not path:
            return
        self.load_logo_from_path(path)

    def load_logo_from_path(self, path: str) -> None:
        self.wm_config["image_path"] = path
        self.wm_config["type"] = "image"
        self.type_switcher.set("Image / Logo")
        self._toggle_type_sections("Image / Logo")
        self._update_logo_label(path)
        self._schedule_composite_render(immediate=True)

    def _on_img_scale_slider(self, value: float) -> None:
        if self._suppress_updates:
            return
        val = round(float(value), 1)
        self.wm_config["image_scale_pct"] = val
        self.lbl_img_scale.configure(text=f"{int(round(val))}%")
        self._schedule_composite_render()

    def _on_opacity_slider(self, value: float) -> None:
        if self._suppress_updates:
            return
        val = int(round(value))
        self.wm_config["opacity"] = val
        self.lbl_opacity_val.configure(text=f"{val}%")
        self._schedule_composite_render()

    def _on_rotation_slider(self, value: float) -> None:
        if self._suppress_updates:
            return
        val = round(float(value), 1)
        self.wm_config["rotation"] = val
        self.lbl_rot_val.configure(text=f"{int(round(val))}°")
        self._schedule_composite_render()

    def _reset_rotation(self) -> None:
        self.wm_config["rotation"] = 0.0
        self.rot_slider.set(0.0)
        self.lbl_rot_val.configure(text="0°")
        self._schedule_composite_render(immediate=True)

    def _on_anchor_clicked(self, anchor_key: str) -> None:
        self.wm_config["anchor"] = anchor_key
        vw, vh = self._active_video_dimensions()
        wm_full = self._get_cached_full_watermark(vw, vh)
        if wm_full is not None:
            x, y = compute_watermark_xy(vw, vh, wm_full.width, wm_full.height, self.wm_config)
            nx, ny = xy_to_normalized_center(x, y, wm_full.width, wm_full.height, vw, vh)
            self.wm_config["norm_x"] = nx
            self.wm_config["norm_y"] = ny
        self._refresh_anchor_buttons(anchor_key)
        self._schedule_composite_render(immediate=True)

    def _on_margin_slider(self, value: float) -> None:
        if self._suppress_updates:
            return
        val = round(float(value), 1)
        self.wm_config["margin_pct"] = val
        self.lbl_margin_val.configure(text=f"{val:.1f}%")
        self._schedule_composite_render()

    # ══════════════════════════════════════════════════════════════════
    #  Queue & Active Video Management (Modern Cards + Dropzone)
    # ══════════════════════════════════════════════════════════════════

    def _refresh_queue_visibility(self) -> None:
        if self.video_queue:
            self.empty_hero.grid_forget()
            self.queue_list.grid(row=0, column=0, sticky="nsew")
        else:
            self.queue_list.grid_forget()
            self.empty_hero.grid(row=0, column=0, sticky="nsew")

    def add_videos(self) -> None:
        files = filedialog.askopenfilenames(
            title="Select Videos to Watermark",
            filetypes=[
                ("Video Files", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.flv *.wmv *.ts"),
                ("All Files", "*.*"),
            ],
        )
        for f in files:
            self.add_path(f)

    def add_path(self, filepath: str) -> None:
        """Handle a dropped or browsed file (video -> queue, image -> logo)."""
        filepath = filepath.strip("{}").strip('"').strip("'")
        if not filepath or not os.path.isfile(filepath):
            return

        ext = os.path.splitext(filepath)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            self.load_logo_from_path(filepath)
            return

        if ext not in VIDEO_EXTENSIONS:
            log.debug("Ignoring unsupported dropped file in watermark mode: %s", filepath)
            return

        if filepath in self.video_queue:
            return

        self.video_queue.append(filepath)
        badge = ext.lstrip(".").upper() or "VID"
        idx = self.queue_list.add_card(
            title=os.path.basename(filepath),
            subtitle="Inspecting video metadata…",
            badge=badge,
        )
        self._refresh_queue_visibility()
        if self.on_queue_changed:
            self.on_queue_changed(len(self.video_queue))

        threading.Thread(
            target=self._probe_and_update_card,
            args=(filepath, idx),
            daemon=True,
        ).start()

    def _probe_and_update_card(self, filepath: str, _hint_idx: int) -> None:
        info = probe_video(filepath)
        self.video_infos[filepath] = info

        def _apply() -> None:
            if filepath not in self.video_queue:
                return
            idx = self.video_queue.index(filepath)
            ext = os.path.splitext(filepath)[1].lstrip(".").upper() or "VID"
            if info.valid:
                meta = f"{info.width}×{info.height} • {format_duration(info.duration)} • {ext}"
                self.queue_list.update_meta(idx, subtitle=meta, badge=ext)
                self.queue_list.update_status(idx, "Ready")
                if self.active_video_path is None:
                    self.queue_list.set_active_index(idx)
                    self._select_video_for_preview(filepath)
            else:
                self.queue_list.update_meta(idx, subtitle=info.error or "Invalid video", badge="ERR")
                self.queue_list.update_status(idx, "✗ Error")

        self._safe_after(_apply)

    def _safe_after(self, fn: Callable[[], None]) -> None:
        self._ui_dispatch_queue.put(fn)

    def _drain_ui_queue(self) -> None:
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        while True:
            try:
                fn = self._ui_dispatch_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as exc:
                log.debug("UI dispatch callback error: %s", exc)
        try:
            self.after(25, self._drain_ui_queue)
        except Exception:
            pass

    def _on_card_selected(self, index: int) -> None:
        if 0 <= index < len(self.video_queue):
            path = self.video_queue[index]
            if path != self.active_video_path:
                self._select_video_for_preview(path)

    def _select_video_for_preview(self, filepath: str) -> None:
        self.stop_playback()
        info = self.video_infos.get(filepath)
        if info is None:
            info = probe_video(filepath)
            self.video_infos[filepath] = info

        self.active_video_path = filepath
        self.active_video_info = info
        self.current_time = 0.0
        self._raw_frame_pil = None

        if info.valid:
            dur = max(0.1, info.duration)
            self.timeline_slider.configure(from_=0.0, to=dur, state="normal")
            self.timeline_var.set(0.0)
            self.btn_play.configure(state="normal", image=self._icon_play)
            self.lbl_timecode.configure(text=f"00:00 / {format_duration(info.duration)}")
            self.lbl_res_badge.configure(text=f"{info.width}×{info.height} • {info.fps:.1f} fps")
            self._fetch_frame_async(0.0)
        else:
            self.timeline_slider.configure(state="disabled")
            self.btn_play.configure(state="disabled", image=self._icon_play)
            self.lbl_timecode.configure(text="00:00 / 00:00")
            self.lbl_res_badge.configure(text=f"Error: {info.error}")
            self._schedule_composite_render(immediate=True)

    def _remove_at_index(self, index: int) -> None:
        if self._export_locked or not (0 <= index < len(self.video_queue)):
            return
        removed = self.video_queue.pop(index)
        self.queue_list.remove_at(index)

        if removed == self.active_video_path:
            self.stop_playback()
            self.active_video_path = None
            self.active_video_info = None
            self._raw_frame_pil = None
            if self.video_queue:
                next_idx = min(index, len(self.video_queue) - 1)
                self.queue_list.set_active_index(next_idx)
                self._select_video_for_preview(self.video_queue[next_idx])
            else:
                self._reset_preview_empty()

        self._refresh_queue_visibility()
        if self.on_queue_changed:
            self.on_queue_changed(len(self.video_queue))

    def clear_queue(self) -> None:
        if self._export_locked:
            return
        self.stop_playback()
        self.video_queue.clear()
        self.video_infos.clear()
        self.active_video_path = None
        self.active_video_info = None
        self._raw_frame_pil = None
        self.queue_list.clear()
        self._refresh_queue_visibility()
        self._reset_preview_empty()
        if self.on_queue_changed:
            self.on_queue_changed(0)

    def _reset_preview_empty(self) -> None:
        self.timeline_var.set(0.0)
        self.timeline_slider.configure(state="disabled")
        self.btn_play.configure(state="disabled", image=self._icon_play)
        self.lbl_timecode.configure(text="00:00 / 00:00")
        self.lbl_res_badge.configure(text="16:9 • Blank Preview")
        self._schedule_composite_render(immediate=True)

    def update_row_status(self, index: int, status_text: str, progress: Optional[float] = None) -> None:
        self.after(0, lambda: self.queue_list.update_status(index, status_text, progress=progress))

    def set_export_locked(self, locked: bool) -> None:
        self._export_locked = locked

    # ══════════════════════════════════════════════════════════════════
    #  Video Frame Extraction, Playback & Scrubbing
    # ══════════════════════════════════════════════════════════════════

    def _active_video_dimensions(self) -> tuple[int, int]:
        if self.active_video_info and self.active_video_info.valid:
            return self.active_video_info.width, self.active_video_info.height
        return 1920, 1080

    def _compute_preview_rect(self) -> tuple[int, int, int, int]:
        cw = max(64, self.canvas.winfo_width())
        ch = max(64, self.canvas.winfo_height())
        vw, vh = self._active_video_dimensions()
        aspect = vw / float(max(1, vh))

        if cw / float(ch) > aspect:
            ph = max(32, ch - 8)
            pw = max(32, int(round(ph * aspect)))
        else:
            pw = max(32, cw - 8)
            ph = max(32, int(round(pw / aspect)))

        x0 = (cw - pw) // 2
        y0 = (ch - ph) // 2
        return x0, y0, pw, ph

    def _fetch_frame_async(self, timestamp: float) -> None:
        path = self.active_video_path
        info = self.active_video_info
        if not path or not info or not info.valid:
            return
        _, _, pw, ph = self._compute_preview_rect()

        def _worker() -> None:
            img = extract_preview_frame(path, timestamp, pw, ph, duration=info.duration)
            if img is None:
                return

            def _apply() -> None:
                if self.active_video_path != path:
                    return
                self._raw_frame_pil = img
                self._render_preview_now()

            self._safe_after(_apply)

        threading.Thread(target=_worker, daemon=True).start()

    def toggle_playback(self) -> None:
        if not self.active_video_path or not self.active_video_info or not self.active_video_info.valid:
            return
        if self.is_playing:
            self.stop_playback()
        else:
            self._start_playback()

    def _start_playback(self) -> None:
        self.stop_playback()
        info = self.active_video_info
        if not info or not info.valid:
            return
        if self.current_time >= max(0.0, info.duration - 0.15):
            self.current_time = 0.0

        _, _, pw, ph = self._compute_preview_rect()
        self.is_playing = True
        self.btn_play.configure(image=self._icon_pause)

        def _on_frame(frame_pil: Image.Image, cur_t: float) -> None:
            def _apply() -> None:
                if not self.is_playing:
                    return
                self._raw_frame_pil = frame_pil
                self.current_time = min(info.duration, cur_t)
                if not self._is_scrubbing_slider:
                    self.timeline_var.set(self.current_time)
                self.lbl_timecode.configure(
                    text=f"{format_duration(self.current_time)} / {format_duration(info.duration)}"
                )
                self._render_preview_now()

            self._safe_after(_apply)

        def _on_eof() -> None:
            self._safe_after(self.stop_playback)

        self._playback_stream = VideoPlaybackStream(
            filepath=info.filepath,
            start_time=self.current_time,
            target_w=pw,
            target_h=ph,
            fps=info.fps,
            on_frame=_on_frame,
            on_eof=_on_eof,
        )
        self._playback_stream.start()

    def stop_playback(self) -> None:
        self.is_playing = False
        if self._playback_stream is not None:
            self._playback_stream.stop()
            self._playback_stream = None
        if hasattr(self, "btn_play"):
            self.btn_play.configure(image=self._icon_play)

    def _on_timeline_scrub(self, value: float) -> None:
        if not self.active_video_info or not self.active_video_info.valid:
            return
        self._is_scrubbing_slider = True
        if self.is_playing:
            self.stop_playback()
        self.current_time = float(value)
        self.lbl_timecode.configure(
            text=f"{format_duration(self.current_time)} / {format_duration(self.active_video_info.duration)}"
        )
        if self._scrub_after_id is not None:
            self.after_cancel(self._scrub_after_id)
        self._scrub_after_id = self.after(45, lambda: self._fetch_frame_async(self.current_time))

    def _on_timeline_release(self, _event) -> None:
        self._is_scrubbing_slider = False
        if self.active_video_info and self.active_video_info.valid:
            self._fetch_frame_async(self.current_time)

    # ══════════════════════════════════════════════════════════════════
    #  1:1 WYSIWYG Preview Compositing & Caching
    # ══════════════════════════════════════════════════════════════════

    def _get_cached_full_watermark(self, video_w: int, video_h: int) -> Optional[Image.Image]:
        key = appearance_cache_key(self.wm_config, video_w, video_h)
        if key != self._wm_cache_key:
            self._wm_cache_key = key
            self._wm_cached_full = render_watermark_rgba(self.wm_config, video_w, video_h)
            self._wm_cached_preview_key = None
            self._wm_cached_preview = None
        return self._wm_cached_full

    def _get_cached_preview_watermark(
        self, video_w: int, video_h: int, preview_w: int, preview_h: int
    ) -> tuple[Optional[Image.Image], int, int]:
        full = self._get_cached_full_watermark(video_w, video_h)
        if full is None:
            return None, 0, 0

        scale_x = preview_w / float(max(1, video_w))
        scale_y = preview_h / float(max(1, video_h))
        pw_wm = max(1, int(round(full.width * scale_x)))
        ph_wm = max(1, int(round(full.height * scale_y)))

        p_key = (self._wm_cache_key, pw_wm, ph_wm)
        if p_key != self._wm_cached_preview_key:
            self._wm_cached_preview_key = p_key
            self._wm_cached_preview = full.resize((pw_wm, ph_wm), Image.Resampling.LANCZOS)

        exact_x, exact_y = compute_watermark_xy(video_w, video_h, full.width, full.height, self.wm_config)
        px = int(round(exact_x * scale_x))
        py = int(round(exact_y * scale_y))
        return self._wm_cached_preview, px, py

    def _schedule_composite_render(self, immediate: bool = False) -> None:
        if self._render_after_id is not None:
            self.after_cancel(self._render_after_id)
            self._render_after_id = None
        if immediate:
            self._render_preview_now()
        else:
            self._render_after_id = self.after(16, self._render_preview_now)

    def _on_canvas_resize(self, _event) -> None:
        if self._resize_after_id is not None:
            self.after_cancel(self._resize_after_id)
        self._render_preview_now()
        if self.active_video_info and self.active_video_info.valid and not self.is_playing:
            self._resize_after_id = self.after(120, lambda: self._fetch_frame_async(self.current_time))

    def _build_placeholder_frame(self, pw: int, ph: int) -> Image.Image:
        img = Image.new("RGBA", (pw, ph), (15, 15, 22, 255))
        draw = ImageDraw.Draw(img)
        step = max(28, pw // 16)
        for x in range(0, pw, step):
            draw.line([(x, 0), (x, ph)], fill=(23, 23, 33, 255), width=1)
        for y in range(0, ph, step):
            draw.line([(0, y), (pw, y)], fill=(23, 23, 33, 255), width=1)
        draw.rectangle([0, 0, pw - 1, ph - 1], outline=(38, 38, 56, 255), width=1)
        return img

    def _render_preview_now(self) -> None:
        self._render_after_id = None
        x0, y0, pw, ph = self._compute_preview_rect()
        self._display_rect = (x0, y0, pw, ph)
        vw, vh = self._active_video_dimensions()

        if self._raw_frame_pil is not None:
            if self._raw_frame_pil.size != (pw, ph):
                base = self._raw_frame_pil.resize((pw, ph), Image.Resampling.BILINEAR).convert("RGBA")
            else:
                base = self._raw_frame_pil.convert("RGBA")
        else:
            base = self._build_placeholder_frame(pw, ph)

        wm_prev, px, py = self._get_cached_preview_watermark(vw, vh, pw, ph)
        if wm_prev is not None:
            overlay_canvas = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            overlay_canvas.paste(wm_prev, (px, py))
            base = Image.alpha_composite(base, overlay_canvas)
            self._last_wm_preview_box = (x0 + px, y0 + py, x0 + px + wm_prev.width, y0 + py + wm_prev.height)
        else:
            self._last_wm_preview_box = None

        self._preview_photo = ImageTk.PhotoImage(base.convert("RGB"))
        self.canvas.delete("all")
        self.canvas.create_image(x0, y0, anchor="nw", image=self._preview_photo)

        if self._raw_frame_pil is None and not self.video_queue:
            self.canvas.create_text(
                x0 + pw // 2,
                y0 + ph // 2 - 12,
                text="Live Watermark Preview",
                fill=TEXT_SECONDARY,
                font=(FONT_FAMILY, 12, "bold"),
            )
            self.canvas.create_text(
                x0 + pw // 2,
                y0 + ph // 2 + 12,
                text="Drag watermark anywhere or add a video below",
                fill=TEXT_MUTED,
                font=(FONT_FAMILY, 10),
            )

        if self._is_dragging_wm:
            margin = max(0.0, min(40.0, float(self.wm_config.get("margin_pct", 4.0)))) / 100.0
            mx_l = x0 + int(round(pw * margin))
            mx_r = x0 + int(round(pw * (1.0 - margin)))
            my_t = y0 + int(round(ph * margin))
            my_b = y0 + int(round(ph * (1.0 - margin)))
            cx = x0 + pw // 2
            cy = y0 + ph // 2
            self.canvas.create_rectangle(mx_l, my_t, mx_r, my_b, outline=ACCENT_GLOW, dash=(4, 4))
            self.canvas.create_line(cx, y0, cx, y0 + ph, fill="#3D3D4A", dash=(3, 5))
            self.canvas.create_line(x0, cy, x0 + pw, cy, fill="#3D3D4A", dash=(3, 5))

            if self._last_wm_preview_box is not None:
                bx0, by0, bx1, by1 = self._last_wm_preview_box
                self.canvas.create_rectangle(bx0 - 2, by0 - 2, bx1 + 2, by1 + 2, outline="#FFFFFF", dash=(3, 3))

    # ══════════════════════════════════════════════════════════════════
    #  Direct Canvas Drag-and-Drop Repositioning
    # ══════════════════════════════════════════════════════════════════

    def _hit_test_watermark(self, cx: int, cy: int) -> bool:
        if self._last_wm_preview_box is None:
            return False
        bx0, by0, bx1, by1 = self._last_wm_preview_box
        pad = 10
        return (bx0 - pad) <= cx <= (bx1 + pad) and (by0 - pad) <= cy <= (by1 + pad)

    def _on_canvas_hover(self, event) -> None:
        if self._is_dragging_wm:
            return
        self.canvas.configure(cursor="fleur" if self._hit_test_watermark(event.x, event.y) else "arrow")

    def _on_canvas_press(self, event) -> None:
        if not self._hit_test_watermark(event.x, event.y):
            return
        bx0, by0, _, _ = self._last_wm_preview_box
        self._is_dragging_wm = True
        self._drag_offset_x = event.x - bx0
        self._drag_offset_y = event.y - by0
        self.canvas.configure(cursor="fleur")
        self._render_preview_now()

    def _on_canvas_drag(self, event) -> None:
        if not self._is_dragging_wm:
            return
        x0, y0, pw, ph = self._display_rect
        vw, vh = self._active_video_dimensions()
        full = self._get_cached_full_watermark(vw, vh)
        if full is None:
            return

        wm_prev, _, _ = self._get_cached_preview_watermark(vw, vh, pw, ph)
        if wm_prev is None:
            return

        rel_px = (event.x - self._drag_offset_x) - x0
        rel_py = (event.y - self._drag_offset_y) - y0
        scale_x = vw / float(max(1, pw))
        scale_y = vh / float(max(1, ph))

        nx, ny = xy_to_normalized_center(
            rel_px * scale_x, rel_py * scale_y, full.width, full.height, vw, vh
        )
        self.wm_config["anchor"] = "custom"
        self.wm_config["norm_x"] = nx
        self.wm_config["norm_y"] = ny
        self._refresh_anchor_buttons("custom")
        self._render_preview_now()

    def _on_canvas_release(self, _event) -> None:
        if not self._is_dragging_wm:
            return
        self._is_dragging_wm = False
        self.canvas.configure(cursor="arrow")
        self._render_preview_now()

    # ══════════════════════════════════════════════════════════════════
    #  Public Helpers
    # ══════════════════════════════════════════════════════════════════

    def get_watermark_config(self) -> dict:
        """Return a deep copy of the active watermark configuration."""
        return copy.deepcopy(self.wm_config)

    def get_video_queue(self) -> list[str]:
        """Return the ordered list of queued video file paths."""
        return list(self.video_queue)
