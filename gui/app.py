#!/usr/bin/env python3
"""Desktop organizer for timestamped screenshots.

Choose a folder (sample_images/ by default), group the files into sessions,
and export a Word document. Run from the repository root:

    pip install -r requirements.txt
    python gui/app.py

The window is CustomTkinter on top of Tkinter. Debian and Ubuntu sometimes
ship Python without Tk:

    sudo apt install python3-tk
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path


try:
    import customtkinter as ctk
except ImportError:
    sys.stderr.write(
        "customtkinter is required.\n"
        "From the repository root, run: pip install -r requirements.txt\n"
    )
    raise SystemExit(1)

try:
    from tkinter import filedialog
except ImportError:
    sys.stderr.write(
        "Tkinter is required but is not installed.\n"
        "On Debian/Ubuntu install it with: sudo apt install python3-tk\n"
    )
    raise SystemExit(1)

# `python gui/app.py` puts this directory on sys.path, so the sibling modules
# import directly. That keeps the launch command a plain script.
from dialogs import ask_yes_no, show_message
from export_docx import export_document
from model import Group, Organizer, Session, Shot
from preview import PreviewWindow
from theme import (
    ACCENT,
    ACCENT_DIM,
    ACCENT_SOFT,
    BG,
    FIELD,
    PANEL,
    PANEL_BORDER,
    TEXT,
    Fonts,
    build_fonts,
    muted_label,
    primary_button,
    secondary_button,
    section_label,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FOLDER = REPO_ROOT / "sample_images"


class OrganizerApp:
    """CustomTkinter front end over Organizer. All edits happen in memory."""

    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        self.organizer = Organizer()
        self.fonts: Fonts = build_fonts()
        self.folder_var = tk.StringVar(value=str(DEFAULT_FOLDER))
        self.session_name_var = tk.StringVar()
        self.group_label_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Choose a screenshots folder to begin.")

        # Parallel to the listboxes, so a selection index maps back to a Shot.
        self._all_view: list[Shot] = []
        self._unassigned_view: list[Shot] = []
        self._group_view: list[Shot] = []
        self._preview: PreviewWindow | None = None

        root.title("Screenshot organizer")
        root.minsize(1080, 700)
        root.geometry("1240x800")
        root.configure(fg_color=BG)
        self._build()
        self.load_folder(confirm=False)

    def _build(self) -> None:
        outer = ctk.CTkFrame(self.root, fg_color=BG)
        outer.pack(fill="both", expand=True, padx=22, pady=18)
        outer.rowconfigure(2, weight=1)
        outer.columnconfigure(0, weight=1)

        self._build_header(outer)
        self._build_folder_bar(outer)

        body = ctk.CTkFrame(outer, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        left = self._panel(body)
        right = self._panel(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self._build_lists(left)
        self._build_organization(right)

        footer = ctk.CTkFrame(outer, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        footer.columnconfigure(1, weight=1)
        export_button = primary_button(footer, "Export assigned to Word", self.export_word, self.fonts)
        export_button.configure(width=230)
        export_button.grid(row=0, column=0, padx=(0, 16))
        muted_label(footer, "", self.fonts, textvariable=self.status_var).grid(
            row=0, column=1, sticky="w"
        )

    def _build_header(self, parent: ctk.CTkFrame) -> None:
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.columnconfigure(1, weight=1)

        # A short cyan bar is the only decoration in the title. The name stays
        # in the light text color so it stays easy to read.
        ctk.CTkFrame(header, width=4, height=36, fg_color=ACCENT, corner_radius=2).grid(
            row=0, column=0, rowspan=2, sticky="ns", padx=(0, 12)
        )
        ctk.CTkLabel(
            header,
            text="Screenshot Organizer",
            font=self.fonts.title,
            text_color=TEXT,
            anchor="w",
            fg_color="transparent",
        ).grid(row=0, column=1, sticky="w")
        muted_label(
            header,
            "Preview a screenshot, drop it into a bucket, then export every bucket.",
            self.fonts,
        ).grid(row=1, column=1, sticky="w", pady=(2, 0))

    def _build_folder_bar(self, parent: ctk.CTkFrame) -> None:
        bar = self._panel(parent)
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        bar.columnconfigure(1, weight=1)

        muted_label(bar, "Screenshots folder", self.fonts).grid(
            row=0, column=0, padx=(16, 10), pady=14
        )
        folder_entry = self._entry(bar, self.folder_var)
        folder_entry.grid(row=0, column=1, sticky="ew", pady=14)
        folder_entry.bind("<Return>", lambda _event: self.load_folder())
        secondary_button(bar, "Browse", self.browse_folder, self.fonts).grid(
            row=0, column=2, padx=(10, 0), pady=14
        )
        secondary_button(bar, "Reload", self.load_folder, self.fonts).grid(
            row=0, column=3, padx=(8, 16), pady=14
        )

    def _build_lists(self, parent: ctk.CTkFrame) -> None:
        parent.rowconfigure(1, weight=3)
        parent.rowconfigure(3, weight=2)
        parent.columnconfigure(0, weight=1)

        section_label(parent, "All screenshots", self.fonts).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 6)
        )
        self.all_list = self._mount_list(parent, row=1, bottom=12)
        self.all_list.bind("<<ListboxSelect>>", self._on_all_select)

        section_label(parent, "Unassigned", self.fonts).grid(
            row=2, column=0, sticky="w", padx=16, pady=(4, 6)
        )
        self.unassigned_list = self._mount_list(parent, row=3, bottom=16)
        self.unassigned_list.bind("<<ListboxSelect>>", self._on_unassigned_select)
        self.unassigned_list.bind("<Double-Button-1>", lambda _event: self.assign_selected())

    def _build_organization(self, parent: ctk.CTkFrame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(6, weight=1)

        session_row = ctk.CTkFrame(parent, fg_color="transparent")
        session_row.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        session_row.columnconfigure(1, weight=1)
        muted_label(session_row, "New session", self.fonts).grid(row=0, column=0, padx=(0, 8))
        self.session_entry = self._entry(session_row, self.session_name_var)
        self.session_entry.grid(row=0, column=1, sticky="ew")
        self.session_entry.bind("<Return>", lambda _event: self.add_session())
        secondary_button(session_row, "Add session", self.add_session, self.fonts).grid(
            row=0, column=2, padx=(8, 0)
        )

        session_pick = ctk.CTkFrame(parent, fg_color="transparent")
        session_pick.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        session_pick.columnconfigure(1, weight=1)
        muted_label(session_pick, "Session", self.fonts).grid(row=0, column=0, padx=(0, 8))
        self.session_combo = self._combo(session_pick, lambda _value: self.refresh_groups())
        self.session_combo.grid(row=0, column=1, sticky="ew")
        secondary_button(session_pick, "Remove session", self.remove_session, self.fonts).grid(
            row=0, column=2, padx=(8, 0)
        )

        group_row = ctk.CTkFrame(parent, fg_color="transparent")
        group_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        group_row.columnconfigure(1, weight=1)
        muted_label(group_row, "New bucket", self.fonts).grid(row=0, column=0, padx=(0, 8))
        self.group_entry = self._entry(group_row, self.group_label_var)
        self.group_entry.grid(row=0, column=1, sticky="ew")
        self.group_entry.bind("<Return>", lambda _event: self.add_group())
        secondary_button(group_row, "Add bucket", self.add_group, self.fonts).grid(
            row=0, column=2, padx=(8, 0)
        )

        group_pick = ctk.CTkFrame(parent, fg_color="transparent")
        group_pick.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 12))
        group_pick.columnconfigure(1, weight=1)
        muted_label(group_pick, "Bucket", self.fonts).grid(row=0, column=0, padx=(0, 8))
        self.group_combo = self._combo(group_pick, lambda _value: self.refresh_group_contents())
        self.group_combo.grid(row=0, column=1, sticky="ew")
        remove_bucket = secondary_button(group_pick, "Remove bucket", self.remove_group, self.fonts)
        remove_bucket.configure(width=150)
        remove_bucket.grid(row=0, column=2, padx=(8, 0))

        action_row = ctk.CTkFrame(parent, fg_color="transparent")
        action_row.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 12))
        action_row.columnconfigure(0, weight=1)
        action_row.columnconfigure(1, weight=1)
        secondary_button(action_row, "Preview", self.preview_selected, self.fonts).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        primary_button(action_row, "Assign selected", self.assign_selected, self.fonts).grid(
            row=0, column=1, sticky="ew"
        )

        section_label(parent, "In this bucket", self.fonts).grid(
            row=5, column=0, sticky="w", padx=16, pady=(0, 6)
        )
        self.group_list = self._mount_list(parent, row=6, bottom=10)

        order_row = ctk.CTkFrame(parent, fg_color="transparent")
        order_row.grid(row=7, column=0, sticky="w", padx=16, pady=(0, 16))
        secondary_button(order_row, "Move up", lambda: self.move_selected(-1), self.fonts).pack(
            side="left"
        )
        secondary_button(order_row, "Move down", lambda: self.move_selected(1), self.fonts).pack(
            side="left", padx=(8, 0)
        )
        secondary_button(order_row, "Unassign", self.unassign_selected, self.fonts).pack(
            side="left", padx=(8, 0)
        )

    def _panel(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent,
            fg_color=PANEL,
            corner_radius=16,
            border_width=1,
            border_color=PANEL_BORDER,
        )

    def _entry(self, parent: ctk.CTkFrame, variable: tk.StringVar) -> ctk.CTkEntry:
        entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            fg_color=FIELD,
            border_color=PANEL_BORDER,
            border_width=1,
            text_color=TEXT,
            font=self.fonts.ui,
            corner_radius=10,
            height=36,
        )
        # A thin cyan edge only while the field is focused.
        entry.bind("<FocusIn>", lambda _event: entry.configure(border_color=ACCENT))
        entry.bind("<FocusOut>", lambda _event: entry.configure(border_color=PANEL_BORDER))
        return entry

    def _combo(self, parent: ctk.CTkFrame, command) -> ctk.CTkComboBox:
        return ctk.CTkComboBox(
            parent,
            values=[],
            command=command,
            state="readonly",
            fg_color=FIELD,
            border_color=PANEL_BORDER,
            button_color="#14313c",
            button_hover_color=ACCENT_DIM,
            dropdown_fg_color=PANEL,
            dropdown_hover_color=ACCENT_SOFT,
            dropdown_text_color=TEXT,
            text_color=TEXT,
            font=self.fonts.ui,
            dropdown_font=self.fonts.ui,
            corner_radius=10,
            border_width=1,
            height=36,
        )

    def _mount_list(self, parent: ctk.CTkFrame, row: int, bottom: int) -> tk.Listbox:
        """Scrolling list with a cyan edge while it has keyboard focus.

        CustomTkinter has no multi-select list, so this is a standard listbox
        painted to match the panels. Shift-click and extended selection stay
        available, which the assign and reorder actions depend on.
        """

        shell = ctk.CTkFrame(
            parent,
            fg_color=FIELD,
            corner_radius=12,
            border_width=1,
            border_color=PANEL_BORDER,
        )
        shell.grid(row=row, column=0, sticky="nsew", padx=16, pady=(0, bottom))
        shell.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)

        listbox = tk.Listbox(
            shell,
            selectmode=tk.EXTENDED,
            exportselection=False,
            activestyle="none",
            height=8,
            font=self.fonts.mono,
            bg=FIELD,
            fg=TEXT,
            selectbackground=ACCENT_SOFT,
            selectforeground=ACCENT,
            highlightthickness=0,
            relief="flat",
            borderwidth=0,
        )
        scroll = ctk.CTkScrollbar(
            shell,
            orientation="vertical",
            command=listbox.yview,
            fg_color=FIELD,
            button_color="#245566",
            button_hover_color=ACCENT,
            width=12,
        )
        listbox.configure(yscrollcommand=scroll.set)
        listbox.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=6)
        scroll.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=6)

        listbox.bind("<FocusIn>", lambda _event: shell.configure(border_color=ACCENT))
        listbox.bind("<FocusOut>", lambda _event: shell.configure(border_color=PANEL_BORDER))
        return listbox

    def browse_folder(self) -> None:
        current = Path(self.folder_var.get()).expanduser()
        initial = current if current.is_dir() else DEFAULT_FOLDER
        chosen = filedialog.askdirectory(
            title="Choose a screenshots folder",
            initialdir=str(initial if initial.is_dir() else REPO_ROOT),
        )
        if not chosen:
            return
        self.folder_var.set(chosen)
        self.load_folder()

    def load_folder(self, confirm: bool = True) -> None:
        if confirm and self.organizer.sessions:
            proceed = ask_yes_no(
                self.root,
                "Reload folder",
                "Reloading clears the sessions and buckets in this window. Continue?",
                self.fonts,
            )
            if not proceed:
                return
        folder = Path(self.folder_var.get()).expanduser()
        try:
            self.organizer.load_folder(folder)
        except (FileNotFoundError, OSError) as exc:
            show_message(self.root, "Screenshots folder", str(exc), self.fonts)
            self.status_var.set(str(exc))
            return
        self._close_preview()
        self.session_combo.set("")
        self.group_combo.set("")
        self.refresh_all()
        self.status_var.set(
            f"Loaded {len(self.organizer.shots)} file(s) from {folder}. "
            "Every file is listed, sorted by the time in its name."
        )

    def add_session(self) -> None:
        try:
            session = self.organizer.add_session(self.session_name_var.get())
        except ValueError as exc:
            show_message(self.root, "Add session", str(exc), self.fonts)
            return
        self.session_name_var.set("")
        self.refresh_sessions(select=session.name)
        self.status_var.set(f"Added session {session.name!r}. Add a bucket inside it.")
        self.group_entry.focus_set()
        self._refresh_open_preview()

    def add_group(self) -> None:
        session = self.current_session()
        if session is None:
            show_message(self.root, "Add bucket", "Add a session before adding a bucket.", self.fonts)
            return
        try:
            group = self.organizer.add_group(session, self.group_label_var.get())
        except ValueError as exc:
            show_message(self.root, "Add bucket", str(exc), self.fonts)
            return
        self.group_label_var.set("")
        self.refresh_groups(select=group.label)
        self.status_var.set(f"Added bucket {group.label!r}. Add another whenever you need a new pile.")
        self._refresh_open_preview()

    def remove_session(self) -> None:
        session = self.current_session()
        if session is None:
            return
        self.organizer.remove_session(session)
        self.refresh_sessions()
        self.status_var.set(f"Removed session {session.name!r}. Its screenshots are unassigned.")
        self._refresh_open_preview()

    def remove_group(self) -> None:
        session = self.current_session()
        group = self.current_group()
        if session is None or group is None:
            return
        self.organizer.remove_group(session, group)
        self.refresh_groups()
        self.refresh_shot_lists()
        self.status_var.set(f"Removed bucket {group.label!r}. Its screenshots are unassigned.")
        self._refresh_open_preview()

    def preview_selected(self) -> None:
        """Open the selected screenshot so it can be reviewed, then bucketed."""

        if not self.organizer.shots:
            show_message(self.root, "Preview", "This folder has no screenshots to preview.", self.fonts)
            return
        selected = self.selected_shots()
        if selected:
            start = selected[0]
        elif self.organizer.unassigned_shots():
            start = self.organizer.unassigned_shots()[0]
        else:
            start = self.organizer.shots[0]
        index = next(i for i, shot in enumerate(self.organizer.shots) if shot.path == start.path)
        if self._preview is not None and self._preview.winfo_exists():
            self._preview.show(index)
            self._preview.lift()
            return
        self._preview = PreviewWindow(
            self.root,
            self.fonts,
            self.organizer.shots,
            index,
            bucket_choices=self._bucket_choices,
            selected_bucket=self._selected_bucket_label,
            on_pick_bucket=self._pick_bucket,
            on_bucket=self._bucket_from_preview,
            on_show=self._select_shot,
            describe=self._preview_description,
            is_unassigned=self._shot_is_unassigned,
        )

    def _close_preview(self) -> None:
        if self._preview is not None and self._preview.winfo_exists():
            self._preview.window.destroy()
        self._preview = None

    def _bucket_choices(self) -> list[str]:
        """Every bucket. Include the session name when more than one session exists."""

        several_sessions = len(self.organizer.sessions) > 1
        labels: list[str] = []
        for session in self.organizer.sessions:
            for group in session.groups:
                if several_sessions:
                    labels.append(f"{session.name} / {group.label}")
                else:
                    labels.append(group.label)
        return labels

    def _selected_bucket_label(self) -> str:
        session = self.current_session()
        group = self.current_group()
        if session is None or group is None:
            return ""
        if len(self.organizer.sessions) > 1:
            return f"{session.name} / {group.label}"
        return group.label

    def _pick_bucket(self, label: str) -> None:
        """Point the main window at the bucket chosen in the preview."""

        several_sessions = len(self.organizer.sessions) > 1
        for session in self.organizer.sessions:
            for group in session.groups:
                text = f"{session.name} / {group.label}" if several_sessions else group.label
                if text != label:
                    continue
                self.refresh_sessions(select=session.name)
                self.refresh_groups(select=group.label)
                return

    def _refresh_open_preview(self) -> None:
        if self._preview is not None and self._preview.winfo_exists():
            self._preview.refresh_buckets()

    def _bucket_from_preview(self, shot: Shot) -> bool:
        if self._preview is not None and self._preview.winfo_exists():
            choice = self._preview._bucket_menu.get()
            if choice and choice != "No buckets yet":
                self._pick_bucket(choice)
        session = self.current_session()
        group = self.current_group()
        if session is None or group is None:
            show_message(self.root, "Bucket", "Add a bucket first, then choose it in the preview.", self.fonts)
            return False
        moved = self.organizer.assign([shot], group)
        self.refresh_shot_lists()
        self.refresh_group_contents()
        self._select_shot(shot)
        if moved:
            self.status_var.set(f"Bucketed {shot.filename} into {session.name} / {group.label}.")
        else:
            self.status_var.set(f"{shot.filename} is already in {session.name} / {group.label}.")
        return True

    def _preview_description(self, shot: Shot) -> str:
        label = self.organizer.assignment_label(shot)
        if label:
            return f"Bucketed in {label}. Export assigned to Word includes this file."
        return "Unassigned. Choose a bucket below, then drop this screenshot into it."

    def _shot_is_unassigned(self, shot: Shot) -> bool:
        return self.organizer.assignment_label(shot) is None

    def _select_shot(self, shot: Shot) -> None:
        """Highlight the shot being previewed in the full list."""

        self.unassigned_list.selection_clear(0, tk.END)
        self.all_list.selection_clear(0, tk.END)
        for index, item in enumerate(self._all_view):
            if item.path == shot.path:
                self.all_list.selection_set(index)
                self.all_list.see(index)
                self.all_list.activate(index)
                return

    def assign_selected(self) -> None:
        group = self.current_group()
        if group is None:
            show_message(self.root, "Assign", "Choose a session and a bucket first.", self.fonts)
            return
        shots = self.selected_shots()
        if not shots:
            show_message(
                self.root,
                "Assign",
                "Select one or more screenshots in the all-files list or the unassigned list.",
                self.fonts,
            )
            return
        moved = self.organizer.assign(shots, group)
        self.refresh_shot_lists()
        self.refresh_group_contents()
        session = self.current_session()
        session_name = session.name if session is not None else ""
        self.status_var.set(
            f"Assigned {moved} screenshot(s) to {session_name} / {group.label}."
        )

    def unassign_selected(self) -> None:
        group = self.current_group()
        if group is None:
            return
        shots = [self._group_view[index] for index in self.group_list.curselection()]
        if not shots:
            show_message(self.root, "Unassign", "Select a screenshot in this bucket first.", self.fonts)
            return
        self.organizer.unassign(shots)
        self.refresh_shot_lists()
        self.refresh_group_contents()
        self.status_var.set(f"Returned {len(shots)} screenshot(s) to unassigned.")

    def move_selected(self, delta: int) -> None:
        group = self.current_group()
        if group is None:
            return
        selection = list(self.group_list.curselection())
        if len(selection) != 1:
            show_message(self.root, "Reorder", "Select one screenshot in this bucket to move it.", self.fonts)
            return
        new_index = self.organizer.move(group, selection[0], delta)
        self.refresh_group_contents()
        self.group_list.selection_set(new_index)
        self.group_list.activate(new_index)
        self.group_list.see(new_index)

    def export_word(self) -> None:
        if not self.organizer.sessions:
            show_message(self.root, "Export", "Add a session before exporting.", self.fonts)
            return
        assigned = sum(
            len(group.shots) for session in self.organizer.sessions for group in session.groups
        )
        if assigned == 0:
            show_message(
                self.root,
                "Export",
                "Add a screenshot to a bucket before exporting. The Word document has one section per bucket.",
                self.fonts,
            )
            return
        unassigned = self.organizer.unassigned_shots()
        if unassigned:
            proceed = ask_yes_no(
                self.root,
                "Unassigned screenshots",
                f"{len(unassigned)} screenshot(s) are still unassigned and will not "
                "appear in the document. Export anyway?",
                self.fonts,
            )
            if not proceed:
                return
        reports = REPO_ROOT / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        chosen = filedialog.asksaveasfilename(
            title="Export Word document",
            defaultextension=".docx",
            filetypes=[("Word document", "*.docx")],
            initialdir=str(reports),
            initialfile="screenshot_organizer.docx",
        )
        if not chosen:
            return
        destination = Path(chosen)
        try:
            export_document(self.organizer.sessions, destination)
        except RuntimeError as exc:
            show_message(self.root, "Export", str(exc), self.fonts)
            return
        except OSError as exc:
            show_message(self.root, "Export", f"Could not write the document: {exc}", self.fonts)
            return
        self.status_var.set(f"Exported {destination}")
        show_message(self.root, "Export", f"Wrote {destination}", self.fonts)

    def selected_shots(self) -> list[Shot]:
        """Screenshots selected in either source list, without duplicates."""

        chosen: list[Shot] = []
        seen: set[Path] = set()
        for index in self.all_list.curselection():
            shot = self._all_view[index]
            if shot.path not in seen:
                chosen.append(shot)
                seen.add(shot.path)
        for index in self.unassigned_list.curselection():
            shot = self._unassigned_view[index]
            if shot.path not in seen:
                chosen.append(shot)
                seen.add(shot.path)
        return chosen

    def current_session(self) -> Session | None:
        name = self.session_combo.get()
        for session in self.organizer.sessions:
            if session.name == name:
                return session
        return None

    def current_group(self) -> Group | None:
        session = self.current_session()
        if session is None:
            return None
        label = self.group_combo.get()
        for group in session.groups:
            if group.label == label:
                return group
        return None

    def refresh_all(self) -> None:
        self.refresh_sessions()
        self.refresh_shot_lists()

    def refresh_sessions(self, select: str | None = None) -> None:
        names = [session.name for session in self.organizer.sessions]
        self._set_combo(self.session_combo, names, select)
        self.refresh_groups()
        self.refresh_shot_lists()

    def refresh_groups(self, select: str | None = None) -> None:
        session = self.current_session()
        labels = [group.label for group in session.groups] if session else []
        self._set_combo(self.group_combo, labels, select)
        self.refresh_group_contents()

    def _set_combo(self, combo: ctk.CTkComboBox, values: list[str], select: str | None) -> None:
        # CTkComboBox has no current() index. The visible text is the selection.
        combo.configure(values=values)
        if not values:
            combo.set("")
            return
        current = select or combo.get()
        if current not in values:
            current = values[0]
        combo.set(current)

    def refresh_shot_lists(self) -> None:
        self._fill_list(
            self.all_list,
            self.organizer.shots,
            lambda shot: self._format_shot(shot, self.organizer.assignment_label(shot)),
        )
        self._all_view = list(self.organizer.shots)
        unassigned = self.organizer.unassigned_shots()
        self._fill_list(self.unassigned_list, unassigned, lambda shot: self._format_shot(shot, None))
        self._unassigned_view = unassigned

    def refresh_group_contents(self) -> None:
        group = self.current_group()
        shots = list(group.shots) if group else []
        self._fill_list(self.group_list, shots, lambda shot: self._format_shot(shot, None))
        self._group_view = shots

    def _fill_list(self, listbox: tk.Listbox, shots: list[Shot], label) -> None:
        listbox.delete(0, tk.END)
        for shot in shots:
            listbox.insert(tk.END, label(shot))

    def _format_shot(self, shot: Shot, assignment: str | None) -> str:
        if assignment:
            return f"{shot.clock_text}  {shot.filename}  ->  {assignment}"
        return f"{shot.clock_text}  {shot.filename}"

    def _on_all_select(self, _event: object) -> None:
        # One source of selection at a time, so Assign is not surprising.
        if self.all_list.curselection():
            self.unassigned_list.selection_clear(0, tk.END)

    def _on_unassigned_select(self, _event: object) -> None:
        if self.unassigned_list.curselection():
            self.all_list.selection_clear(0, tk.END)


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    # The display is a normal desktop DPI. Leave scaling at 1 so padding stays
    # what the layout was drawn for.
    ctk.set_widget_scaling(1.0)
    ctk.set_window_scaling(1.0)
    root = ctk.CTk()
    OrganizerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
