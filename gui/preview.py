"""Preview one screenshot, then bucket it into the current group.

The main window stays usable while this is open, so the session and group
can be chosen before bucketing. Real images are shown scaled down. A text
placeholder is shown as its filename, the same way Word export treats it.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path

import customtkinter as ctk

from export_docx import is_embeddable_image
from model import Shot
from theme import (
    ACCENT,
    BG,
    FIELD,
    MUTED,
    PANEL_BORDER,
    TEXT,
    Fonts,
    primary_button,
    secondary_button,
)


# Keep previews inside the dialog. subsample() only scales by whole numbers.
_MAX_WIDTH = 720
_MAX_HEIGHT = 400


class PreviewWindow:
    """One reusable preview. Call show() to point it at another file."""

    def __init__(
        self,
        parent: ctk.CTk,
        fonts: Fonts,
        shots: list[Shot],
        start_index: int,
        bucket_text: Callable[[], str],
        on_bucket: Callable[[Shot], bool],
        on_show: Callable[[Shot], None],
        describe: Callable[[Shot], str],
        is_unassigned: Callable[[Shot], bool],
    ) -> None:
        self._fonts = fonts
        self._shots = shots
        self._index = start_index
        self._bucket_text = bucket_text
        self._on_bucket = on_bucket
        self._on_show = on_show
        self._describe = describe
        self._is_unassigned = is_unassigned
        # PhotoImage is dropped if nothing in Python still references it.
        self._photo: tk.PhotoImage | None = None

        self.window = ctk.CTkToplevel(parent)
        self.window.title("Preview")
        self.window.configure(fg_color=BG)
        self.window.transient(parent)
        self.window.resizable(False, False)

        body = ctk.CTkFrame(self.window, fg_color=BG)
        body.pack(fill="both", expand=True, padx=22, pady=18)

        ctk.CTkLabel(
            body,
            text="Preview",
            font=fonts.ui_bold,
            text_color=ACCENT,
            anchor="w",
            fg_color="transparent",
        ).pack(fill="x")

        self._stage = ctk.CTkFrame(
            body,
            fg_color=FIELD,
            corner_radius=12,
            border_width=1,
            border_color=PANEL_BORDER,
            width=_MAX_WIDTH + 24,
            height=_MAX_HEIGHT + 24,
        )
        self._stage.pack(fill="x", pady=(12, 10))
        self._stage.pack_propagate(False)

        # A plain label hosts the bitmap. CustomTkinter images need Pillow,
        # and the sample PNGs load with Tk on their own.
        self._image_label = tk.Label(self._stage, bg=FIELD, bd=0, highlightthickness=0)
        self._text_label = ctk.CTkLabel(
            self._stage,
            text="",
            font=fonts.section,
            text_color=TEXT,
            fg_color="transparent",
            wraplength=640,
            justify="center",
        )

        self._caption = ctk.CTkLabel(
            body,
            text="",
            font=fonts.ui,
            text_color=TEXT,
            anchor="w",
            fg_color="transparent",
        )
        self._caption.pack(fill="x")
        self._status = ctk.CTkLabel(
            body,
            text="",
            font=fonts.small,
            text_color=MUTED,
            anchor="w",
            fg_color="transparent",
        )
        self._status.pack(fill="x", pady=(2, 14))

        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(anchor="e")
        self._previous = secondary_button(buttons, "Previous", self._previous_shot, fonts)
        self._previous.pack(side="left")
        self._next = secondary_button(buttons, "Next", self._next_shot, fonts)
        self._next.pack(side="left", padx=(8, 0))
        self._bucket = primary_button(buttons, "Bucket into this group", self._bucket_current, fonts)
        self._bucket.configure(width=320)
        self._bucket.pack(side="left", padx=(8, 0))
        secondary_button(buttons, "Close", self.window.destroy, fonts).pack(side="left", padx=(8, 0))

        self.window.bind("<Left>", lambda _event: self._previous_shot())
        self.window.bind("<Right>", lambda _event: self._next_shot())
        self.window.bind("<Escape>", lambda _event: self.window.destroy())

        self.show(start_index)
        self.window.update_idletasks()
        width = max(self.window.winfo_width(), _MAX_WIDTH + 68)
        height = self.window.winfo_height()
        origin_x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        origin_y = parent.winfo_rooty() + max(40, (parent.winfo_height() - height) // 2)
        self.window.geometry(f"{width}x{height}+{origin_x}+{origin_y}")
        self.window.lift()
        self.window.focus_force()

    def winfo_exists(self) -> bool:
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    def lift(self) -> None:
        self.window.lift()
        self.window.focus_force()

    def show(self, index: int) -> None:
        if not self._shots:
            return
        self._index = max(0, min(index, len(self._shots) - 1))
        shot = self._shots[self._index]
        self._show_shot(shot)
        self._caption.configure(text=shot.caption())
        self._status.configure(text=self._describe(shot))
        self._bucket.configure(text=self._bucket_text())
        self._previous.configure(state="normal" if self._index > 0 else "disabled")
        self._next.configure(state="normal" if self._index + 1 < len(self._shots) else "disabled")
        self._on_show(shot)

    def _show_shot(self, shot: Shot) -> None:
        photo = _load_preview(shot.path)
        self._photo = photo
        if photo is None:
            self._image_label.pack_forget()
            note = shot.filename
            if not is_embeddable_image(shot.path):
                note = f"{shot.filename}\n\nText placeholder. The Word document will use this filename."
            self._text_label.configure(text=note)
            self._text_label.pack(expand=True)
            return
        self._text_label.pack_forget()
        self._image_label.configure(image=photo)
        self._image_label.pack(expand=True)

    def _previous_shot(self) -> None:
        if self._index > 0:
            self.show(self._index - 1)

    def _next_shot(self) -> None:
        if self._index + 1 < len(self._shots):
            self.show(self._index + 1)

    def _bucket_current(self) -> None:
        if not self._shots:
            return
        shot = self._shots[self._index]
        if not self._on_bucket(shot):
            self._bucket.configure(text=self._bucket_text())
            return
        # Keep reviewing files that are not in a group yet.
        for nxt in list(range(self._index + 1, len(self._shots))) + list(range(0, self._index)):
            if self._is_unassigned(self._shots[nxt]):
                self.show(nxt)
                return
        self.show(self._index)


def _load_preview(path: Path) -> tk.PhotoImage | None:
    """Return a scaled bitmap, or None when the file is not a Tk image."""

    if not is_embeddable_image(path):
        return None
    try:
        photo = tk.PhotoImage(file=str(path))
    except tk.TclError:
        return None
    factor = 1
    width = max(photo.width(), 1)
    height = max(photo.height(), 1)
    while width // factor > _MAX_WIDTH or height // factor > _MAX_HEIGHT:
        factor += 1
    if factor > 1:
        photo = photo.subsample(factor, factor)
    return photo
