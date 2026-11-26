"""
AudioMorph — flagship desktop creative suite window.

Features an Obsidian & Royal Amethyst design system, categorized vector-icon
sidebar rail, contextual workspace headers, interactive dashed dropzone empty
states, custom dark FileQueueCard lists (replacing classic Treeview), and an
Export & Delivery panel powering Convert, Download, Watermark Studio, and AI tools.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from tkinter import filedialog, messagebox
from typing import Callable, Optional

import customtkinter as ctk

from core.ai_worker import AIWorker
from core.online_trimmer import StreamMetadata, download_trimmed_segment, format_seconds
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
    BG_SIDEBAR,
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
from utils.config import get_icon_path, load_settings, save_settings
from utils.logger import get_logger
from utils.validators import is_valid_url, platform_display_name

log = get_logger(__name__)

# ── Try optional drag-and-drop ────────────────────────────────────────────
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _HAS_DND = True
except ImportError:
    _HAS_DND = False
    log.debug("tkinterdnd2 not available — drag-and-drop disabled")


if _HAS_DND:
    class _BaseWindow(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    _BaseWindow = ctk.CTk


class _SidebarNavItem(ctk.CTkFrame):
    """Sleek sidebar navigation row with 3px left glow bar, icon, and pill highlight."""

    def __init__(
        self,
        master,
        label: str,
        icon_name: str,
        command: Callable[[], None],
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", height=38, corner_radius=10, **kwargs)
        self._label_text = label
        self._icon_name = icon_name
        self._command = command
        self._active = False

        self.pack_propagate(False)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._accent_bar = ctk.CTkFrame(
            self, width=3, height=20, corner_radius=2, fg_color="transparent"
        )
        self._accent_bar.grid(row=0, column=0, padx=(2, 6), pady=8, sticky="ns")

        self._icon_idle = get_icon(icon_name, size=18, color=TEXT_SECONDARY, accent=TEXT_SECONDARY)
        self._icon_active = get_icon(icon_name, size=18, color=TEXT_PRIMARY, accent=ACCENT_TEXT)

        self._btn = ctk.CTkButton(
            self,
            text=f"  {label}",
            image=self._icon_idle,
            compound="left",
            anchor="w",
            height=32,
            corner_radius=9,
            font=(FONT_FAMILY, 12, "bold"),
            fg_color="transparent",
            hover_color=BG_CARD,
            text_color=TEXT_SECONDARY,
            command=self._command,
        )
        self._btn.grid(row=0, column=1, sticky="nsew", padx=(0, 4), pady=1)

    def set_active(self, active: bool) -> None:
        self._active = active
        if active:
            self._accent_bar.configure(fg_color=ACCENT_GLOW)
            self._btn.configure(
                fg_color=ACCENT_SOFT_BG,
                hover_color=ACCENT_SOFT_BG,
                text_color=TEXT_PRIMARY,
                image=self._icon_active,
            )
        else:
            self._accent_bar.configure(fg_color="transparent")
            self._btn.configure(
                fg_color="transparent",
                hover_color=BG_CARD,
                text_color=TEXT_SECONDARY,
                image=self._icon_idle,
            )


class AudioMorphApp(_BaseWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("AudioMorph Studio • Created by Evoless")
        try:
            self.iconbitmap(get_icon_path())
        except Exception:
            pass

        self.geometry("1300x760")
        self.minsize(1100, 660)
        self.configure(fg_color=BG_ROOT)

        self.settings = load_settings()
        self.file_queue: list[str] = []
        self.current_mode: str = "CONVERT"
        self.current_convert_category: str = "AUDIO"
        self.worker = None
        self._last_output_dir: str = ""
        self._last_watermark_output_dir: str = ""

        self.formats = {
            "AUDIO": ["MP3", "WAV", "AAC", "FLAC"],
            "VIDEO": ["MP4", "MKV", "MOV", "AVI"],
            "IMAGE": ["JPG", "PNG", "WEBP", "ICO"],
            "ARCHIVE": ["ZIP", "TAR"],
        }
        self.download_formats = ["MP4", "MKV", "WEBM", "MP3", "WAV", "M4A", "FLAC", "JPG", "PNG", "WEBP"]
        self.download_qualities = [
            "Best Available", "4K", "2K", "1080p", "720p", "480p", "Audio Only",
        ]
        self.watermark_formats = ["Original (Same as input)", "MP4", "MKV", "MOV", "AVI"]
        self.watermark_qualities = [
            "High (Visually Lossless / CRF 18)",
            "Balanced (CRF 21)",
            "Compact (CRF 25)",
        ]

        self._nav_items: dict[str, _SidebarNavItem] = {}
        self._cat_buttons: dict[str, ctk.CTkButton] = {}

        self._build_ui()
        self._load_ui_settings()
        if _HAS_DND:
            self._enable_drag_and_drop()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ══════════════════════════════════════════════════════════════════
    #  UI Construction
    # ══════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_center_workspace()
        self._build_right_export_panel()

        # Lazy-initialized full-screen/studio views (created on first navigation click)
        self.cutter_frame = None
        self.subtitle_frame = None
        self.bg_frame = None
        self.vocal_frame = None
        self.watermark_frame = None
        self.viral_frame = None

    def _get_cutter_frame(self):
        if self.cutter_frame is None:
            from gui.cutter_widget import AudioCutterWidget
            self.cutter_frame = AudioCutterWidget(
                self, bg_color=BG_ROOT, panel_color=BG_PANEL, accent_color=ACCENT_PRIMARY
            )
            self._register_dnd_targets([self.cutter_frame])
        return self.cutter_frame

    def _get_subtitle_frame(self):
        if self.subtitle_frame is None:
            from gui.subtitle_widget import SubtitleWidget
            self.subtitle_frame = SubtitleWidget(
                self, bg_color=BG_ROOT, panel_color=BG_PANEL, accent_color=ACCENT_PRIMARY
            )
            self._register_dnd_targets([self.subtitle_frame])
        return self.subtitle_frame

    def _get_bg_frame(self):
        if self.bg_frame is None:
            from gui.bg_remover_widget import BgRemoverWidget
            self.bg_frame = BgRemoverWidget(
                self, bg_color=BG_ROOT, panel_color=BG_PANEL, accent_color=ACCENT_PRIMARY
            )
            self._register_dnd_targets([self.bg_frame])
        return self.bg_frame

    def _get_vocal_frame(self):
        if self.vocal_frame is None:
            from gui.vocal_isolation_widget import VocalIsolationWidget
            self.vocal_frame = VocalIsolationWidget(
                self, bg_color=BG_ROOT, panel_color=BG_PANEL, accent_color=ACCENT_PRIMARY
            )
            self._register_dnd_targets([self.vocal_frame])
        return self.vocal_frame

    def _get_watermark_frame(self):
        if self.watermark_frame is None:
            from gui.watermark_widget import WatermarkEditorWidget
            self.watermark_frame = WatermarkEditorWidget(
                self.center_container,
                settings=self.settings,
                on_queue_changed=self._on_watermark_queue_changed,
                bg_color=BG_ROOT,
                panel_color=BG_PANEL,
                accent_color=ACCENT_PRIMARY,
                text_main=TEXT_PRIMARY,
                text_muted=TEXT_SECONDARY,
            )
            self._register_dnd_targets([
                self.watermark_frame,
                getattr(self.watermark_frame, "canvas", None),
                getattr(self.watermark_frame, "empty_hero", None),
                getattr(self.watermark_frame, "queue_list", None),
            ])
        return self.watermark_frame

    def _get_viral_frame(self):
        if self.viral_frame is None:
            from gui.viral_clipper_widget import ViralClipperWidget
            self.viral_frame = ViralClipperWidget(
                self,
                settings=self.settings,
                bg_color=BG_ROOT,
                panel_color=BG_PANEL,
                accent_color=ACCENT_PRIMARY,
            )
            self._register_dnd_targets([
                self.viral_frame,
                getattr(self.viral_frame, "preview_canvas", None),
            ])
        return self.viral_frame

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(
            self,
            width=230,
            fg_color=BG_SIDEBAR,
            corner_radius=0,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        self.sidebar = sidebar

        # Brand Header
        brand_box = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand_box.pack(fill="x", padx=16, pady=(16, 10))

        ctk.CTkLabel(
            brand_box,
            text="",
            image=get_icon("brand", size=30, color=TEXT_PRIMARY, accent=ACCENT_PRIMARY),
        ).pack(side="left", padx=(0, 10))

        title_col = ctk.CTkFrame(brand_box, fg_color="transparent")
        title_col.pack(side="left", fill="x")
        ctk.CTkLabel(
            title_col,
            text="AudioMorph",
            font=(FONT_FAMILY, 16, "bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_col,
            text="PRO STUDIO",
            font=(FONT_MONO, 9, "bold"),
            text_color=ACCENT_TEXT,
            fg_color=ACCENT_SOFT_BG,
            corner_radius=5,
            padx=6,
            pady=1,
        ).pack(anchor="w", pady=(2, 0))

        def _group_header(text: str) -> None:
            ctk.CTkLabel(
                sidebar,
                text=text,
                font=(FONT_FAMILY, 10, "bold"),
                text_color=TEXT_MUTED,
                anchor="w",
            ).pack(fill="x", padx=18, pady=(10, 4))

        def _add_nav(key: str, label: str, icon_name: str, cmd: Callable[[], None]) -> None:
            item = _SidebarNavItem(sidebar, label=label, icon_name=icon_name, command=cmd)
            item.pack(fill="x", padx=10, pady=1)
            self._nav_items[key] = item

        _group_header("CONVERT SUITE")
        _add_nav("CONVERT", "Media Converter", "audio", lambda: self._switch_to_convert(self.current_convert_category))

        _group_header("WEB & STREAM")
        _add_nav("DOWNLOAD", "Media Downloader", "download", self._switch_to_download)

        _group_header("CREATIVE & AI STUDIO")
        _add_nav("VIRAL_CLIPPER", "Viral Clipper", "clipper", self._switch_to_viral_clipper)
        _add_nav("WATERMARK", "Watermark Studio", "watermark", self._switch_to_watermark)
        _add_nav("CUT", "Cut & Trim Audio", "cut", self._switch_to_cutter)
        _add_nav("SUBTITLES", "AI Subtitles", "subtitles", self._switch_to_subtitles)
        _add_nav("BG_REMOVER", "AI BG Remover", "bg_remover", self._switch_to_bg_remover)
        _add_nav("VOCAL_ISOLATOR", "Vocal Isolator", "vocal", self._switch_to_vocal_isolator)
        _add_nav("AI_TOOLS", "AI Batch Queue", "ai_tools", self._switch_to_aitools)

        # Subtle footer version hint
        ctk.CTkLabel(
            sidebar,
            text="Obsidian Edition • FFmpeg Ready",
            font=(FONT_FAMILY, 10),
            text_color=TEXT_MUTED,
        ).pack(side="bottom", pady=(6, 18))

    def _build_center_workspace(self) -> None:
        self.center_container = ctk.CTkFrame(self, fg_color=BG_ROOT)
        self.center_container.grid(row=0, column=1, padx=(18, 14), pady=18, sticky="nsew")
        self.center_container.grid_rowconfigure(1, weight=1)
        self.center_container.grid_columnconfigure(0, weight=1)

        # ── Contextual Top Workspace Header ──────────────────────────
        self.header_frame = ctk.CTkFrame(
            self.center_container,
            fg_color=BG_PANEL,
            corner_radius=RADIUS_PANEL,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        self.header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.header_frame.grid_columnconfigure(1, weight=1)

        self.hdr_icon_lbl = ctk.CTkLabel(
            self.header_frame,
            text="",
            image=get_icon("audio", size=24, color=TEXT_PRIMARY, accent=ACCENT_TEXT),
            width=40,
            height=40,
            fg_color=ACCENT_SOFT_BG,
            corner_radius=10,
        )
        self.hdr_icon_lbl.grid(row=0, column=0, padx=(14, 12), pady=12)

        hdr_text = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        hdr_text.grid(row=0, column=1, sticky="ew", pady=10)
        self.hdr_title = ctk.CTkLabel(
            hdr_text,
            text="Universal Converter",
            font=(FONT_FAMILY, 16, "bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        )
        self.hdr_title.pack(anchor="w")
        self.hdr_subtitle = ctk.CTkLabel(
            hdr_text,
            text="Convert audio, video, images, and archives at high speed",
            font=(FONT_FAMILY, 11),
            text_color=TEXT_SECONDARY,
            anchor="w",
        )
        self.hdr_subtitle.pack(anchor="w")

        hdr_actions = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        hdr_actions.grid(row=0, column=2, padx=14, pady=12)

        self.lbl_count_badge = ctk.CTkLabel(
            hdr_actions,
            text="0 files",
            font=(FONT_MONO, 10, "bold"),
            text_color=ACCENT_TEXT,
            fg_color=ACCENT_SOFT_BG,
            corner_radius=8,
            padx=10,
            pady=5,
        )
        self.lbl_count_badge.pack(side="left", padx=(0, 8))

        self.btn_hdr_add = ctk.CTkButton(
            hdr_actions,
            text="Add Files",
            image=get_icon("add", size=14, color=TEXT_PRIMARY),
            compound="left",
            height=32,
            corner_radius=9,
            font=(FONT_FAMILY, 11, "bold"),
            fg_color=BG_CARD,
            hover_color=BG_CARD_HOVER,
            border_width=1,
            border_color=BORDER_SUBTLE,
            command=self._on_header_add,
        )
        self.btn_hdr_add.pack(side="left", padx=(0, 6))

        self.btn_hdr_clear = ctk.CTkButton(
            hdr_actions,
            text="Clear",
            image=get_icon("trash", size=14, color=TEXT_SECONDARY),
            compound="left",
            height=32,
            width=82,
            corner_radius=9,
            font=(FONT_FAMILY, 11),
            fg_color=BG_CARD,
            hover_color=BG_CARD_HOVER,
            border_width=1,
            border_color=BORDER_SUBTLE,
            text_color=TEXT_SECONDARY,
            command=self._on_header_clear,
        )
        self.btn_hdr_clear.pack(side="left")

        # ── Standard Queue Workspace (CONVERT / DOWNLOAD / AI_TOOLS) ─
        self.queue_frame = ctk.CTkFrame(self.center_container, fg_color="transparent")
        self.queue_frame.grid(row=1, column=0, sticky="nsew")
        self.queue_frame.grid_rowconfigure(2, weight=1)
        self.queue_frame.grid_columnconfigure(0, weight=1)

        # Converter Segmented Category Bar (Audio | Video | Image | Archive)
        self.conv_toolbar = ctk.CTkFrame(
            self.queue_frame,
            fg_color=BG_PANEL,
            corner_radius=RADIUS_CARD,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        self.conv_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.conv_toolbar.grid_columnconfigure((0, 1, 2, 3), weight=1)

        cat_defs = [
            ("AUDIO", "Audio", "audio"),
            ("VIDEO", "Video", "video"),
            ("IMAGE", "Image", "image"),
            ("ARCHIVE", "Archive", "archive"),
        ]
        for idx, (cat_key, label, icon_name) in enumerate(cat_defs):
            btn = ctk.CTkButton(
                self.conv_toolbar,
                text=f"  {label}",
                image=get_icon(icon_name, size=16, color=TEXT_PRIMARY, accent=ACCENT_TEXT),
                compound="left",
                height=36,
                corner_radius=8,
                font=(FONT_FAMILY, 12, "bold"),
                fg_color="transparent",
                hover_color=BG_CARD_HOVER,
                command=lambda k=cat_key: self._switch_to_convert(k),
            )
            btn.grid(row=0, column=idx, padx=5, pady=5, sticky="ew")
            self._cat_buttons[cat_key] = btn

        # Download URL Toolbar
        self.dl_toolbar = ctk.CTkFrame(
            self.queue_frame,
            fg_color=BG_PANEL,
            corner_radius=RADIUS_CARD,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        self.url_entry = ctk.CTkEntry(
            self.dl_toolbar,
            placeholder_text="Paste video or audio URL (YouTube, TikTok, Instagram, Twitch, Kick, X)…",
            height=38,
            fg_color=BG_INPUT,
            border_color=BORDER_SUBTLE,
            corner_radius=9,
            font=(FONT_FAMILY, 12),
        )
        self.url_entry.pack(side="left", padx=(10, 8), pady=8, fill="x", expand=True)

        def _on_url_return(_e=None):
            if hasattr(self, "online_trimmer") and self.online_trimmer.winfo_ismapped():
                u = self.url_entry.get().strip()
                if u:
                    self.online_trimmer.load_url(u)
                    return
            self.add_url()

        self.url_entry.bind("<Return>", _on_url_return)

        ctk.CTkButton(
            self.dl_toolbar,
            text="Add URL",
            image=get_icon("add", size=14, color=TEXT_PRIMARY),
            compound="left",
            height=38,
            width=116,
            corner_radius=9,
            font=(FONT_FAMILY, 12, "bold"),
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            command=self.add_url,
        ).pack(side="left", padx=(0, 6), pady=8)

        self.btn_dl_trim = ctk.CTkButton(
            self.dl_toolbar,
            text="Trim Segment",
            image=get_icon("trim", size=14, color=TEXT_PRIMARY, accent=ACCENT_TEXT),
            compound="left",
            height=38,
            width=132,
            corner_radius=9,
            font=(FONT_FAMILY, 12, "bold"),
            fg_color=BG_CARD,
            hover_color=BG_CARD_HOVER,
            border_width=1,
            border_color=BORDER_SUBTLE,
            command=self._toggle_online_trimmer,
        )
        self.btn_dl_trim.pack(side="left", padx=(0, 10), pady=8)

        # Embedded Online Stream Trimmer Drawer (hidden by default)
        from gui.online_trimmer_widget import OnlineTrimmerDrawer
        self.online_trimmer = OnlineTrimmerDrawer(
            self.queue_frame,
            on_download_segment=self._on_download_trimmed_segment,
            on_close=self._hide_online_trimmer,
            get_url_fn=lambda: self.url_entry.get().strip(),
        )

        # Body container: toggles between EmptyDropzoneHero and ModernQueueList
        self.queue_body = ctk.CTkFrame(self.queue_frame, fg_color="transparent")
        self.queue_body.grid(row=2, column=0, sticky="nsew")
        self.queue_body.grid_rowconfigure(0, weight=1)
        self.queue_body.grid_columnconfigure(0, weight=1)

        self.empty_hero_convert = EmptyDropzoneHero(
            self.queue_body,
            title="Drop your media files here",
            subtitle="or click anywhere to browse from your computer • Supports MP4, MOV, MKV, MP3, WAV, FLAC, PNG, JPG, WebP",
            button_text="Select Files",
            on_browse=self.add_files,
            icon_name="upload",
            compact=False,
        )

        self.empty_hero_download = EmptyDropzoneHero(
            self.queue_body,
            title="Paste a link above to queue downloads",
            subtitle="Supports high-resolution video, playlists, lossless audio extraction, and thumbnail grabs",
            button_text="Focus URL Input",
            on_browse=lambda: self.url_entry.focus_set(),
            icon_name="download",
            platform_badges=["YouTube", "TikTok", "Instagram", "Twitch", "Kick", "X"],
            compact=False,
        )

        self.empty_hero_ai = EmptyDropzoneHero(
            self.queue_body,
            title="Drop media files for AI batch processing",
            subtitle="Queue images for AI background removal, videos for Whisper auto-subtitles, or tracks for vocal isolation",
            button_text="Select Media Files",
            on_browse=self.add_files,
            icon_name="ai_tools",
            compact=False,
        )

        self.queue_list = ModernQueueList(
            self.queue_body,
            on_remove_index=self._remove_at_index,
            compact=False,
        )

        # Status / speed readout bar under queue
        self.status_frame = ctk.CTkFrame(self.queue_frame, fg_color="transparent", height=24)
        self.status_frame.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self.speed_label = ctk.CTkLabel(
            self.status_frame, text="", font=(FONT_MONO, 10), text_color=TEXT_SECONDARY
        )
        self.speed_label.pack(side="left", padx=4)

    def _build_right_export_panel(self) -> None:
        self.right_frame = ctk.CTkFrame(
            self,
            width=280,
            fg_color=BG_PANEL,
            corner_radius=RADIUS_PANEL,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        self.right_frame.grid(row=0, column=2, padx=(0, 18), pady=18, sticky="nsew")
        self.right_frame.grid_propagate(False)
        self.right_frame.grid_columnconfigure(0, weight=1)
        self.right_frame.grid_rowconfigure(0, weight=1)
        self.right_frame.grid_rowconfigure(1, weight=0)

        # Scrollable upper config region (prevents overflow clipping on shorter viewports)
        self.right_top_panel = ctk.CTkScrollableFrame(
            self.right_frame,
            fg_color="transparent",
            scrollbar_button_color=BG_CARD,
            scrollbar_button_hover_color=ACCENT_PRIMARY,
        )
        self.right_top_panel.grid(row=0, column=0, padx=4, pady=(6, 0), sticky="nsew")

        self.lbl_config_title = ctk.CTkLabel(
            self.right_top_panel,
            text="EXPORT & DELIVERY",
            font=(FONT_FAMILY, 11, "bold"),
            text_color=TEXT_MUTED,
        )
        self.lbl_config_title.pack(anchor="w", padx=12, pady=(10, 10))

        # Format / Quality / AI cards
        self.lbl_format = ctk.CTkLabel(
            self.right_top_panel, text="TARGET FORMAT", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT_SECONDARY
        )
        self.format_menu = ctk.CTkOptionMenu(
            self.right_top_panel,
            values=self.formats["AUDIO"],
            fg_color=BG_CARD,
            button_color=BG_CARD_HOVER,
            button_hover_color=ACCENT_PRIMARY,
            corner_radius=RADIUS_BTN,
            height=34,
            command=self._on_format_change,
        )

        self.lbl_quality = ctk.CTkLabel(
            self.right_top_panel, text="QUALITY", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT_SECONDARY
        )
        self.quality_menu = ctk.CTkOptionMenu(
            self.right_top_panel,
            values=self.download_qualities,
            fg_color=BG_CARD,
            button_color=BG_CARD_HOVER,
            button_hover_color=ACCENT_PRIMARY,
            corner_radius=RADIUS_BTN,
            height=34,
        )

        self.lbl_ai_action = ctk.CTkLabel(
            self.right_top_panel, text="AI WORKFLOW", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT_SECONDARY
        )
        self.ai_action_menu = ctk.CTkOptionMenu(
            self.right_top_panel,
            values=["Remove Background (Image)", "Auto Subtitles (Video/Audio)", "Isolate Vocals (Audio)"],
            fg_color=BG_CARD,
            button_color=BG_CARD_HOVER,
            button_hover_color=ACCENT_PRIMARY,
            corner_radius=RADIUS_BTN,
            height=34,
        )

        self.lbl_wm_quality = ctk.CTkLabel(
            self.right_top_panel, text="QUALITY PRESET", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT_SECONDARY
        )
        self.wm_quality_menu = ctk.CTkOptionMenu(
            self.right_top_panel,
            values=self.watermark_qualities,
            fg_color=BG_CARD,
            button_color=BG_CARD_HOVER,
            button_hover_color=ACCENT_PRIMARY,
            corner_radius=RADIUS_BTN,
            height=34,
        )

        # Audio Converter fine-tuning controls
        self.lbl_sample_rate = ctk.CTkLabel(
            self.right_top_panel, text="SAMPLE RATE", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT_SECONDARY
        )
        self.sample_rate_menu = ctk.CTkOptionMenu(
            self.right_top_panel,
            values=["44100 Hz", "48000 Hz", "32000 Hz", "22050 Hz"],
            fg_color=BG_CARD,
            button_color=BG_CARD_HOVER,
            button_hover_color=ACCENT_PRIMARY,
            corner_radius=RADIUS_BTN,
            height=32,
        )
        self.lbl_channels = ctk.CTkLabel(
            self.right_top_panel, text="CHANNELS", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT_SECONDARY
        )
        self.channels_menu = ctk.CTkOptionMenu(
            self.right_top_panel,
            values=["Stereo", "Mono"],
            fg_color=BG_CARD,
            button_color=BG_CARD_HOVER,
            button_hover_color=ACCENT_PRIMARY,
            corner_radius=RADIUS_BTN,
            height=32,
        )
        self.normalize_audio_var = ctk.BooleanVar(value=bool(self.settings.get("normalize_audio", False)))
        self.chk_normalize_audio = ctk.CTkCheckBox(
            self.right_top_panel,
            text="Normalize audio loudness",
            variable=self.normalize_audio_var,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            font=(FONT_FAMILY, 12),
        )

        # Video Converter / Trimmer acceleration controls
        self.stream_copy_var = ctk.BooleanVar(value=bool(self.settings.get("fast_stream_copy", False)))
        self.chk_stream_copy = ctk.CTkCheckBox(
            self.right_top_panel,
            text="Fast Stream Copy (No Re-encode)",
            variable=self.stream_copy_var,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            font=(FONT_FAMILY, 11),
        )
        self.hw_accel_var = ctk.BooleanVar(value=bool(self.settings.get("hardware_accel", True)))
        self.chk_hw_accel = ctk.CTkCheckBox(
            self.right_top_panel,
            text="Hardware Accel (Auto GPU)",
            variable=self.hw_accel_var,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            font=(FONT_FAMILY, 11),
        )

        # Destination Card
        self.dest_card = ctk.CTkFrame(
            self.right_top_panel,
            fg_color=BG_CARD,
            corner_radius=RADIUS_CARD,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        self.dest_card.pack(fill="x", padx=10, pady=(10, 8))

        ctk.CTkLabel(
            self.dest_card,
            text="DESTINATION",
            font=(FONT_FAMILY, 10, "bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=12, pady=(10, 6))

        self.save_source_var = ctk.BooleanVar(value=True)
        self.chk_save_source = ctk.CTkCheckBox(
            self.dest_card,
            text="Save in source folder",
            variable=self.save_source_var,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            font=(FONT_FAMILY, 12),
        )
        self.chk_save_source.pack(anchor="w", padx=12, pady=(0, 6))

        self.playlist_var = ctk.BooleanVar(value=False)
        self.chk_playlist = ctk.CTkCheckBox(
            self.dest_card,
            text="Allow playlists",
            variable=self.playlist_var,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            font=(FONT_FAMILY, 12),
        )

        self.lbl_wm_suffix_hint = ctk.CTkLabel(
            self.dest_card,
            text="Appends _watermarked suffix",
            font=(FONT_FAMILY, 10),
            text_color=TEXT_MUTED,
        )

        # Folder preview chip
        self.path_chip = ctk.CTkFrame(
            self.dest_card,
            fg_color=BG_INPUT,
            corner_radius=8,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        self.path_chip.pack(fill="x", padx=12, pady=(4, 8))
        self.out_dir_label = ctk.CTkLabel(
            self.path_chip,
            text=" Source folder",
            image=get_icon("folder", size=14, color=TEXT_SECONDARY, accent=ACCENT_TEXT),
            compound="left",
            font=(FONT_MONO, 10),
            text_color=TEXT_SECONDARY,
            anchor="w",
        )
        self.out_dir_label.pack(fill="x", padx=8, pady=6)

        ctk.CTkButton(
            self.dest_card,
            text="Choose Folder",
            image=get_icon("folder", size=14, color=TEXT_PRIMARY),
            compound="left",
            command=self._select_output_folder,
            fg_color=BG_CARD_HOVER,
            hover_color=ACCENT_PRIMARY,
            corner_radius=8,
            height=32,
            font=(FONT_FAMILY, 11, "bold"),
        ).pack(fill="x", padx=12, pady=(0, 12))

        # Pinned bottom action dock (status + banner + progress + primary CTA)
        self.right_footer = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.right_footer.grid(row=1, column=0, sticky="ew")
        self.right_footer.grid_columnconfigure(0, weight=1)

        # Prominent Emerald Completion Banner (hidden until export/tasks succeed)
        self.completion_banner = ctk.CTkFrame(
            self.right_footer,
            fg_color=STATUS_SUCCESS_BG,
            corner_radius=RADIUS_CARD,
            border_width=1,
            border_color=STATUS_SUCCESS,
        )
        banner_hdr = ctk.CTkFrame(self.completion_banner, fg_color="transparent")
        banner_hdr.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(
            banner_hdr,
            text=" Export Complete",
            image=get_icon("check", size=15, color=STATUS_SUCCESS),
            compound="left",
            font=(FONT_FAMILY, 11, "bold"),
            text_color=STATUS_SUCCESS,
        ).pack(side="left")

        self.btn_open_wm_output = ctk.CTkButton(
            self.completion_banner,
            text="Open Output Folder",
            image=get_icon("folder", size=14, color=TEXT_PRIMARY, accent=STATUS_SUCCESS),
            compound="left",
            fg_color="#163F33",
            hover_color="#1D5444",
            text_color=TEXT_PRIMARY,
            corner_radius=8,
            height=30,
            font=(FONT_FAMILY, 11, "bold"),
            command=self._open_output_folder,
        )
        self.btn_open_wm_output.pack(fill="x", padx=10, pady=(2, 10))

        # Status readout
        self.lbl_wm_status = ctk.CTkLabel(
            self.right_footer,
            text="",
            font=(FONT_FAMILY, 11, "bold"),
            text_color=TEXT_SECONDARY,
            wraplength=240,
        )

        # Clean progress bar housed inside right export dock (hidden when idle)
        self.total_progress = ctk.CTkProgressBar(
            self.right_footer,
            height=6,
            corner_radius=3,
            progress_color=ACCENT_PRIMARY,
            fg_color=BG_CARD,
        )
        self.total_progress.set(0)

        # Primary Action & Cancel Buttons pinned cleanly at bottom
        self.btn_start = ctk.CTkButton(
            self.right_footer,
            text="CONVERT NOW",
            image=get_icon("export", size=16, color=TEXT_PRIMARY, accent=ACCENT_TEXT),
            compound="left",
            font=(FONT_FAMILY, 13, "bold"),
            height=46,
            corner_radius=RADIUS_BTN,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            command=self.start_action,
        )
        self.btn_start.grid(row=3, column=0, padx=14, pady=(0, 14), sticky="ew")

        self.btn_cancel = ctk.CTkButton(
            self.right_footer,
            text="CANCEL",
            image=get_icon("close", size=14, color=TEXT_PRIMARY),
            compound="left",
            font=(FONT_FAMILY, 13, "bold"),
            height=46,
            corner_radius=RADIUS_BTN,
            fg_color=CANCEL_BG,
            hover_color=CANCEL_HOVER,
            command=self._cancel_action,
        )

    # ══════════════════════════════════════════════════════════════════
    #  Header, Empty-State & Nav Synchronization
    # ══════════════════════════════════════════════════════════════════

    def _set_active_nav(self, active_key: str) -> None:
        for k, item in self._nav_items.items():
            item.set_active(k == active_key)

    def _update_header(
        self,
        title: str,
        subtitle: str,
        icon_name: str,
        add_text: Optional[str] = "Add Files",
        show_actions: bool = True,
    ) -> None:
        self.hdr_icon_lbl.configure(
            image=get_icon(icon_name, size=22, color=TEXT_PRIMARY, accent=ACCENT_TEXT)
        )
        self.hdr_title.configure(text=title)
        self.hdr_subtitle.configure(text=subtitle)
        if show_actions:
            self.lbl_count_badge.pack(side="left", padx=(0, 8))
            if add_text:
                self.btn_hdr_add.configure(text=add_text)
                self.btn_hdr_add.pack(side="left", padx=(0, 6))
            else:
                self.btn_hdr_add.pack_forget()
            self.btn_hdr_clear.pack(side="left")
        else:
            self.lbl_count_badge.pack_forget()
            self.btn_hdr_add.pack_forget()
            self.btn_hdr_clear.pack_forget()

    def _refresh_queue_display(self) -> None:
        count = len(self.file_queue) if self.current_mode != "WATERMARK" else len(self.watermark_frame.get_video_queue())
        unit = "video" if self.current_mode == "WATERMARK" else "item"
        self.lbl_count_badge.configure(text=f"{count} {unit}" if count == 1 else f"{count} {unit}s")

        if self.current_mode == "WATERMARK":
            return

        self.empty_hero_convert.grid_forget()
        self.empty_hero_download.grid_forget()
        self.empty_hero_ai.grid_forget()
        self.queue_list.grid_forget()

        if self.file_queue:
            self.queue_list.grid(row=0, column=0, sticky="nsew")
        else:
            if self.current_mode == "DOWNLOAD":
                self.empty_hero_download.grid(row=0, column=0, sticky="nsew")
            elif self.current_mode == "AI_TOOLS":
                self.empty_hero_ai.grid(row=0, column=0, sticky="nsew")
            else:
                self.empty_hero_convert.grid(row=0, column=0, sticky="nsew")

    def _on_header_add(self) -> None:
        if self.current_mode == "WATERMARK":
            self.watermark_frame.add_videos()
        else:
            self.add_files()

    def _on_header_clear(self) -> None:
        if self.current_mode == "WATERMARK":
            self.watermark_frame.clear_queue()
        else:
            self.clear_list()

    # ══════════════════════════════════════════════════════════════════
    #  Mode Switching
    # ══════════════════════════════════════════════════════════════════

    def _hide_right_dynamic_widgets(self) -> None:
        self.lbl_format.pack_forget()
        self.format_menu.pack_forget()
        self.lbl_quality.pack_forget()
        self.quality_menu.pack_forget()
        self.lbl_ai_action.pack_forget()
        self.ai_action_menu.pack_forget()
        self.lbl_wm_quality.pack_forget()
        self.wm_quality_menu.pack_forget()
        self.lbl_sample_rate.pack_forget()
        self.sample_rate_menu.pack_forget()
        self.lbl_channels.pack_forget()
        self.channels_menu.pack_forget()
        self.chk_normalize_audio.pack_forget()
        self.chk_stream_copy.pack_forget()
        self.chk_hw_accel.pack_forget()
        self.chk_save_source.pack_forget()
        self.chk_playlist.pack_forget()
        self.lbl_wm_suffix_hint.pack_forget()
        self.lbl_wm_status.grid_remove()
        self.completion_banner.grid_remove()

    def _hide_full_frames(self) -> None:
        self._hide_online_trimmer()
        for attr in ("cutter_frame", "subtitle_frame", "bg_frame", "vocal_frame", "watermark_frame", "viral_frame"):
            frame = getattr(self, attr, None)
            if frame is None:
                continue
            if hasattr(frame, "stop_audio"):
                frame.stop_audio()
            if hasattr(frame, "stop_playback"):
                frame.stop_playback()
            if frame.winfo_ismapped():
                frame.grid_remove()

        # Restore standard center container + right export card
        self.center_container.grid(row=0, column=1, padx=(18, 14), pady=18, sticky="nsew")
        self.queue_frame.grid(row=1, column=0, sticky="nsew")
        self.right_frame.grid(row=0, column=2, padx=(0, 18), pady=18, sticky="nsew")

    def _show_fullscreen_tool(self, frame) -> None:
        self._hide_full_frames()
        self.center_container.grid_remove()
        self.right_frame.grid_remove()
        frame.grid(row=0, column=1, columnspan=2, padx=18, pady=18, sticky="nsew")

    def _refresh_dest_chip(self, folder_path: str, default_label: str = "Source folder") -> None:
        if folder_path:
            name = os.path.basename(folder_path) or folder_path
            self.out_dir_label.configure(text=f" {name}", text_color=ACCENT_TEXT)
        else:
            self.out_dir_label.configure(text=f" {default_label}", text_color=TEXT_SECONDARY)

    def _switch_to_convert(self, category: str) -> None:
        self._hide_full_frames()

        if self.current_mode != "CONVERT":
            self.clear_list()
        self.current_mode = "CONVERT"
        self.current_convert_category = category
        self._set_active_nav("CONVERT")

        for k, btn in self._cat_buttons.items():
            btn.configure(
                fg_color=ACCENT_PRIMARY if k == category else "transparent",
                hover_color=ACCENT_HOVER if k == category else BG_CARD_HOVER,
                text_color=TEXT_PRIMARY if k == category else TEXT_SECONDARY,
            )

        self._update_header(
            title="Universal Converter",
            subtitle="Convert audio, video, images, and archives at high speed",
            icon_name=category.lower(),
            add_text="Add Files",
        )

        self.dl_toolbar.grid_remove()
        self.conv_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        self._hide_right_dynamic_widgets()
        self.lbl_format.pack(anchor="w", padx=12, pady=(0, 4), after=self.lbl_config_title)
        self.format_menu.pack(fill="x", padx=12, pady=(0, 6), after=self.lbl_format)

        if category == "AUDIO":
            self.lbl_sample_rate.pack(anchor="w", padx=12, pady=(4, 4), after=self.format_menu)
            self.sample_rate_menu.set(self.settings.get("sample_rate", "44100 Hz"))
            self.sample_rate_menu.pack(fill="x", padx=12, pady=(0, 6), after=self.lbl_sample_rate)
            self.lbl_channels.pack(anchor="w", padx=12, pady=(2, 4), after=self.sample_rate_menu)
            self.channels_menu.set(self.settings.get("channels", "Stereo"))
            self.channels_menu.pack(fill="x", padx=12, pady=(0, 6), after=self.lbl_channels)
            self.normalize_audio_var.set(bool(self.settings.get("normalize_audio", False)))
            self.chk_normalize_audio.pack(anchor="w", padx=12, pady=(2, 6), after=self.channels_menu)
        elif category == "VIDEO":
            self.stream_copy_var.set(bool(self.settings.get("fast_stream_copy", False)))
            self.chk_stream_copy.pack(anchor="w", padx=12, pady=(4, 4), after=self.format_menu)
            self.hw_accel_var.set(bool(self.settings.get("hardware_accel", True)))
            self.chk_hw_accel.pack(anchor="w", padx=12, pady=(0, 6), after=self.chk_stream_copy)

        self.chk_save_source.pack(anchor="w", padx=12, pady=(0, 6), before=self.path_chip)
        self.save_source_var.set(self.settings.get("save_in_source", True))
        self._refresh_dest_chip(self.settings.get("custom_output_dir", ""), "Source folder")

        new_values = self.formats.get(category, ["MP3"])
        self.format_menu.configure(values=new_values)
        self.format_menu.set(new_values[0])
        self.btn_start.configure(text="CONVERT NOW")
        self.speed_label.configure(text="")
        self._refresh_queue_display()

    def _switch_to_download(self) -> None:
        self._hide_full_frames()

        if self.current_mode != "DOWNLOAD":
            self.clear_list()
        self.current_mode = "DOWNLOAD"
        self._set_active_nav("DOWNLOAD")
        self._update_header(
            title="Media Downloader",
            subtitle="Save videos, audio, and thumbnails from YouTube, TikTok, Instagram, Twitch, Kick & X",
            icon_name="download",
            add_text=None,
        )

        self.conv_toolbar.grid_remove()
        self.dl_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        self._hide_right_dynamic_widgets()
        self.lbl_format.pack(anchor="w", padx=12, pady=(0, 4), after=self.lbl_config_title)
        self.format_menu.configure(values=self.download_formats)
        self.format_menu.set(self.settings.get("download_format", "MP4").upper())
        self.format_menu.pack(fill="x", padx=12, pady=(0, 10), after=self.lbl_format)

        self.lbl_quality.pack(anchor="w", padx=12, pady=(0, 4), after=self.format_menu)
        self.quality_menu.set(self.settings.get("download_quality", "Best Available"))
        self.quality_menu.pack(fill="x", padx=12, pady=(0, 6), after=self.lbl_quality)

        self.chk_playlist.pack(anchor="w", padx=12, pady=(0, 6), before=self.path_chip)
        self.playlist_var.set(not self.settings.get("noplaylist", True))
        self.stream_copy_var.set(bool(self.settings.get("fast_stream_copy", False)))
        self.chk_stream_copy.pack(anchor="w", padx=12, pady=(2, 4), after=self.quality_menu)
        self.hw_accel_var.set(bool(self.settings.get("hardware_accel", True)))
        self.chk_hw_accel.pack(anchor="w", padx=12, pady=(0, 6), after=self.chk_stream_copy)
        self._on_format_change(self.format_menu.get())

        out_dir = self.settings.get("download_output_dir", os.path.expanduser("~\\Downloads"))
        self._refresh_dest_chip(out_dir, "Downloads")
        self.btn_start.configure(text="DOWNLOAD")
        self.speed_label.configure(text="")
        self._refresh_queue_display()

    def _switch_to_aitools(self) -> None:
        self._hide_full_frames()

        if self.current_mode != "AI_TOOLS":
            self.clear_list()
        self.current_mode = "AI_TOOLS"
        self._set_active_nav("AI_TOOLS")
        self._update_header(
            title="AI Batch Queue",
            subtitle="Run automated AI background removal, subtitles, or vocal isolation on multiple files",
            icon_name="ai_tools",
            add_text="Add Files",
        )

        self.dl_toolbar.grid_remove()
        self.conv_toolbar.grid_remove()

        self._hide_right_dynamic_widgets()
        self.lbl_ai_action.pack(anchor="w", padx=12, pady=(0, 4), after=self.lbl_config_title)
        self.ai_action_menu.pack(fill="x", padx=12, pady=(0, 6), after=self.lbl_ai_action)
        self._refresh_dest_chip(self.settings.get("custom_output_dir", ""), "Source folder")

        self.btn_start.configure(text="START AI PROCESS")
        self.speed_label.configure(text="")
        self._refresh_queue_display()

    def _switch_to_watermark(self) -> None:
        if self.current_mode == "WATERMARK":
            return

        self._hide_full_frames()
        self.current_mode = "WATERMARK"
        self._set_active_nav("WATERMARK")

        self._update_header(
            title="Watermark Studio",
            subtitle="Design, preview, and batch-apply custom signatures or logos to your videos",
            icon_name="watermark",
            add_text="Add Videos",
        )

        wm_frame = self._get_watermark_frame()
        self.queue_frame.grid_remove()
        wm_frame.grid(row=1, column=0, sticky="nsew")

        self._hide_right_dynamic_widgets()
        self.lbl_format.pack(anchor="w", padx=12, pady=(0, 4), after=self.lbl_config_title)
        self.format_menu.configure(values=self.watermark_formats)
        self.format_menu.set(self.settings.get("watermark_format", "Original (Same as input)"))
        self.format_menu.pack(fill="x", padx=12, pady=(0, 10), after=self.lbl_format)

        self.lbl_wm_quality.pack(anchor="w", padx=12, pady=(0, 4), after=self.format_menu)
        self.wm_quality_menu.set(self.settings.get("watermark_quality", "High (Visually Lossless / CRF 18)"))
        self.wm_quality_menu.pack(fill="x", padx=12, pady=(0, 6), after=self.lbl_wm_quality)

        self.hw_accel_var.set(bool(self.settings.get("hardware_accel", True)))
        self.chk_hw_accel.pack(anchor="w", padx=12, pady=(0, 6), after=self.wm_quality_menu)

        self.chk_save_source.pack(anchor="w", padx=12, pady=(0, 4), before=self.path_chip)
        self.save_source_var.set(self.settings.get("watermark_save_in_source", True))
        self.lbl_wm_suffix_hint.pack(anchor="w", padx=14, pady=(0, 6), before=self.path_chip)

        self._refresh_dest_chip(self.settings.get("watermark_output_dir", ""), "Source folder")
        self.lbl_wm_status.configure(text="Ready", text_color=TEXT_SECONDARY)
        self.lbl_wm_status.grid(row=1, column=0, sticky="ew", padx=14, pady=(2, 2))

        if self._last_watermark_output_dir and os.path.isdir(self._last_watermark_output_dir):
            self.completion_banner.grid(row=0, column=0, sticky="ew", padx=14, pady=(6, 4))

        self._on_watermark_queue_changed(len(wm_frame.get_video_queue()))

    def _switch_to_viral_clipper(self) -> None:
        if self.current_mode == "VIRAL_CLIPPER":
            return
        self.current_mode = "VIRAL_CLIPPER"
        self._set_active_nav("VIRAL_CLIPPER")
        self._show_fullscreen_tool(self._get_viral_frame())

    def _toggle_online_trimmer(self) -> None:
        if hasattr(self, "online_trimmer"):
            if not self.online_trimmer.winfo_ismapped():
                self._show_online_trimmer()
            else:
                url = self.url_entry.get().strip()
                if url and (not self.online_trimmer.stream_info or self.online_trimmer.stream_info.url != url):
                    self.online_trimmer.load_url(url)
                else:
                    self._hide_online_trimmer()

    def _show_online_trimmer(self) -> None:
        if hasattr(self, "online_trimmer"):
            self.online_trimmer.grid(row=1, column=0, sticky="ew", pady=(0, 10))
            if hasattr(self, "btn_dl_trim"):
                self.btn_dl_trim.configure(fg_color=ACCENT_PRIMARY, text_color=TEXT_PRIMARY)
            url = self.url_entry.get().strip()
            if url:
                self.online_trimmer.load_url(url)

    def _hide_online_trimmer(self) -> None:
        if hasattr(self, "online_trimmer"):
            if hasattr(self.online_trimmer, "stop_playback"):
                self.online_trimmer.stop_playback()
            if self.online_trimmer.winfo_ismapped():
                self.online_trimmer.grid_remove()
        if hasattr(self, "btn_dl_trim"):
            self.btn_dl_trim.configure(fg_color=BG_CARD, text_color=TEXT_PRIMARY)

    def _on_download_trimmed_segment(
        self, url: str, start_sec: float, end_sec: float, stream_info: StreamMetadata
    ) -> None:
        if hasattr(self, "online_trimmer") and hasattr(self.online_trimmer, "stop_playback"):
            self.online_trimmer.stop_playback()

        out_dir = self.settings.get("download_output_dir", os.path.expanduser("~\\Downloads"))
        format_choice = self.format_menu.get() if hasattr(self, "format_menu") else "MP4"
        quality_choice = self.quality_menu.get() if hasattr(self, "quality_menu") else "Best Available"
        dur_str = format_seconds(end_sec - start_sec)
        title = stream_info.title if (stream_info and stream_info.title) else url
        subtitle = f"Trimmed ({format_seconds(start_sec)} - {format_seconds(end_sec)} • {dur_str})"

        idx = len(self.file_queue)
        fake_item = f"{url}#[{start_sec:.1f}-{end_sec:.1f}]"
        self.file_queue.append(fake_item)
        self.queue_list.add_card(
            title=title,
            subtitle=subtitle,
            badge=f"TRIM • {int(end_sec - start_sec)}s",
        )
        self._refresh_queue_display()

        self.btn_start.grid_remove()
        self.btn_cancel.grid(row=3, column=0, padx=14, pady=(0, 14), sticky="ew")
        self.total_progress.grid(row=2, column=0, padx=14, pady=(6, 8), sticky="ew")
        self.total_progress.set(0)
        self.speed_label.configure(text=f"Downloading segment ({dur_str})…")
        self.update_tree(idx, "Downloading segment…")

        import threading

        def _worker():
            def _prog(pct: int, speed: str):
                self.after(0, lambda p=pct, s=speed: (
                    self.update_tree(idx, f"{p}% • {s}" if s else f"{p}%"),
                    self.total_progress.set(p / 100.0),
                    self.speed_label.configure(text=f"{p}% • {s}" if s else f"{p}%"),
                ))

            try:
                dl_settings = {
                    **self.settings,
                    "fast_stream_copy": bool(self.stream_copy_var.get()),
                    "hardware_accel": bool(self.hw_accel_var.get()),
                }
                out_path = download_trimmed_segment(
                    url=url,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    settings=dl_settings,
                    stream_info=stream_info,
                    output_dir=out_dir,
                    format_choice=format_choice,
                    quality_choice=quality_choice,
                    progress_callback=_prog,
                )
                self._last_output_dir = out_dir
                self.after(0, lambda p=out_path: (
                    self.update_tree(idx, "✓ Completed"),
                    self.total_progress.set(1.0),
                    self._on_work_complete(),
                ))
            except Exception as ex:
                log.error("Trimmed segment download error: %s", ex)
                self.after(0, lambda e=str(ex): (
                    self.update_tree(idx, f"✗ {e[:25]}"),
                    self._restore_buttons(),
                    messagebox.showerror("Download Error", f"Segment download failed:\n{e}"),
                ))

        threading.Thread(target=_worker, daemon=True).start()

    def _switch_to_cutter(self) -> None:
        if self.current_mode == "CUT":
            return
        self.current_mode = "CUT"
        self._set_active_nav("CUT")
        self._show_fullscreen_tool(self._get_cutter_frame())

    def _switch_to_subtitles(self) -> None:
        if self.current_mode == "SUBTITLES":
            return
        self.current_mode = "SUBTITLES"
        self._set_active_nav("SUBTITLES")
        self._show_fullscreen_tool(self._get_subtitle_frame())

    def _switch_to_bg_remover(self) -> None:
        if self.current_mode == "BG_REMOVER":
            return
        self.current_mode = "BG_REMOVER"
        self._set_active_nav("BG_REMOVER")
        self._show_fullscreen_tool(self._get_bg_frame())

    def _switch_to_vocal_isolator(self) -> None:
        if self.current_mode == "VOCAL_ISOLATOR":
            return
        self.current_mode = "VOCAL_ISOLATOR"
        self._set_active_nav("VOCAL_ISOLATOR")
        self._show_fullscreen_tool(self._get_vocal_frame())

    def _on_watermark_queue_changed(self, count: int) -> None:
        if self.current_mode == "WATERMARK":
            self._refresh_queue_display()
            if not self.btn_cancel.winfo_ismapped():
                self.btn_start.configure(text="EXPORT BATCH" if count >= 2 else "EXPORT VIDEO")

    def _on_format_change(self, choice: str) -> None:
        if self.current_mode == "DOWNLOAD":
            if choice.upper() in ["JPG", "PNG", "WEBP"]:
                self.lbl_quality.pack_forget()
                self.quality_menu.pack_forget()
                self.chk_stream_copy.pack_forget()
                self.chk_hw_accel.pack_forget()
            else:
                self.lbl_quality.pack(anchor="w", padx=12, pady=(0, 4), after=self.format_menu)
                self.quality_menu.pack(fill="x", padx=12, pady=(0, 6), after=self.lbl_quality)
                self.chk_stream_copy.pack(anchor="w", padx=12, pady=(2, 4), after=self.quality_menu)
                self.chk_hw_accel.pack(anchor="w", padx=12, pady=(0, 6), after=self.chk_stream_copy)

    # ══════════════════════════════════════════════════════════════════
    #  Output Folder
    # ══════════════════════════════════════════════════════════════════

    def _select_output_folder(self) -> None:
        folder = filedialog.askdirectory()
        if folder:
            if self.current_mode == "CONVERT":
                key = "custom_output_dir"
            elif self.current_mode == "WATERMARK":
                key = "watermark_output_dir"
            else:
                key = "download_output_dir"
            self.settings[key] = folder
            self._refresh_dest_chip(folder)
            save_settings(self.settings)

    def _open_output_folder(self) -> None:
        target = self._last_watermark_output_dir if self.current_mode == "WATERMARK" else self._last_output_dir
        if not target or not os.path.isdir(target):
            return
        try:
            if os.name == "nt":
                os.startfile(target)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except Exception as exc:
            log.warning("Could not open output folder %s: %s", target, exc)

    # ══════════════════════════════════════════════════════════════════
    #  Drag & Drop
    # ══════════════════════════════════════════════════════════════════

    def _register_dnd_targets(self, targets: list) -> None:
        if not _HAS_DND:
            return

        def on_drop(e):
            for f in self.tk.splitlist(e.data):
                self._add_to_queue(f)

        for w in targets:
            if w and hasattr(w, "drop_target_register"):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", on_drop)
                except Exception as ex:
                    log.debug("Failed registering drop target on %s: %s", w, ex)

    def _enable_drag_and_drop(self) -> None:
        self._register_dnd_targets([
            self,
            self.center_container,
            self.queue_frame,
            self.queue_body,
            self.queue_list,
            self.empty_hero_convert,
            self.empty_hero_download,
            self.empty_hero_ai,
            getattr(self, "online_trimmer", None),
        ])

    # ══════════════════════════════════════════════════════════════════
    #  Queue Management (Modern File Cards)
    # ══════════════════════════════════════════════════════════════════

    def _add_to_queue(self, filepath: str) -> None:
        filepath = filepath.strip("{}").strip('"').strip("'")
        if not filepath:
            return

        if self.current_mode == "DOWNLOAD":
            if is_valid_url(filepath) and filepath not in self.file_queue:
                self.file_queue.append(filepath)
                label = platform_display_name(filepath)
                self.queue_list.add_card(
                    title=filepath,
                    subtitle=f"{label} • Ready to download",
                    badge=label[:5].upper(),
                )
                self._refresh_queue_display()
            return

        if self.current_mode == "CUT":
            self._get_cutter_frame().load_audio_from_path(filepath)
            return

        if self.current_mode == "SUBTITLES":
            self._get_subtitle_frame().load_from_path(filepath)
            return

        if self.current_mode == "BG_REMOVER":
            self._get_bg_frame().load_file_from_path(filepath)
            return

        if self.current_mode == "VOCAL_ISOLATOR":
            self._get_vocal_frame().load_file_from_path(filepath)
            return

        if self.current_mode == "WATERMARK":
            self._get_watermark_frame().add_path(filepath)
            return

        if self.current_mode == "VIRAL_CLIPPER":
            self._get_viral_frame().load_source(filepath)
            return

        if filepath not in self.file_queue:
            self.file_queue.append(filepath)
            ext = os.path.splitext(filepath)[1].lstrip(".").upper() or "FILE"
            size_txt = ""
            if os.path.isfile(filepath):
                mb = os.path.getsize(filepath) / (1024 * 1024)
                size_txt = f" • {mb:.1f} MB"
            self.queue_list.add_card(
                title=os.path.basename(filepath),
                subtitle=f"{ext} source{size_txt}",
                badge=ext,
            )
            self._refresh_queue_display()

    def add_files(self) -> None:
        files = filedialog.askopenfilenames()
        for f in files:
            self._add_to_queue(f)

    def add_url(self) -> None:
        url = self.url_entry.get().strip()
        if not url:
            return
        if not is_valid_url(url):
            messagebox.showwarning("Invalid URL", f"The URL doesn't look valid:\n{url}")
            return
        if url not in self.file_queue:
            self.file_queue.append(url)
            label = platform_display_name(url)
            self.queue_list.add_card(
                title=url,
                subtitle=f"{label} • Ready to download",
                badge=label[:5].upper(),
            )
            self.url_entry.delete(0, "end")
            self._refresh_queue_display()

    def _remove_at_index(self, index: int) -> None:
        if 0 <= index < len(self.file_queue):
            self.file_queue.pop(index)
            self.queue_list.remove_at(index)
            self._refresh_queue_display()

    def clear_list(self) -> None:
        self.file_queue.clear()
        self.queue_list.clear()
        self.speed_label.configure(text="")
        self._refresh_queue_display()

    # ══════════════════════════════════════════════════════════════════
    #  Card Status Helpers
    # ══════════════════════════════════════════════════════════════════

    def _load_ui_settings(self) -> None:
        self._switch_to_convert("AUDIO")
        self.format_menu.set(self.settings.get("output_format", "MP3").upper())

    def update_tree(self, index: int, value: str) -> None:
        """Thread-safe card status updater (retains legacy method name for workers)."""
        prog: Optional[float] = None
        m = re.search(r"(\d+)%", str(value))
        if m:
            prog = int(m.group(1)) / 100.0
        self.after(0, lambda: self.queue_list.update_status(index, value, progress=prog))

    def _update_speed(self, text: str) -> None:
        self.after(0, lambda: self.speed_label.configure(text=text))

    # ══════════════════════════════════════════════════════════════════
    #  Start / Cancel
    # ══════════════════════════════════════════════════════════════════

    def start_action(self) -> None:
        if self.current_mode == "WATERMARK":
            self._start_watermark_export()
            return

        if not self.file_queue:
            messagebox.showinfo("Nothing to do", "Add files or URLs to the queue first.")
            return

        self.completion_banner.grid_remove()

        if self.current_mode == "DOWNLOAD":
            callbacks = {
                "on_file_start": lambda idx, f: self.update_tree(idx, "Downloading…"),
                "on_progress": self._on_download_progress,
                "on_file_done": lambda idx, title: self.update_tree(idx, "✓ Completed"),
                "on_file_error": lambda idx, err: self.update_tree(idx, f"✗ {err}"),
                "on_total_progress": lambda p: self.after(0, lambda val=p: self.total_progress.set(val / 100.0)),
                "on_complete": lambda: self.after(0, self._on_work_complete),
            }
        elif self.current_mode == "AI_TOOLS":
            callbacks = {
                "on_file_start": lambda idx, f: self.update_tree(idx, "Processing AI…"),
                "on_progress": lambda idx, p: self.update_tree(idx, "Processing…"),
                "on_file_done": lambda idx, msg: self.update_tree(idx, "✓ Completed"),
                "on_file_error": lambda idx, err: self.update_tree(idx, f"✗ {err}"),
                "on_total_progress": lambda p: self.after(0, lambda val=p: self.total_progress.set(val / 100.0)),
                "on_complete": lambda: self.after(0, self._on_work_complete),
            }
        else:
            callbacks = {
                "on_file_start": lambda idx, f: self.update_tree(idx, "Converting…"),
                "on_progress": lambda idx, p: self.update_tree(idx, f"{p}%"),
                "on_file_done": lambda idx, msg: self.update_tree(idx, "✓ Completed"),
                "on_file_error": lambda idx, err: self.update_tree(idx, f"✗ {err}"),
                "on_total_progress": lambda p: self.after(0, lambda val=p: self.total_progress.set(val / 100.0)),
                "on_complete": lambda: self.after(0, self._on_work_complete),
            }

        self.btn_start.grid_remove()
        self.btn_cancel.grid(row=3, column=0, padx=14, pady=(0, 14), sticky="ew")
        self.total_progress.grid(row=2, column=0, padx=14, pady=(6, 8), sticky="ew")
        self.total_progress.set(0)
        self.speed_label.configure(text="Starting…")

        if self.current_mode == "CONVERT":
            from core.worker import ConversionWorker
            self.settings.update({
                "output_format": self.format_menu.get().lower(),
                "sample_rate": self.sample_rate_menu.get(),
                "channels": self.channels_menu.get(),
                "normalize_audio": bool(self.normalize_audio_var.get()),
                "fast_stream_copy": bool(self.stream_copy_var.get()),
                "hardware_accel": bool(self.hw_accel_var.get()),
                "save_in_source": self.save_source_var.get(),
            })
            save_settings(self.settings)
            self._last_output_dir = (
                os.path.dirname(self.file_queue[0])
                if self.save_source_var.get()
                else self.settings.get("custom_output_dir", "")
            )
            self.worker = ConversionWorker(self.file_queue, self.settings, callbacks)

        elif self.current_mode == "AI_TOOLS":
            self._last_output_dir = os.path.dirname(self.file_queue[0])
            self.worker = AIWorker(self.file_queue, self.ai_action_menu.get(), callbacks, settings=self.settings)

        else:
            from core.download_worker import DownloadWorker
            self.settings.update({
                "download_format": self.format_menu.get().upper(),
                "download_quality": self.quality_menu.get(),
                "fast_stream_copy": bool(self.stream_copy_var.get()),
                "hardware_accel": bool(self.hw_accel_var.get()),
                "noplaylist": not self.playlist_var.get(),
            })
            save_settings(self.settings)
            self._last_output_dir = self.settings.get("download_output_dir", os.path.expanduser("~\\Downloads"))
            self.worker = DownloadWorker(self.file_queue, self.settings, callbacks)

        self.worker.start()
        log.info("Worker started — mode=%s, items=%d", self.current_mode, len(self.file_queue))

    def _start_watermark_export(self) -> None:
        wm_frame = self._get_watermark_frame()
        videos = wm_frame.get_video_queue()
        if not videos:
            messagebox.showinfo("No Videos", "Add at least one video to export.")
            return

        wm_cfg = wm_frame.get_watermark_config()
        if wm_cfg.get("type") == "image":
            img_path = (wm_cfg.get("image_path") or "").strip()
            if not img_path or not os.path.isfile(img_path):
                messagebox.showwarning("Missing Logo", "Please upload a watermark logo/image first.")
                return
        elif not (wm_cfg.get("text") or "").strip():
            messagebox.showwarning("Empty Text", "Please enter watermark text before exporting.")
            return

        wm_frame.stop_playback()
        wm_frame.set_export_locked(True)
        self.completion_banner.grid_remove()

        export_settings = {
            "format": self.format_menu.get(),
            "quality": self.wm_quality_menu.get(),
            "save_in_source": self.save_source_var.get(),
            "custom_output_dir": self.settings.get("watermark_output_dir", ""),
            "hardware_accel": bool(self.hw_accel_var.get()),
        }
        self.settings.update({
            "watermark_format": export_settings["format"],
            "watermark_quality": export_settings["quality"],
            "watermark_save_in_source": export_settings["save_in_source"],
            "hardware_accel": export_settings["hardware_accel"],
        })
        save_settings(self.settings)

        total_count = len(videos)
        for i in range(total_count):
            self.watermark_frame.update_row_status(i, "Pending")

        def _on_start(idx: int, _fp: str) -> None:
            self.watermark_frame.update_row_status(idx, "Rendering…", progress=0.0)
            self.after(
                0,
                lambda i=idx: self.lbl_wm_status.configure(
                    text=f"Rendering {i + 1}/{total_count}…", text_color=TEXT_PRIMARY
                ),
            )

        def _on_prog(idx: int, pct: int) -> None:
            self.watermark_frame.update_row_status(idx, f"{pct}%", progress=pct / 100.0)
            self.after(
                0,
                lambda i=idx, p=pct: self.lbl_wm_status.configure(
                    text=f"Rendering {i + 1}/{total_count} ({p}%)", text_color=TEXT_PRIMARY
                ),
            )

        def _on_done(idx: int, _out_path: str) -> None:
            self.watermark_frame.update_row_status(idx, "✓ Completed", progress=1.0)

        def _on_err(idx: int, err: str) -> None:
            short = err if len(err) <= 24 else err[:21] + "…"
            self.watermark_frame.update_row_status(idx, f"✗ {short}")

        callbacks = {
            "on_file_start": _on_start,
            "on_progress": _on_prog,
            "on_file_done": _on_done,
            "on_file_error": _on_err,
            "on_total_progress": lambda p: self.after(0, lambda val=p: self.total_progress.set(val / 100.0)),
            "on_complete": lambda summary: self.after(0, lambda s=summary: self._on_watermark_complete(s)),
        }

        self.btn_start.grid_remove()
        self.btn_cancel.grid(row=3, column=0, padx=14, pady=(0, 14), sticky="ew")
        self.total_progress.grid(row=2, column=0, padx=14, pady=(6, 8), sticky="ew")
        self.total_progress.set(0)
        self.lbl_wm_status.configure(text="Starting export…", text_color=TEXT_PRIMARY)

        from core.watermark_worker import WatermarkWorker
        self.worker = WatermarkWorker(videos, wm_cfg, export_settings, callbacks)
        self.worker.start()
        log.info("WatermarkWorker started — items=%d", total_count)

    def _on_watermark_complete(self, summary: dict) -> None:
        self.watermark_frame.set_export_locked(False)
        self._restore_buttons()
        succeeded = summary.get("succeeded", 0)
        failed = summary.get("failed", 0)
        dirs = summary.get("output_dirs") or []
        if dirs:
            self._last_watermark_output_dir = dirs[0]
            if self.current_mode == "WATERMARK":
                self.completion_banner.grid(row=0, column=0, sticky="ew", padx=14, pady=(6, 4))

        if failed == 0:
            self.lbl_wm_status.configure(
                text=f"✓ Exported {succeeded} video(s)", text_color=STATUS_SUCCESS
            )
            messagebox.showinfo("Export Complete", f"Successfully exported {succeeded} watermarked video(s)!")
        else:
            self.lbl_wm_status.configure(
                text=f"Done: {succeeded} ok, {failed} failed", text_color=STATUS_ERROR
            )
            messagebox.showwarning(
                "Export Finished with Errors",
                f"Exported {succeeded} video(s), {failed} failed. Check queue status.",
            )

    def _on_download_progress(self, index: int, data: dict) -> None:
        percent = data.get("percent", 0)
        speed = data.get("speed", "")
        eta = data.get("eta", "")
        status = data.get("status", "downloading")

        if status == "processing":
            self.update_tree(index, "Merging…")
            self._update_speed("Merging streams…")
        else:
            display = f"{percent}%"
            if speed:
                display += f" • {speed}"
            self.update_tree(index, display)
            speed_text = speed if speed else ""
            if eta and eta != "—":
                speed_text += f"  ETA: {eta}"
            self._update_speed(speed_text)

    def _cancel_action(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            log.info("Cancel requested by user.")
        if self.current_mode == "WATERMARK":
            self.watermark_frame.set_export_locked(False)
            self.lbl_wm_status.configure(text="Cancelled", text_color=STATUS_ERROR)
        self._restore_buttons()
        self.speed_label.configure(text="Cancelled")

    def _on_work_complete(self) -> None:
        self._restore_buttons()
        self.speed_label.configure(text="Complete!")
        if self._last_output_dir and os.path.isdir(self._last_output_dir):
            self.completion_banner.grid(row=0, column=0, sticky="ew", padx=14, pady=(6, 4))
        messagebox.showinfo("Success", "All tasks finished!")

    def _restore_buttons(self) -> None:
        self.total_progress.grid_remove()
        self.btn_cancel.grid_remove()
        if self.current_mode == "CONVERT":
            text = "CONVERT NOW"
        elif self.current_mode == "AI_TOOLS":
            text = "START AI PROCESS"
        elif self.current_mode == "WATERMARK":
            wm = getattr(self, "watermark_frame", None)
            cnt = len(wm.get_video_queue()) if wm else 0
            text = "EXPORT BATCH" if cnt >= 2 else "EXPORT VIDEO"
        else:
            text = "DOWNLOAD"
        self.btn_start.configure(state="normal", text=text)
        self.btn_start.grid(row=3, column=0, padx=14, pady=(0, 14), sticky="ew")

    def _on_close(self) -> None:
        try:
            for attr in ("watermark_frame", "viral_frame", "cutter_frame", "subtitle_frame", "bg_frame", "vocal_frame"):
                frame = getattr(self, attr, None)
                if frame is None:
                    continue
                if hasattr(frame, "cleanup"):
                    frame.cleanup()
                elif hasattr(frame, "stop_playback"):
                    frame.stop_playback()
                elif hasattr(frame, "stop_audio"):
                    frame.stop_audio()
            if getattr(self, "online_trimmer", None) and hasattr(self.online_trimmer, "stop_playback"):
                self.online_trimmer.stop_playback()
            if self.worker is not None and hasattr(self.worker, "cancel"):
                self.worker.cancel()
        finally:
            self.destroy()
