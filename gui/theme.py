"""Visual tokens for the screenshot organizer.

The window is a dark navy surface with one electric-cyan accent. Cyan is
reserved for the title mark, section labels, focus rings, and the two
primary actions (assign and export). Other buttons stay dark with a thin
accent outline so they do not compete.
"""

from __future__ import annotations

from dataclasses import dataclass

import customtkinter as ctk


# Near-black navy, not a neutral gray.
BG = "#071018"
PANEL = "#0d1826"
PANEL_BORDER = "#1c3346"
FIELD = "#09141f"
TEXT = "#e7f2f7"
MUTED = "#8ea6b8"
ACCENT = "#2ee6ff"
ACCENT_HOVER = "#7af6ff"
ACCENT_DIM = "#1a6572"
ACCENT_SOFT = "#0f3d48"

UI_FAMILY = "Inter"
MONO_FAMILY = "JetBrains Mono"


@dataclass
class Fonts:
    """Created after the Tk root exists. CTkFont needs a running window."""

    title: ctk.CTkFont
    section: ctk.CTkFont
    ui: ctk.CTkFont
    ui_bold: ctk.CTkFont
    small: ctk.CTkFont
    mono: tuple[str, int]


def build_fonts() -> Fonts:
    return Fonts(
        title=ctk.CTkFont(family=UI_FAMILY, size=26, weight="bold"),
        section=ctk.CTkFont(family=MONO_FAMILY, size=13, weight="bold"),
        ui=ctk.CTkFont(family=UI_FAMILY, size=14),
        ui_bold=ctk.CTkFont(family=UI_FAMILY, size=14, weight="bold"),
        small=ctk.CTkFont(family=UI_FAMILY, size=13),
        # 11px fits the ten sample rows in each list without clipping the last line.
        mono=(MONO_FAMILY, 11),
    )


def primary_button(parent: ctk.CTkBaseClass, text: str, command, fonts: Fonts) -> ctk.CTkButton:
    """Solid cyan button for the action that should be obvious."""

    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        fg_color=ACCENT,
        hover_color=ACCENT_HOVER,
        text_color="#041016",
        font=fonts.ui_bold,
        corner_radius=10,
        height=36,
        border_width=0,
    )


def secondary_button(parent: ctk.CTkBaseClass, text: str, command, fonts: Fonts) -> ctk.CTkButton:
    """Quiet button: dark fill, thin cyan edge."""

    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        fg_color=PANEL,
        hover_color="#143044",
        text_color=TEXT,
        border_width=1,
        border_color=ACCENT_DIM,
        font=fonts.ui,
        corner_radius=10,
        height=34,
    )


def section_label(parent: ctk.CTkBaseClass, text: str, fonts: Fonts) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent,
        text=text,
        font=fonts.section,
        text_color=ACCENT,
        anchor="w",
        fg_color="transparent",
    )


def muted_label(parent: ctk.CTkBaseClass, text: str, fonts: Fonts, **kwargs) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent,
        text=text,
        font=fonts.small,
        text_color=MUTED,
        anchor="w",
        fg_color="transparent",
        **kwargs,
    )
