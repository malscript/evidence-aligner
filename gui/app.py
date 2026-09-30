#!/usr/bin/env python3
"""Desktop organizer for timestamped screenshots.

Choose a folder (sample_images/ by default), group the files into sessions,
and export a Word document. Run from the repository root:

    pip install -r requirements.txt
    python gui/app.py

Tkinter ships with Python on most installs. Debian and Ubuntu split it out:

    sudo apt install python3-tk
"""

from __future__ import annotations

import sys
from pathlib import Path


try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    sys.stderr.write(
        "Tkinter is required but is not installed.\n"
        "On Debian/Ubuntu install it with: sudo apt install python3-tk\n"
    )
    raise SystemExit(1)

# `python gui/app.py` puts this directory on sys.path, so the sibling modules
# import directly. That keeps the launch command a plain script.
from export_docx import export_document
from model import Group, Organizer, Session, Shot


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FOLDER = REPO_ROOT / "sample_images"


class OrganizerApp:
    """Tkinter front end over Organizer. All edits happen in memory."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.organizer = Organizer()
        self.folder_var = tk.StringVar(value=str(DEFAULT_FOLDER))
        self.session_name_var = tk.StringVar()
        self.group_label_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Choose a screenshots folder to begin.")

        # Parallel to the listboxes, so a selection index maps back to a Shot.
        self._all_view: list[Shot] = []
        self._unassigned_view: list[Shot] = []
        self._group_view: list[Shot] = []

        root.title("Screenshot organizer")
        root.minsize(980, 640)
        root.geometry("1100x720")
        self._build()
        self.load_folder(confirm=False)

    def _build(self) -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.rowconfigure(2, weight=1)
        outer.columnconfigure(0, weight=1)

        ttk.Label(
            outer,
            text="Group timestamped screenshots into sessions, then export a Word document.",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        folder_row = ttk.Frame(outer)
        folder_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        folder_row.columnconfigure(1, weight=1)
        ttk.Label(folder_row, text="Screenshots folder").grid(row=0, column=0, padx=(0, 8))
        folder_entry = ttk.Entry(folder_row, textvariable=self.folder_var)
        folder_entry.grid(row=0, column=1, sticky="ew")
        folder_entry.bind("<Return>", lambda _event: self.load_folder())
        ttk.Button(folder_row, text="Browse", command=self.browse_folder).grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Button(folder_row, text="Reload", command=self.load_folder).grid(
            row=0, column=3, padx=(8, 0)
        )

        paned = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
        paned.grid(row=2, column=0, sticky="nsew")

        left = ttk.Frame(paned, padding=(0, 0, 8, 0))
        right = ttk.Frame(paned, padding=(8, 0, 0, 0))
        paned.add(left, weight=3)
        paned.add(right, weight=2)
        self._build_lists(left)
        self._build_organization(right)

        bottom = ttk.Frame(outer)
        bottom.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        bottom.columnconfigure(1, weight=1)
        ttk.Button(bottom, text="Export to Word", command=self.export_word).grid(
            row=0, column=0, padx=(0, 12)
        )
        ttk.Label(bottom, textvariable=self.status_var).grid(row=0, column=1, sticky="w")

    def _build_lists(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=3)
        parent.rowconfigure(3, weight=2)
        parent.columnconfigure(0, weight=1)

        ttk.Label(
            parent,
            text="All screenshots, sorted by filename time",
        ).grid(row=0, column=0, sticky="w")
        self.all_list = self._mount_list(parent, row=1, pady=(4, 8))
        self.all_list.bind("<<ListboxSelect>>", self._on_all_select)

        ttk.Label(parent, text="Unassigned").grid(row=2, column=0, sticky="w")
        self.unassigned_list = self._mount_list(parent, row=3, pady=(4, 0))
        self.unassigned_list.bind("<<ListboxSelect>>", self._on_unassigned_select)
        self.unassigned_list.bind("<Double-Button-1>", lambda _event: self.assign_selected())

    def _build_organization(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(6, weight=1)

        session_row = ttk.Frame(parent)
        session_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        session_row.columnconfigure(1, weight=1)
        ttk.Label(session_row, text="New session").grid(row=0, column=0, padx=(0, 8))
        self.session_entry = ttk.Entry(session_row, textvariable=self.session_name_var)
        self.session_entry.grid(row=0, column=1, sticky="ew")
        self.session_entry.bind("<Return>", lambda _event: self.add_session())
        ttk.Button(session_row, text="Add session", command=self.add_session).grid(
            row=0, column=2, padx=(8, 0)
        )

        session_pick = ttk.Frame(parent)
        session_pick.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        session_pick.columnconfigure(1, weight=1)
        ttk.Label(session_pick, text="Session").grid(row=0, column=0, padx=(0, 8))
        self.session_combo = ttk.Combobox(session_pick, state="readonly")
        self.session_combo.grid(row=0, column=1, sticky="ew")
        self.session_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_groups())
        ttk.Button(session_pick, text="Remove session", command=self.remove_session).grid(
            row=0, column=2, padx=(8, 0)
        )

        group_row = ttk.Frame(parent)
        group_row.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        group_row.columnconfigure(1, weight=1)
        ttk.Label(group_row, text="New group").grid(row=0, column=0, padx=(0, 8))
        self.group_entry = ttk.Entry(group_row, textvariable=self.group_label_var)
        self.group_entry.grid(row=0, column=1, sticky="ew")
        self.group_entry.bind("<Return>", lambda _event: self.add_group())
        ttk.Button(group_row, text="Add group", command=self.add_group).grid(
            row=0, column=2, padx=(8, 0)
        )

        group_pick = ttk.Frame(parent)
        group_pick.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        group_pick.columnconfigure(1, weight=1)
        ttk.Label(group_pick, text="Group").grid(row=0, column=0, padx=(0, 8))
        self.group_combo = ttk.Combobox(group_pick, state="readonly")
        self.group_combo.grid(row=0, column=1, sticky="ew")
        self.group_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_group_contents())
        ttk.Button(group_pick, text="Remove group", command=self.remove_group).grid(
            row=0, column=2, padx=(8, 0)
        )

        ttk.Button(parent, text="Assign selected", command=self.assign_selected).grid(
            row=4, column=0, sticky="w", pady=(0, 8)
        )

        ttk.Label(parent, text="In this group").grid(row=5, column=0, sticky="w")
        self.group_list = self._mount_list(parent, row=6, pady=(4, 8))

        order_row = ttk.Frame(parent)
        order_row.grid(row=7, column=0, sticky="w")
        ttk.Button(order_row, text="Move up", command=lambda: self.move_selected(-1)).pack(
            side=tk.LEFT
        )
        ttk.Button(order_row, text="Move down", command=lambda: self.move_selected(1)).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(order_row, text="Unassign", command=self.unassign_selected).pack(
            side=tk.LEFT, padx=(8, 0)
        )

    def _mount_list(self, parent: ttk.Frame, row: int, pady: tuple[int, int]) -> tk.Listbox:
        """Put a scrolling listbox in a grid row and return the listbox."""

        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="nsew", pady=pady)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        listbox = tk.Listbox(
            frame,
            selectmode=tk.EXTENDED,
            exportselection=False,
            activestyle="dotbox",
            height=8,
            font="TkFixedFont",
        )
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
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
            proceed = messagebox.askyesno(
                "Reload folder",
                "Reloading clears the sessions and groups in this window. Continue?",
            )
            if not proceed:
                return
        folder = Path(self.folder_var.get()).expanduser()
        try:
            self.organizer.load_folder(folder)
        except (FileNotFoundError, OSError) as exc:
            messagebox.showerror("Screenshots folder", str(exc))
            self.status_var.set(str(exc))
            return
        self.session_combo.set("")
        self.group_combo.set("")
        self.refresh_all()
        self.status_var.set(
            f"Loaded {len(self.organizer.shots)} file(s) from {folder}. "
            "Every file is listed, sorted by the HHMMSS time in its name."
        )

    def add_session(self) -> None:
        try:
            session = self.organizer.add_session(self.session_name_var.get())
        except ValueError as exc:
            messagebox.showwarning("Add session", str(exc))
            return
        self.session_name_var.set("")
        self.refresh_sessions(select=session.name)
        self.status_var.set(f"Added session {session.name!r}.")
        self.group_entry.focus_set()

    def add_group(self) -> None:
        session = self.current_session()
        if session is None:
            messagebox.showwarning("Add group", "Add a session before adding a group.")
            return
        try:
            group = self.organizer.add_group(session, self.group_label_var.get())
        except ValueError as exc:
            messagebox.showwarning("Add group", str(exc))
            return
        self.group_label_var.set("")
        self.refresh_groups(select=group.label)
        self.status_var.set(f"Added group {group.label!r} to {session.name!r}.")

    def remove_session(self) -> None:
        session = self.current_session()
        if session is None:
            return
        self.organizer.remove_session(session)
        self.refresh_sessions()
        self.status_var.set(f"Removed session {session.name!r}. Its screenshots are unassigned.")

    def remove_group(self) -> None:
        session = self.current_session()
        group = self.current_group()
        if session is None or group is None:
            return
        self.organizer.remove_group(session, group)
        self.refresh_groups()
        self.refresh_shot_lists()
        self.status_var.set(f"Removed group {group.label!r}. Its screenshots are unassigned.")

    def assign_selected(self) -> None:
        group = self.current_group()
        if group is None:
            messagebox.showwarning("Assign", "Choose a session and a group first.")
            return
        shots = self.selected_shots()
        if not shots:
            messagebox.showwarning(
                "Assign",
                "Select one or more screenshots in the all-files list or the unassigned list.",
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
            messagebox.showwarning("Unassign", "Select a screenshot in this group first.")
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
            messagebox.showwarning("Reorder", "Select one screenshot in this group to move it.")
            return
        new_index = self.organizer.move(group, selection[0], delta)
        self.refresh_group_contents()
        self.group_list.selection_set(new_index)
        self.group_list.activate(new_index)
        self.group_list.see(new_index)

    def export_word(self) -> None:
        if not self.organizer.sessions:
            messagebox.showwarning("Export", "Add a session before exporting.")
            return
        unassigned = self.organizer.unassigned_shots()
        if unassigned:
            proceed = messagebox.askyesno(
                "Unassigned screenshots",
                f"{len(unassigned)} screenshot(s) are still unassigned and will not "
                "appear in the document. Export anyway?",
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
            messagebox.showerror("Export", str(exc))
            return
        except OSError as exc:
            messagebox.showerror("Export", f"Could not write the document: {exc}")
            return
        self.status_var.set(f"Exported {destination}")
        messagebox.showinfo("Export", f"Wrote {destination}")

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
        index = self.session_combo.current()
        if index < 0 or index >= len(self.organizer.sessions):
            return None
        return self.organizer.sessions[index]

    def current_group(self) -> Group | None:
        session = self.current_session()
        if session is None:
            return None
        index = self.group_combo.current()
        if index < 0 or index >= len(session.groups):
            return None
        return session.groups[index]

    def refresh_all(self) -> None:
        self.refresh_sessions()
        self.refresh_shot_lists()

    def refresh_sessions(self, select: str | None = None) -> None:
        names = [session.name for session in self.organizer.sessions]
        self.session_combo["values"] = names
        if not names:
            self.session_combo.set("")
            self.refresh_groups()
            self.refresh_shot_lists()
            return
        current = select or self.session_combo.get()
        if current not in names:
            current = names[0]
        self.session_combo.current(names.index(current))
        self.refresh_groups()
        self.refresh_shot_lists()

    def refresh_groups(self, select: str | None = None) -> None:
        session = self.current_session()
        labels = [group.label for group in session.groups] if session else []
        self.group_combo["values"] = labels
        if not labels:
            self.group_combo.set("")
            self.refresh_group_contents()
            return
        current = select or self.group_combo.get()
        if current not in labels:
            current = labels[0]
        self.group_combo.current(labels.index(current))
        self.refresh_group_contents()

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
    root = tk.Tk()
    OrganizerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
