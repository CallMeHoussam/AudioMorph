"""
Online Stream Trimmer Widget — live interactive stream player and precision cutter
embedded inside Media Downloader. Provides 2-column control panel & 16:9 cinema video
canvas with smooth 24fps frame streaming, instant Start/End capture, interactive timeline,
and verified cut previews.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from core.online_trimmer import (
    OnlineStreamPlayer,
    StreamMetadata,
    download_trimmed_segment,
    extract_remote_frame,
    fetch_remote_thumbnail,
    fetch_stream_info,
    format_seconds,
    format_seconds_tenths,
    parse_timestamp_str,
)
from gui.icons import get_icon
from gui.theme import (
    ACCENT_HOVER,
    ACCENT_PRIMARY,
    ACCENT_SOFT_BG,
    ACCENT_TEXT,
    BG_CARD,
    BG_CARD_HOVER,
    BG_INPUT,
    BG_PANEL,
    BORDER_SUBTLE,
    FONT_FAMILY,
    FONT_MONO,
    RADIUS_BTN,
    RADIUS_CARD,
    STATUS_SUCCESS,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from utils.logger import get_logger

log = get_logger(__name__)


class OnlineTrimmerDrawer(ctk.CTkFrame):
    """
    Live interactive stream player and precision segment cutter.
    Features a 2-column layout: Left Controls (live digital tracker, steppers,
    Start/End captures, preview cut, download) and Right Cinema Video Player
    (smooth 24fps streaming canvas, interactive scrub timeline with range markers).
    """

    def __init__(
        self,
        master,
        on_download_segment: Optional[Callable[[str, float, float, StreamMetadata], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
        get_url_fn: Optional[Callable[[], str]] = None,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=BG_PANEL,
            corner_radius=RADIUS_CARD,
            border_width=1,
            border_color=BORDER_SUBTLE,
            **kwargs,
        )
        self.on_download_segment = on_download_segment
        self.on_close = on_close
        self.get_url_fn = get_url_fn

        self.stream_info: Optional[StreamMetadata] = None
        self.start_sec: float = 0.0
        self.end_sec: float = 60.0
        self.total_duration: float = 120.0
        self.current_time_sec: float = 0.0
        self.audio_muted: bool = False
        self._is_scrubbing: bool = False

        self.canvas_w: int = 560
        self.canvas_h: int = 315

        self._preview_photo: Optional[ImageTk.PhotoImage] = None
        self._debounce_timer: Optional[threading.Timer] = None
        self._ui_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._is_loading = False

        # Live Real-Time Stream Player Engine
        self.player = OnlineStreamPlayer(
            width=self.canvas_w,
            height=self.canvas_h,
            fps=24,
            on_frame=self._queue_player_frame,
            on_state_change=self._queue_player_state_change,
            on_cut_finished=self._queue_cut_finished,
        )

        self._build_ui()
        self._poll_ui_queue()

    def _poll_ui_queue(self) -> None:
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception as ex:
                    log.debug("UI queue dispatch error: %s", ex)
        except queue.Empty:
            pass
        self.after(40, self._poll_ui_queue)

    def _queue_player_frame(self, img: Image.Image, timestamp: float) -> None:
        self._ui_queue.put(lambda: self._on_player_frame(img, timestamp))

    def _queue_player_state_change(self, is_playing: bool) -> None:
        self._ui_queue.put(lambda: self._on_player_state_change(is_playing))

    def _queue_cut_finished(self) -> None:
        self._ui_queue.put(self._on_cut_preview_finished)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=0, minsize=265)  # Left controls column
        self.grid_columnconfigure(1, weight=1)               # Right video cinema stage
        self.grid_rowconfigure(0, weight=1)

        # ═════════════════════════════════════════════════════════════
        # ── LEFT PANEL: Controls, Stepper, Captures & Actions ─────────
        # ═════════════════════════════════════════════════════════════
        controls_col = ctk.CTkFrame(self, width=265, fg_color="transparent")
        controls_col.grid(row=0, column=0, padx=(14, 10), pady=12, sticky="nsew")

        # Top Tag / Section Label
        header_row = ctk.CTkFrame(controls_col, fg_color="transparent")
        header_row.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            header_row,
            text=" STREAM TRIMMER",
            image=get_icon("trim", size=14, color=TEXT_PRIMARY, accent=ACCENT_TEXT),
            compound="left",
            font=(FONT_FAMILY, 11, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        # ── 1. CURRENT TIME Live Tracker & Steppers ───────────────────
        ctk.CTkLabel(
            controls_col,
            text="CURRENT TIME",
            font=(FONT_FAMILY, 9, "bold"),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).pack(fill="x", pady=(2, 2))

        time_box_row = ctk.CTkFrame(controls_col, fg_color="transparent")
        time_box_row.pack(fill="x", pady=(0, 8))

        ctk.CTkButton(
            time_box_row,
            text="◄ -1s",
            width=44,
            height=32,
            font=(FONT_FAMILY, 10, "bold"),
            fg_color=BG_CARD,
            hover_color=BG_CARD_HOVER,
            border_width=1,
            border_color=BORDER_SUBTLE,
            command=lambda: self._step_time(-1.0),
        ).pack(side="left", padx=(0, 4))

        self.lbl_current_time = ctk.CTkLabel(
            time_box_row,
            text="00:00:00.0",
            font=(FONT_MONO, 14, "bold"),
            text_color=ACCENT_TEXT,
            fg_color=BG_CARD,
            corner_radius=6,
            height=32,
        )
        self.lbl_current_time.pack(side="left", fill="x", expand=True, padx=2)

        ctk.CTkButton(
            time_box_row,
            text="+1s ►",
            width=44,
            height=32,
            font=(FONT_FAMILY, 10, "bold"),
            fg_color=BG_CARD,
            hover_color=BG_CARD_HOVER,
            border_width=1,
            border_color=BORDER_SUBTLE,
            command=lambda: self._step_time(1.0),
        ).pack(side="right", padx=(4, 0))

        # ── 2. Instant Capture Buttons ([ Start ] and [ End ]) ─────────
        capture_row = ctk.CTkFrame(controls_col, fg_color="transparent")
        capture_row.pack(fill="x", pady=(0, 10))

        self.btn_capture_start = ctk.CTkButton(
            capture_row,
            text="[ Set Start",
            height=32,
            font=(FONT_FAMILY, 11, "bold"),
            fg_color=BG_CARD,
            hover_color=ACCENT_PRIMARY,
            border_width=1,
            border_color=BORDER_SUBTLE,
            command=self._capture_start_time,
        )
        self.btn_capture_start.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_capture_end = ctk.CTkButton(
            capture_row,
            text="Set End ]",
            height=32,
            font=(FONT_FAMILY, 11, "bold"),
            fg_color=BG_CARD,
            hover_color=ACCENT_PRIMARY,
            border_width=1,
            border_color=BORDER_SUBTLE,
            command=self._capture_end_time,
        )
        self.btn_capture_end.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # ── 3. Editable Timestamp Inputs & Live Duration ──────────────
        # Start Input
        start_row = ctk.CTkFrame(controls_col, fg_color="transparent")
        start_row.pack(fill="x", pady=2)
        ctk.CTkLabel(
            start_row,
            text="Start:",
            font=(FONT_FAMILY, 10, "bold"),
            text_color=TEXT_SECONDARY,
            width=42,
            anchor="w",
        ).pack(side="left")

        self.entry_start = ctk.CTkEntry(
            start_row,
            height=28,
            font=(FONT_MONO, 11),
            fg_color=BG_CARD,
            border_color=BORDER_SUBTLE,
        )
        self.entry_start.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.entry_start.insert(0, "00:00:00.0")
        self.entry_start.bind("<Return>", self._on_start_entry_changed)
        self.entry_start.bind("<FocusOut>", self._on_start_entry_changed)

        ctk.CTkButton(
            start_row,
            text="Seek",
            width=42,
            height=28,
            font=(FONT_FAMILY, 10, "bold"),
            fg_color=BG_CARD,
            hover_color=ACCENT_PRIMARY,
            command=lambda: self._jump_to(self.start_sec),
        ).pack(side="right")

        # End Input
        end_row = ctk.CTkFrame(controls_col, fg_color="transparent")
        end_row.pack(fill="x", pady=2)
        ctk.CTkLabel(
            end_row,
            text="End:",
            font=(FONT_FAMILY, 10, "bold"),
            text_color=TEXT_SECONDARY,
            width=42,
            anchor="w",
        ).pack(side="left")

        self.entry_end = ctk.CTkEntry(
            end_row,
            height=28,
            font=(FONT_MONO, 11),
            fg_color=BG_CARD,
            border_color=BORDER_SUBTLE,
        )
        self.entry_end.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.entry_end.insert(0, "00:01:00.0")
        self.entry_end.bind("<Return>", self._on_end_entry_changed)
        self.entry_end.bind("<FocusOut>", self._on_end_entry_changed)

        ctk.CTkButton(
            end_row,
            text="Seek",
            width=42,
            height=28,
            font=(FONT_FAMILY, 10, "bold"),
            fg_color=BG_CARD,
            hover_color=ACCENT_PRIMARY,
            command=lambda: self._jump_to(self.end_sec),
        ).pack(side="right")

        # Duration Readout
        self.lbl_duration_pill = ctk.CTkLabel(
            controls_col,
            text="Duration: 01:00.0s",
            font=(FONT_MONO, 11, "bold"),
            text_color=ACCENT_TEXT,
            fg_color=ACCENT_SOFT_BG,
            corner_radius=6,
            height=28,
        )
        self.lbl_duration_pill.pack(fill="x", pady=(6, 6))

        # Quick Relative Offset Chips (+30s, +1m, +3m, +5m)
        chips_row = ctk.CTkFrame(controls_col, fg_color="transparent")
        chips_row.pack(fill="x", pady=(0, 10))

        def _preset(name: str, offset: float):
            return ctk.CTkButton(
                chips_row,
                text=name,
                height=24,
                font=(FONT_FAMILY, 9, "bold"),
                fg_color=BG_CARD,
                hover_color=BG_CARD_HOVER,
                command=lambda off=offset: self._apply_relative_preset(off),
            )

        _preset("+30s", 30.0).pack(side="left", fill="x", expand=True, padx=1)
        _preset("+1m", 60.0).pack(side="left", fill="x", expand=True, padx=1)
        _preset("+3m", 180.0).pack(side="left", fill="x", expand=True, padx=1)
        _preset("+5m", 300.0).pack(side="left", fill="x", expand=True, padx=1)

        # ── 4. Cut Verification & Download Buttons ────────────────────
        self.btn_preview_cut = ctk.CTkButton(
            controls_col,
            text="▶ Preview Cut",
            height=34,
            font=(FONT_FAMILY, 11, "bold"),
            fg_color=BG_CARD,
            hover_color=ACCENT_PRIMARY,
            border_width=1,
            border_color=BORDER_SUBTLE,
            command=self._toggle_preview_cut,
        )
        self.btn_preview_cut.pack(fill="x", pady=(4, 6))

        self.btn_download_trim = ctk.CTkButton(
            controls_col,
            text="⬇ Download Clip",
            height=36,
            font=(FONT_FAMILY, 12, "bold"),
            corner_radius=RADIUS_BTN,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            command=self._on_click_download,
        )
        self.btn_download_trim.pack(fill="x", pady=(0, 2))

        # ═════════════════════════════════════════════════════════════
        # ── RIGHT PANEL: 16:9 Cinema Player & Interactive Timeline ────
        # ═════════════════════════════════════════════════════════════
        player_col = ctk.CTkFrame(self, fg_color="transparent")
        player_col.grid(row=0, column=1, padx=(6, 14), pady=12, sticky="nsew")
        player_col.grid_columnconfigure(0, weight=1)

        # Top Bar: Video Title, Metadata & Action Icons
        top_bar = ctk.CTkFrame(player_col, fg_color="transparent")
        top_bar.pack(fill="x", pady=(0, 6))

        info_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        info_box.pack(side="left", fill="x", expand=True)

        self.lbl_stream_title = ctk.CTkLabel(
            info_box,
            text="Ready to preview and trim online stream",
            font=(FONT_FAMILY, 11, "bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
            wraplength=400,
        )
        self.lbl_stream_title.pack(fill="x")

        self.lbl_stream_meta = ctk.CTkLabel(
            info_box,
            text="Paste a stream URL and click 'Trim Segment' or 'Load URL'",
            font=(FONT_MONO, 10),
            text_color=TEXT_MUTED,
            anchor="w",
        )
        self.lbl_stream_meta.pack(fill="x")

        top_actions = ctk.CTkFrame(top_bar, fg_color="transparent")
        top_actions.pack(side="right", padx=(8, 0))

        self.btn_audio = ctk.CTkButton(
            top_actions,
            text="Audio",
            width=54,
            height=26,
            font=(FONT_FAMILY, 10, "bold"),
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            command=self._toggle_audio,
        )
        self.btn_audio.pack(side="left", padx=2)

        self.btn_load_url = ctk.CTkButton(
            top_actions,
            text="Load URL",
            image=get_icon("download", size=12, color=TEXT_PRIMARY),
            compound="left",
            width=78,
            height=26,
            font=(FONT_FAMILY, 10, "bold"),
            fg_color=BG_CARD,
            hover_color=BG_CARD_HOVER,
            border_width=1,
            border_color=BORDER_SUBTLE,
            command=self._on_click_load_url,
        )
        self.btn_load_url.pack(side="left", padx=2)

        if self.on_close:
            ctk.CTkButton(
                top_actions,
                text="",
                image=get_icon("close", size=12, color=TEXT_SECONDARY),
                width=26,
                height=26,
                fg_color="transparent",
                hover_color=BG_CARD_HOVER,
                command=self.on_close,
            ).pack(side="left", padx=(4, 0))

        # ── 16:9 Cinema Live Video Canvas ─────────────────────────────
        self.preview_canvas = ctk.CTkCanvas(
            player_col,
            width=self.canvas_w,
            height=self.canvas_h,
            bg=BG_INPUT,
            highlightthickness=1,
            highlightbackground=BORDER_SUBTLE,
            cursor="hand2",
        )
        self.preview_canvas.pack(fill="both", expand=True, pady=(0, 8))
        self.preview_canvas.bind("<Button-1>", lambda _e: self._toggle_play_pause())
        self._draw_canvas_placeholder("⚡ Enter stream URL to preview & trim")

        # ── Unified Transport & Range Timeline Bar ────────────────────
        transport_row = ctk.CTkFrame(player_col, fg_color="transparent")
        transport_row.pack(fill="x")

        self.btn_play_pause = ctk.CTkButton(
            transport_row,
            text="▶",
            width=36,
            height=30,
            font=(FONT_FAMILY, 13, "bold"),
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            command=self._toggle_play_pause,
        )
        self.btn_play_pause.pack(side="left", padx=(0, 8))

        # Interactive Timeline Scrub Canvas with Start/End Range Markers
        self.timeline_canvas = ctk.CTkCanvas(
            transport_row,
            height=28,
            bg=BG_PANEL,
            highlightthickness=0,
            cursor="crosshair",
        )
        self.timeline_canvas.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.timeline_canvas.bind("<Configure>", lambda _e: self._redraw_timeline_track())
        self.timeline_canvas.bind("<Button-1>", self._on_timeline_click)
        self.timeline_canvas.bind("<B1-Motion>", self._on_timeline_drag)
        self.timeline_canvas.bind("<ButtonRelease-1>", self._on_timeline_release)

        self.lbl_timeline_time = ctk.CTkLabel(
            transport_row,
            text="00:00:00 / 00:00:00",
            font=(FONT_MONO, 10),
            text_color=TEXT_MUTED,
            width=120,
            anchor="e",
        )
        self.lbl_timeline_time.pack(side="right")

    # ═════════════════════════════════════════════════════════════════
    # ── Live Player Frame Handling & UI Synchronization ──────────────
    # ═════════════════════════════════════════════════════════════════
    def _on_player_frame(self, img: Image.Image, timestamp: float) -> None:
        self.current_time_sec = timestamp
        self.lbl_current_time.configure(text=format_seconds_tenths(timestamp))
        self.lbl_timeline_time.configure(
            text=f"{format_seconds(timestamp)} / {format_seconds(self.total_duration)}"
        )
        if not self._is_scrubbing:
            self._redraw_timeline_track()

        self._display_frame(img, timestamp)

    def _on_player_state_change(self, is_playing: bool) -> None:
        if is_playing:
            self.btn_play_pause.configure(text="⏸")
        else:
            self.btn_play_pause.configure(text="▶")
            if not self.player.is_previewing_cut:
                self.btn_preview_cut.configure(text="▶ Preview Cut", fg_color=BG_CARD)

    def _on_cut_preview_finished(self) -> None:
        self.btn_preview_cut.configure(text="▶ Preview Cut", fg_color=BG_CARD)
        self.btn_play_pause.configure(text="▶")
        self._redraw_timeline_track()

    def _display_frame(self, img: Image.Image, timestamp: float) -> None:
        try:
            cw = self.preview_canvas.winfo_width()
            ch = self.preview_canvas.winfo_height()
            if cw > 50 and ch > 50 and (cw != self.canvas_w or ch != self.canvas_h):
                self.canvas_w = cw
                self.canvas_h = ch
                img = img.resize((cw, ch), Image.Resampling.BILINEAR)

            self._preview_photo = ImageTk.PhotoImage(img)
            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(
                self.canvas_w // 2, self.canvas_h // 2, image=self._preview_photo
            )

            # Timestamp pill overlay on bottom-right of preview
            t_str = format_seconds_tenths(timestamp)
            pw, ph = 92, 22
            x2 = self.canvas_w - 8
            y2 = self.canvas_h - 8
            x1 = x2 - pw
            y1 = y2 - ph
            self.preview_canvas.create_rectangle(
                x1, y1, x2, y2, fill="#0E0E14", outline=BORDER_SUBTLE, width=1
            )
            self.preview_canvas.create_text(
                (x1 + x2) // 2,
                (y1 + y2) // 2,
                text=t_str,
                fill=ACCENT_TEXT,
                font=(FONT_MONO, 9, "bold"),
            )

            # Cut preview active indicator badge
            if self.player.is_previewing_cut:
                self.preview_canvas.create_rectangle(
                    8, 8, 150, 32, fill="#4C1D95", outline=ACCENT_HOVER, width=1
                )
                self.preview_canvas.create_text(
                    79,
                    20,
                    text="✂ PREVIEWING CUT",
                    fill="#FFFFFF",
                    font=(FONT_FAMILY, 9, "bold"),
                )
            elif not self.player.is_playing:
                # Translucent play badge overlay in center when paused
                cx, cy = self.canvas_w // 2, self.canvas_h // 2
                self.preview_canvas.create_oval(
                    cx - 24, cy - 24, cx + 24, cy + 24,
                    fill="#1A1A26", outline=BORDER_SUBTLE, width=1
                )
                self.preview_canvas.create_polygon(
                    cx - 7, cy - 11, cx - 7, cy + 11, cx + 11, cy,
                    fill="#FFFFFF"
                )
        except Exception as exc:
            log.debug("Display frame error: %s", exc)

    def _draw_canvas_placeholder(self, text: str) -> None:
        try:
            self.preview_canvas.delete("all")
            self.preview_canvas.create_text(
                self.canvas_w // 2,
                self.canvas_h // 2,
                text=text,
                fill=TEXT_MUTED,
                font=(FONT_FAMILY, 11, "bold"),
                justify="center",
                width=self.canvas_w - 40,
            )
        except Exception:
            pass

    # ═════════════════════════════════════════════════════════════════
    # ── Interactive Timeline Rendering & Scrubbing ────────────────────
    # ═════════════════════════════════════════════════════════════════
    def _redraw_timeline_track(self) -> None:
        c = self.timeline_canvas
        w = max(50, c.winfo_width())
        h = max(20, c.winfo_height())
        c.delete("all")

        pad = 8
        track_w = max(10, w - 2 * pad)
        track_h = 10
        y1 = (h - track_h) // 2
        y2 = y1 + track_h

        # 1. Background Track
        c.create_rectangle(pad, y1, pad + track_w, y2, fill=BG_CARD, outline=BORDER_SUBTLE, width=1)

        dur = max(1.0, self.total_duration)

        # 2. Selected Cut Range Highlight
        x_start = pad + (max(0.0, self.start_sec) / dur) * track_w
        x_end = pad + (min(dur, self.end_sec) / dur) * track_w
        if x_end > x_start:
            c.create_rectangle(x_start, y1, x_end, y2, fill=ACCENT_PRIMARY, outline=ACCENT_HOVER, width=1)
            # Start bracket marker [
            c.create_line(x_start, y1 - 3, x_start, y2 + 3, fill="#C4B5FD", width=2)
            c.create_line(x_start, y1 - 3, x_start + 4, y1 - 3, fill="#C4B5FD", width=2)
            c.create_line(x_start, y2 + 3, x_start + 4, y2 + 3, fill="#C4B5FD", width=2)
            # End bracket marker ]
            c.create_line(x_end, y1 - 3, x_end, y2 + 3, fill="#C4B5FD", width=2)
            c.create_line(x_end, y1 - 3, x_end - 4, y1 - 3, fill="#C4B5FD", width=2)
            c.create_line(x_end, y2 + 3, x_end - 4, y2 + 3, fill="#C4B5FD", width=2)

        # 3. Current Playhead Indicator
        x_cur = pad + (max(0.0, min(dur, self.current_time_sec)) / dur) * track_w
        c.create_line(x_cur, 2, x_cur, h - 2, fill="#FFFFFF", width=2)
        c.create_oval(x_cur - 4, y1 - 3, x_cur + 4, y1 + 5, fill="#FFFFFF", outline=ACCENT_PRIMARY)

    def _on_timeline_click(self, event) -> None:
        self._is_scrubbing = True
        self._seek_from_timeline_event(event)

    def _on_timeline_drag(self, event) -> None:
        self._seek_from_timeline_event(event)

    def _on_timeline_release(self, event) -> None:
        self._seek_from_timeline_event(event)
        self._is_scrubbing = False

    def _seek_from_timeline_event(self, event) -> None:
        c = self.timeline_canvas
        w = max(50, c.winfo_width())
        pad = 8
        track_w = max(10, w - 2 * pad)
        frac = max(0.0, min(1.0, (event.x - pad) / track_w))
        target_t = frac * max(1.0, self.total_duration)

        self.current_time_sec = target_t
        self.lbl_current_time.configure(text=format_seconds_tenths(target_t))
        self.lbl_timeline_time.configure(
            text=f"{format_seconds(target_t)} / {format_seconds(self.total_duration)}"
        )
        self._redraw_timeline_track()

        if self.player.is_playing:
            self.player.seek(target_t)
        else:
            self._schedule_debounce_frame_fetch(target_t)

    # ═════════════════════════════════════════════════════════════════
    # ── Playback Controls & Cut Preview ───────────────────────────────
    # ═════════════════════════════════════════════════════════════════
    def _toggle_play_pause(self) -> None:
        if not self.stream_info or not (self.stream_info.preview_stream_url or self.stream_info.stream_url):
            return

        if self.player.is_playing:
            self.player.pause()
        else:
            from_t = self.current_time_sec
            if from_t >= self.total_duration - 0.5:
                from_t = self.start_sec
            self.player.play(from_time=from_t)

    def _toggle_preview_cut(self) -> None:
        if not self.stream_info:
            return

        if self.player.is_playing and self.player.is_previewing_cut:
            self.player.pause()
        else:
            self.btn_preview_cut.configure(text="■ Stop Preview", fg_color=ACCENT_PRIMARY)
            self.player.play(from_time=self.start_sec, until_time=self.end_sec)

    def _step_time(self, delta: float) -> None:
        new_t = self.player.step(delta)
        self.current_time_sec = new_t
        self.lbl_current_time.configure(text=format_seconds_tenths(new_t))
        self.lbl_timeline_time.configure(
            text=f"{format_seconds(new_t)} / {format_seconds(self.total_duration)}"
        )
        self._redraw_timeline_track()
        self._fetch_preview_frame(new_t)

    def _jump_to(self, timestamp: float) -> None:
        t = max(0.0, min(self.total_duration, float(timestamp)))
        self.current_time_sec = t
        self.lbl_current_time.configure(text=format_seconds_tenths(t))
        self.lbl_timeline_time.configure(
            text=f"{format_seconds(t)} / {format_seconds(self.total_duration)}"
        )
        self._redraw_timeline_track()
        if self.player.is_playing:
            self.player.seek(t)
        else:
            self._fetch_preview_frame(t)

    def _toggle_audio(self) -> None:
        self.audio_muted = not self.audio_muted
        self.player.set_audio_enabled(not self.audio_muted)
        if self.audio_muted:
            self.btn_audio.configure(text="Muted", fg_color=BG_CARD)
        else:
            self.btn_audio.configure(text="Audio", fg_color=ACCENT_PRIMARY)

    def stop_playback(self) -> None:
        if hasattr(self, "player") and self.player:
            self.player.stop()

    # ═════════════════════════════════════════════════════════════════
    # ── Instant Timestamp Captures & Offset Chips ────────────────────
    # ═════════════════════════════════════════════════════════════════
    def _capture_start_time(self) -> None:
        self.start_sec = max(0.0, min(self.total_duration, round(self.current_time_sec, 1)))
        if self.start_sec >= self.end_sec:
            self.end_sec = min(self.total_duration, self.start_sec + 30.0)

        self.entry_start.delete(0, "end")
        self.entry_start.insert(0, format_seconds_tenths(self.start_sec))
        self.entry_end.delete(0, "end")
        self.entry_end.insert(0, format_seconds_tenths(self.end_sec))
        self._update_duration_pill()
        self._redraw_timeline_track()

    def _capture_end_time(self) -> None:
        new_end = max(0.0, min(self.total_duration, round(self.current_time_sec, 1)))
        if new_end <= self.start_sec:
            new_end = min(self.total_duration, self.start_sec + 5.0)

        self.end_sec = new_end
        self.entry_end.delete(0, "end")
        self.entry_end.insert(0, format_seconds_tenths(self.end_sec))
        self._update_duration_pill()
        self._redraw_timeline_track()

    def _apply_relative_preset(self, offset: float) -> None:
        self.end_sec = min(self.total_duration, self.start_sec + offset)
        if self.end_sec <= self.start_sec:
            self.end_sec = min(self.total_duration, self.start_sec + 1.0)
        self.entry_end.delete(0, "end")
        self.entry_end.insert(0, format_seconds_tenths(self.end_sec))
        self._update_duration_pill()
        self._redraw_timeline_track()
        self._jump_to(self.end_sec)

    def _on_start_entry_changed(self, _event=None) -> None:
        s_val = parse_timestamp_str(self.entry_start.get())
        self.start_sec = max(0.0, min(self.total_duration, s_val))
        if self.start_sec >= self.end_sec:
            self.end_sec = min(self.total_duration, self.start_sec + 30.0)
            self.entry_end.delete(0, "end")
            self.entry_end.insert(0, format_seconds_tenths(self.end_sec))

        self.entry_start.delete(0, "end")
        self.entry_start.insert(0, format_seconds_tenths(self.start_sec))
        self._update_duration_pill()
        self._redraw_timeline_track()
        self._jump_to(self.start_sec)

    def _on_end_entry_changed(self, _event=None) -> None:
        e_val = parse_timestamp_str(self.entry_end.get())
        if e_val <= self.start_sec:
            e_val = min(self.total_duration, self.start_sec + 5.0)
        self.end_sec = max(self.start_sec + 0.5, min(self.total_duration, e_val))

        self.entry_end.delete(0, "end")
        self.entry_end.insert(0, format_seconds_tenths(self.end_sec))
        self._update_duration_pill()
        self._redraw_timeline_track()

    def _update_duration_pill(self) -> None:
        clip_dur = max(0.1, self.end_sec - self.start_sec)
        dur_str = format_seconds_tenths(clip_dur)
        self.lbl_duration_pill.configure(text=f"Duration: {dur_str}s")

    # ═════════════════════════════════════════════════════════════════
    # ── Remote Stream Loading & Segment Download ──────────────────────
    # ═════════════════════════════════════════════════════════════════
    def load_url(self, url: str) -> None:
        """Alias for load_stream_url."""
        self.load_stream_url(url)

    def _on_click_load_url(self) -> None:
        url = ""
        if self.get_url_fn:
            try:
                url = self.get_url_fn()
            except Exception:
                url = ""
        if not url and self.stream_info:
            url = self.stream_info.url
        if url:
            self.load_stream_url(url)
        else:
            self.lbl_stream_title.configure(text="Please paste a stream URL first")

    def load_stream_url(self, url: str) -> None:
        url = url.strip()
        if not url:
            return

        self.stop_playback()
        self._is_loading = True
        self.lbl_stream_title.configure(text="⚡ Fetching stream info & buffering live preview...")
        self.lbl_stream_meta.configure(text="Resolving direct stream URL & keyframes…")
        self._draw_canvas_placeholder("⚡ Fetching stream info\n& buffering live preview...")

        def _worker():
            info = fetch_stream_info(url)
            self._ui_queue.put(lambda: self._on_stream_info_loaded(info))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stream_info_loaded(self, info: StreamMetadata) -> None:
        self._is_loading = False
        self.stream_info = info
        if not info.valid:
            self.lbl_stream_title.configure(text=f"Error: {info.error[:50]}")
            self.lbl_stream_meta.configure(text="Could not resolve stream URL")
            self._draw_canvas_placeholder(f"✗ Could not load stream\n{info.error[:40]}")
            return

        self.total_duration = max(1.0, float(info.duration or 300.0))

        # Check initial timestamp parameter (e.g. &t=8392s or 2h19m52s)
        if info.initial_timestamp is not None and info.initial_timestamp > 0:
            self.start_sec = min(self.total_duration, float(info.initial_timestamp))
            self.end_sec = min(self.total_duration, self.start_sec + 60.0)
            self.current_time_sec = self.start_sec
        else:
            self.start_sec = 0.0
            self.end_sec = min(self.total_duration, 60.0)
            self.current_time_sec = 0.0

        # Configure stream player source
        self.player.set_source(info)
        self.player.current_time = self.current_time_sec

        # Update entry readouts
        self.entry_start.delete(0, "end")
        self.entry_start.insert(0, format_seconds_tenths(self.start_sec))
        self.entry_end.delete(0, "end")
        self.entry_end.insert(0, format_seconds_tenths(self.end_sec))

        self.lbl_current_time.configure(text=format_seconds_tenths(self.current_time_sec))
        self.lbl_timeline_time.configure(
            text=f"{format_seconds(self.current_time_sec)} / {format_seconds(self.total_duration)}"
        )

        title = info.title if len(info.title) <= 55 else info.title[:52] + "…"
        dur_str = format_seconds(self.total_duration)
        channel = f" • {info.channel}" if info.channel else ""
        res = f" • {info.resolutions[0]}" if info.resolutions else ""

        self.lbl_stream_title.configure(text=title)
        self.lbl_stream_meta.configure(text=f"Duration: {dur_str}{channel}{res}")
        self._update_duration_pill()
        self._redraw_timeline_track()

        # Display remote thumbnail as immediate poster frame
        if info.thumbnail:
            def _thumb_worker():
                thumb_img = fetch_remote_thumbnail(info.thumbnail, self.canvas_w, self.canvas_h)
                if thumb_img:
                    self._ui_queue.put(lambda: self._display_frame(thumb_img, self.current_time_sec))

            threading.Thread(target=_thumb_worker, daemon=True).start()

        # Fetch first accurate frame at current_time_sec
        self._fetch_preview_frame(self.current_time_sec)

    def _schedule_debounce_frame_fetch(self, timestamp: float) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
        self._debounce_timer = threading.Timer(0.18, lambda: self._fetch_preview_frame(timestamp))
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def _fetch_preview_frame(self, timestamp: float) -> None:
        if not self.stream_info:
            return
        stream_url = self.stream_info.preview_stream_url or self.stream_info.stream_url
        if not stream_url:
            return

        cw, ch = self.canvas_w, self.canvas_h

        def _worker():
            img = extract_remote_frame(stream_url, timestamp, target_w=cw, target_h=ch)
            if img:
                self._ui_queue.put(lambda: self._display_frame(img, timestamp))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_click_download(self) -> None:
        if not self.stream_info:
            return
        self.stop_playback()
        if self.on_download_segment:
            self.on_download_segment(
                self.stream_info.url, self.start_sec, self.end_sec, self.stream_info
            )
