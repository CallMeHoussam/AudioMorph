"""
Modern custom card-based queue and interactive drag-and-drop empty-state hero.

Replaces classic ``ttk.Treeview`` tables and native OS scrollbars with dark,
1px-bordered ``FileQueueCard`` rows, live status pills, mini progress bars,
and a dashed-border ``EmptyDropzoneHero`` for effortless onboarding.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

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
    BORDER_DASHED,
    BORDER_SUBTLE,
    FONT_FAMILY,
    FONT_MONO,
    RADIUS_BTN,
    RADIUS_CARD,
    STATUS_ERROR,
    STATUS_ERROR_BG,
    STATUS_SUCCESS,
    STATUS_SUCCESS_BG,
    STATUS_WARNING,
    STATUS_WARNING_BG,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


def _draw_rounded_rect_points(x0: float, y0: float, x1: float, y1: float, r: float) -> list[float]:
    """Generate polygon points for a smooth rounded rectangle on tk.Canvas."""
    r = max(2.0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    return [
        x0 + r, y0,
        x1 - r, y0,
        x1, y0, x1, y0 + r,
        x1, y1 - r,
        x1, y1, x1 - r, y1,
        x0 + r, y1,
        x0, y1, x0, y1 - r,
        x0, y0 + r,
        x0, y0, x0 + r, y0,
    ]


class EmptyDropzoneHero(ctk.CTkFrame):
    """Interactive dashed-border dropzone hero shown when a queue is empty."""

    def __init__(
        self,
        master,
        title: str,
        subtitle: str,
        button_text: str,
        on_browse: Optional[Callable[[], None]] = None,
        icon_name: str = "upload",
        platform_badges: Optional[list[str]] = None,
        compact: bool = False,
        canvas_bg: str = BG_ROOT,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color=canvas_bg, **kwargs)
        self._on_browse = on_browse
        self._compact = compact
        self._canvas_bg = canvas_bg

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            self, bg=canvas_bg, highlightthickness=0, cursor="hand2" if on_browse else "arrow"
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._canvas.bind("<Configure>", self._redraw_border)

        self._inner = ctk.CTkFrame(self._canvas, fg_color=BG_PANEL, corner_radius=0)
        self._win_id = self._canvas.create_window(0, 0, window=self._inner, anchor="center")

        if compact:
            self._build_compact(icon_name, title, subtitle, button_text)
        else:
            self._build_full(icon_name, title, subtitle, button_text, platform_badges)

        if on_browse:
            self._bind_click_recursive(self._canvas)
            self._bind_click_recursive(self._inner)

    def _build_full(
        self,
        icon_name: str,
        title: str,
        subtitle: str,
        button_text: str,
        platform_badges: Optional[list[str]],
    ) -> None:
        badge = ctk.CTkFrame(
            self._inner,
            width=76,
            height=76,
            corner_radius=38,
            fg_color=ACCENT_SOFT_BG,
            border_width=1,
            border_color=BORDER_DASHED,
        )
        badge.pack(pady=(8, 16))
        badge.pack_propagate(False)
        ctk.CTkLabel(
            badge,
            text="",
            image=get_icon(icon_name, size=34, color=TEXT_PRIMARY, accent=ACCENT_TEXT),
        ).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            self._inner,
            text=title,
            font=(FONT_FAMILY, 19, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(pady=(0, 6))

        ctk.CTkLabel(
            self._inner,
            text=subtitle,
            font=(FONT_FAMILY, 12),
            text_color=TEXT_SECONDARY,
            wraplength=460,
            justify="center",
        ).pack(pady=(0, 16))

        if platform_badges:
            row = ctk.CTkFrame(self._inner, fg_color="transparent")
            row.pack(pady=(0, 16))
            for name in platform_badges:
                pill = ctk.CTkLabel(
                    row,
                    text=name,
                    font=(FONT_FAMILY, 10, "bold"),
                    text_color=ACCENT_TEXT,
                    fg_color=BG_CARD,
                    corner_radius=8,
                    padx=10,
                    pady=3,
                )
                pill.pack(side="left", padx=4)

        if self._on_browse:
            ctk.CTkButton(
                self._inner,
                text=button_text,
                image=get_icon("add", size=16, color=TEXT_PRIMARY),
                compound="left",
                height=40,
                width=190,
                corner_radius=RADIUS_BTN,
                font=(FONT_FAMILY, 13, "bold"),
                fg_color=ACCENT_PRIMARY,
                hover_color=ACCENT_HOVER,
                command=self._on_browse,
            ).pack(pady=(2, 8))

    def _build_compact(
        self,
        icon_name: str,
        title: str,
        subtitle: str,
        button_text: str,
    ) -> None:
        row = ctk.CTkFrame(self._inner, fg_color="transparent")
        row.pack(fill="x", expand=True, padx=16, pady=8)

        badge = ctk.CTkFrame(
            row,
            width=48,
            height=48,
            corner_radius=24,
            fg_color=ACCENT_SOFT_BG,
            border_width=1,
            border_color=BORDER_DASHED,
        )
        badge.pack(side="left", padx=(0, 14))
        badge.pack_propagate(False)
        ctk.CTkLabel(
            badge,
            text="",
            image=get_icon(icon_name, size=24, color=TEXT_PRIMARY, accent=ACCENT_TEXT),
        ).place(relx=0.5, rely=0.5, anchor="center")

        txt_col = ctk.CTkFrame(row, fg_color="transparent")
        txt_col.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(
            txt_col,
            text=title,
            font=(FONT_FAMILY, 13, "bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            txt_col,
            text=subtitle,
            font=(FONT_FAMILY, 11),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).pack(anchor="w")

        if self._on_browse:
            ctk.CTkButton(
                row,
                text=button_text,
                image=get_icon("add", size=14, color=TEXT_PRIMARY),
                compound="left",
                height=34,
                width=145,
                corner_radius=RADIUS_BTN,
                font=(FONT_FAMILY, 12, "bold"),
                fg_color=ACCENT_PRIMARY,
                hover_color=ACCENT_HOVER,
                command=self._on_browse,
            ).pack(side="right", padx=(12, 0))

    def _bind_click_recursive(self, widget) -> None:
        # Avoid overriding the primary button's own command
        if isinstance(widget, ctk.CTkButton):
            return
        try:
            widget.bind("<Button-1>", lambda _e: self._on_browse() if self._on_browse else None)
        except Exception:
            pass
        for child in widget.winfo_children():
            self._bind_click_recursive(child)

    def _redraw_border(self, _event=None) -> None:
        w = max(80, self._canvas.winfo_width())
        h = max(60, self._canvas.winfo_height())
        self._canvas.delete("border")
        pad = 3
        pts = _draw_rounded_rect_points(pad, pad, w - pad, h - pad, 14)
        self._canvas.create_polygon(
            pts,
            smooth=True,
            fill=BG_PANEL,
            outline=BORDER_DASHED,
            width=2,
            dash=(7, 5),
            tags="border",
        )
        self._canvas.coords(self._win_id, w / 2.0, h / 2.0)
        self._canvas.tag_lower("border")


class FileQueueCard(ctk.CTkFrame):
    """Single luxury card representing a queued media file or URL."""

    def __init__(
        self,
        master,
        title: str,
        subtitle: str,
        badge: str,
        on_remove: Callable[[], None],
        on_select: Optional[Callable[[], None]] = None,
        compact: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=BG_CARD,
            corner_radius=RADIUS_CARD,
            border_width=1,
            border_color=BORDER_SUBTLE,
            **kwargs,
        )
        self._on_select = on_select
        self._is_active = False

        pad_y = 6 if compact else 9
        self.grid_columnconfigure(1, weight=1)

        # Left file-type pill
        self._badge_lbl = ctk.CTkLabel(
            self,
            text=(badge or "FILE")[:6].upper(),
            width=54,
            height=28 if compact else 32,
            corner_radius=8,
            fg_color=ACCENT_SOFT_BG,
            text_color=ACCENT_TEXT,
            font=(FONT_MONO, 10, "bold"),
        )
        self._badge_lbl.grid(row=0, column=0, padx=(10, 10), pady=pad_y)

        # Middle title + metadata
        info = ctk.CTkFrame(self, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", pady=pad_y)
        info.grid_columnconfigure(0, weight=1)

        display_title = title if len(title) <= 58 else title[:55] + "…"
        self._title_lbl = ctk.CTkLabel(
            info,
            text=display_title,
            font=(FONT_FAMILY, 12, "bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        )
        self._title_lbl.grid(row=0, column=0, sticky="w")

        self._sub_lbl = ctk.CTkLabel(
            info,
            text=subtitle,
            font=(FONT_FAMILY, 10),
            text_color=TEXT_SECONDARY,
            anchor="w",
        )
        self._sub_lbl.grid(row=1, column=0, sticky="w")

        # Right status pill + mini progress + remove
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=2, padx=(8, 8), pady=pad_y)

        self._preview_pill = ctk.CTkLabel(
            right,
            text="Previewing",
            font=(FONT_FAMILY, 9, "bold"),
            text_color=ACCENT_TEXT,
            fg_color=ACCENT_SOFT_BG,
            corner_radius=6,
            padx=7,
            pady=2,
        )

        self._status_box = ctk.CTkFrame(right, fg_color="transparent")
        self._status_box.pack(side="left", padx=(0, 8))

        self._status_pill = ctk.CTkLabel(
            self._status_box,
            text="Ready",
            font=(FONT_FAMILY, 10, "bold"),
            text_color=TEXT_SECONDARY,
            fg_color="#222232",
            corner_radius=8,
            padx=10,
            pady=3,
        )
        self._status_pill.pack(anchor="e")

        self._mini_progress = ctk.CTkProgressBar(
            self._status_box,
            width=96,
            height=4,
            corner_radius=2,
            progress_color=ACCENT_HOVER,
            fg_color=BG_INPUT,
        )
        self._mini_progress.set(0.0)

        self._btn_remove = ctk.CTkButton(
            right,
            text="",
            image=get_icon("close", size=13, color=TEXT_SECONDARY),
            width=26,
            height=26,
            corner_radius=8,
            fg_color="transparent",
            hover_color=STATUS_ERROR_BG,
            command=on_remove,
        )
        self._btn_remove.pack(side="right")

        if on_select is not None:
            for w in (self, self._badge_lbl, info, self._title_lbl, self._sub_lbl, self._status_pill):
                w.configure(cursor="hand2")
                w.bind("<Button-1>", lambda _e: self._on_select())

        self.bind("<Enter>", lambda _e: self._on_hover(True))
        self.bind("<Leave>", lambda _e: self._on_hover(False))

    def _on_hover(self, entered: bool) -> None:
        self.configure(fg_color=BG_CARD_HOVER if entered else BG_CARD)

    def set_active(self, active: bool) -> None:
        self._is_active = active
        if active:
            self.configure(border_color=ACCENT_GLOW)
            self._preview_pill.pack(side="left", padx=(0, 8), before=self._status_box)
        else:
            self.configure(border_color=BORDER_SUBTLE)
            self._preview_pill.pack_forget()

    def update_meta(self, subtitle: Optional[str] = None, badge: Optional[str] = None) -> None:
        if subtitle is not None:
            self._sub_lbl.configure(text=subtitle)
        if badge is not None:
            self._badge_lbl.configure(text=badge[:6].upper())

    def update_status(self, status_text: str, progress: Optional[float] = None) -> None:
        txt = (status_text or "Ready").strip()
        low = txt.lower()

        if txt.startswith("✓") or "done" in low or "complete" in low:
            fg, col = STATUS_SUCCESS_BG, STATUS_SUCCESS
            show_bar = False
        elif txt.startswith("✗") or "error" in low or "fail" in low or "invalid" in low or "cancel" in low:
            fg, col = STATUS_ERROR_BG, STATUS_ERROR
            show_bar = False
        elif "%" in txt or "processing" in low or "downloading" in low or "rendering" in low or "converting" in low or "pending" in low or "merging" in low:
            fg, col = ACCENT_SOFT_BG, ACCENT_TEXT
            show_bar = progress is not None
        else:
            fg, col = "#222232", TEXT_SECONDARY
            show_bar = False

        self._status_pill.configure(text=txt, fg_color=fg, text_color=col)
        if show_bar and progress is not None:
            self._mini_progress.set(max(0.0, min(1.0, float(progress))))
            if not self._mini_progress.winfo_ismapped():
                self._mini_progress.pack(anchor="e", pady=(4, 0))
        else:
            if self._mini_progress.winfo_ismapped():
                self._mini_progress.pack_forget()


class ModernQueueList(ctk.CTkScrollableFrame):
    """Dark scrollable container managing an ordered list of ``FileQueueCard`` widgets."""

    def __init__(
        self,
        master,
        on_remove_index: Optional[Callable[[int], None]] = None,
        on_select_index: Optional[Callable[[int], None]] = None,
        compact: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color="transparent",
            scrollbar_button_color=BORDER_SUBTLE,
            scrollbar_button_hover_color=ACCENT_PRIMARY,
            **kwargs,
        )
        self._on_remove_index = on_remove_index
        self._on_select_index = on_select_index
        self._compact = compact
        self.cards: list[FileQueueCard] = []
        self._active_index: int = -1

    def add_card(self, title: str, subtitle: str, badge: str) -> int:
        idx = len(self.cards)

        def _remove() -> None:
            if card in self.cards:
                cur_idx = self.cards.index(card)
                if self._on_remove_index:
                    self._on_remove_index(cur_idx)

        def _select() -> None:
            if card in self.cards:
                cur_idx = self.cards.index(card)
                self.set_active_index(cur_idx)
                if self._on_select_index:
                    self._on_select_index(cur_idx)

        card = FileQueueCard(
            self,
            title=title,
            subtitle=subtitle,
            badge=badge,
            on_remove=_remove,
            on_select=_select if self._on_select_index is not None else None,
            compact=self._compact,
        )
        card.pack(fill="x", padx=2, pady=(0, 6 if self._compact else 8))
        self.cards.append(card)
        return idx

    def update_meta(self, index: int, subtitle: Optional[str] = None, badge: Optional[str] = None) -> None:
        if 0 <= index < len(self.cards):
            self.cards[index].update_meta(subtitle=subtitle, badge=badge)

    def update_status(self, index: int, status_text: str, progress: Optional[float] = None) -> None:
        if 0 <= index < len(self.cards):
            self.cards[index].update_status(status_text, progress=progress)

    def remove_at(self, index: int) -> None:
        if 0 <= index < len(self.cards):
            card = self.cards.pop(index)
            card.destroy()
            if self._active_index == index:
                self._active_index = -1
            elif self._active_index > index:
                self._active_index -= 1

    def clear(self) -> None:
        for card in self.cards:
            card.destroy()
        self.cards.clear()
        self._active_index = -1

    def set_active_index(self, index: int) -> None:
        self._active_index = index
        for i, card in enumerate(self.cards):
            card.set_active(i == index)

    def count(self) -> int:
        return len(self.cards)

