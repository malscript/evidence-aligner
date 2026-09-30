"""Small dark prompts so warnings match the rest of the window.

File pickers stay with the system dialog. These prompts only replace the
plain message boxes for yes/no questions and short notices.
"""

from __future__ import annotations

import customtkinter as ctk

from theme import ACCENT, BG, TEXT, Fonts, primary_button, secondary_button


def show_message(parent: ctk.CTk, title: str, message: str, fonts: Fonts) -> None:
    _choose(parent, title, message, [("OK", True)], primary="OK", fonts=fonts)


def ask_yes_no(parent: ctk.CTk, title: str, message: str, fonts: Fonts) -> bool:
    answer = _choose(
        parent,
        title,
        message,
        [("No", False), ("Yes", True)],
        primary="Yes",
        fonts=fonts,
    )
    return answer is True


def _choose(
    parent: ctk.CTk,
    title: str,
    message: str,
    options: list[tuple[str, bool]],
    primary: str,
    fonts: Fonts,
) -> bool | None:
    result: dict[str, bool | None] = {"value": None}
    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    dialog.configure(fg_color=BG)
    dialog.resizable(False, False)
    dialog.transient(parent)

    body = ctk.CTkFrame(dialog, fg_color=BG)
    body.pack(fill="both", expand=True, padx=22, pady=20)

    ctk.CTkLabel(
        body,
        text=title,
        font=fonts.ui_bold,
        text_color=ACCENT,
        anchor="w",
        fg_color="transparent",
    ).pack(fill="x")
    ctk.CTkLabel(
        body,
        text=message,
        font=fonts.ui,
        text_color=TEXT,
        anchor="w",
        justify="left",
        wraplength=420,
        fg_color="transparent",
    ).pack(fill="x", pady=(10, 18))

    buttons = ctk.CTkFrame(body, fg_color="transparent")
    buttons.pack(anchor="e")

    def close(value: bool | None) -> None:
        result["value"] = value
        dialog.destroy()

    for label, value in options:
        button = primary_button if label == primary else secondary_button
        button(buttons, label, lambda chosen=value: close(chosen), fonts).pack(side="left", padx=(8, 0))

    primary_value = next(value for label, value in options if label == primary)
    dialog.protocol("WM_DELETE_WINDOW", lambda: close(None))
    dialog.bind("<Escape>", lambda _event: close(None))
    dialog.bind("<Return>", lambda _event: close(primary_value))

    dialog.update_idletasks()
    width = max(dialog.winfo_width(), 460)
    height = dialog.winfo_height()
    origin_x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
    origin_y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
    dialog.geometry(f"{width}x{height}+{origin_x}+{origin_y}")

    # Keep the prompt above the main window on Linux window managers.
    dialog.attributes("-topmost", True)
    dialog.lift()
    dialog.grab_set()
    dialog.focus_force()
    parent.wait_window(dialog)
    return result["value"]
