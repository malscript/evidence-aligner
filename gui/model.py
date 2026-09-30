"""In-memory organization of timestamped screenshot files.

A screenshot is any file in a chosen folder. Its clock time is read from the
filename. Two shapes are recognized:

- yyyy-MM-dd HH_mm_ss, as in 2026-09-30 14_30_22.png
- HHMMSS, as in shot_143022.png (14:30:22)

Sessions and groups are created by the user; this module only stores them
and keeps the screenshot order inside each group.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# Capture pattern yyyy-MM-dd HH_mm_ss. A space or underscore may separate the
# date from the clock. Digits must not be part of a longer number.
_CAPTURED_AT = re.compile(
    r"(?<!\d)(\d{4})-(\d{2})-(\d{2})[ _](\d{2})_(\d{2})_(\d{2})(?!\d)"
)
# Six clock digits bounded by non-digits, so shot_143022.png matches and a
# longer digit run (shot_1430229.png) does not.
_TIMESTAMP = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)")


@dataclass
class Shot:
    """One file from the screenshots folder."""

    path: Path
    timestamp: tuple[int, int, int] | None
    # Set when the filename includes yyyy-MM-dd. Clock-only names leave this empty.
    captured_on: tuple[int, int, int] | None = None

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def clock_text(self) -> str:
        if self.timestamp is None:
            return "--:--:--"
        hour, minute, second = self.timestamp
        clock = f"{hour:02d}:{minute:02d}:{second:02d}"
        if self.captured_on is None:
            return clock
        year, month, day = self.captured_on
        return f"{year:04d}-{month:02d}-{day:02d} {clock}"

    def caption(self) -> str:
        if self.timestamp is None:
            return f"{self.filename} — no timestamp in filename"
        return f"{self.filename} — {self.clock_text}"


@dataclass
class Group:
    """A labeled, ordered list of screenshots inside one session."""

    label: str
    shots: list[Shot] = field(default_factory=list)


@dataclass
class Session:
    """A named block of groups. Export writes one heading per session."""

    name: str
    groups: list[Group] = field(default_factory=list)


@dataclass
class Organizer:
    """Screenshots plus the sessions the user has built in this run."""

    shots: list[Shot] = field(default_factory=list)
    sessions: list[Session] = field(default_factory=list)

    def load_folder(self, folder: Path) -> None:
        """Replace the file list. Clears sessions, because they point at the old files."""

        if not folder.is_dir():
            raise FileNotFoundError(f"Screenshots folder not found: {folder}")

        shots: list[Shot] = []
        for path in folder.iterdir():
            # Every real file counts, image or not. Skip directories and
            # hidden files so editor debris does not show up as a screenshot.
            if not path.is_file() or path.name.startswith("."):
                continue
            captured_on, timestamp = parse_filename_timestamp(path.name)
            shots.append(Shot(path=path, timestamp=timestamp, captured_on=captured_on))
        shots.sort(key=shot_sort_key)
        self.shots = shots
        self.sessions = []

    def add_session(self, name: str) -> Session:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Enter a session name.")
        if any(session.name == cleaned for session in self.sessions):
            raise ValueError(f"A session named {cleaned!r} already exists.")
        session = Session(name=cleaned)
        self.sessions.append(session)
        return session

    def add_group(self, session: Session, label: str) -> Group:
        cleaned = label.strip()
        if not cleaned:
            raise ValueError("Enter a bucket name.")
        if any(group.label == cleaned for group in session.groups):
            raise ValueError(f"This session already has a bucket named {cleaned!r}.")
        group = Group(label=cleaned)
        session.groups.append(group)
        return group

    def remove_session(self, session: Session) -> None:
        self.sessions = [item for item in self.sessions if item is not session]

    def remove_group(self, session: Session, group: Group) -> None:
        session.groups = [item for item in session.groups if item is not group]

    def assign(self, shots: list[Shot], group: Group) -> int:
        """Move shots into group, appending them in timestamp order.

        Shots already in this group stay where the user placed them. Shots
        coming from another group leave that group first. Returns how many
        shots were appended.
        """

        fresh: list[Shot] = []
        for shot in shots:
            current = self.group_containing(shot)
            if current is group:
                continue
            if current is not None:
                current.shots = [item for item in current.shots if item.path != shot.path]
            fresh.append(shot)
        fresh.sort(key=shot_sort_key)
        group.shots.extend(fresh)
        return len(fresh)

    def unassign(self, shots: list[Shot]) -> None:
        paths = {shot.path for shot in shots}
        for session in self.sessions:
            for group in session.groups:
                group.shots = [item for item in group.shots if item.path not in paths]

    def move(self, group: Group, index: int, delta: int) -> int:
        """Swap one screenshot up or down. Returns the new index."""

        new_index = index + delta
        if index < 0 or index >= len(group.shots):
            return index
        if new_index < 0 or new_index >= len(group.shots):
            return index
        shot = group.shots.pop(index)
        group.shots.insert(new_index, shot)
        return new_index

    def group_containing(self, shot: Shot) -> Group | None:
        for session in self.sessions:
            for group in session.groups:
                if any(item.path == shot.path for item in group.shots):
                    return group
        return None

    def assignment_label(self, shot: Shot) -> str | None:
        for session in self.sessions:
            for group in session.groups:
                if any(item.path == shot.path for item in group.shots):
                    return f"{session.name} / {group.label}"
        return None

    def unassigned_shots(self) -> list[Shot]:
        assigned = {
            shot.path
            for session in self.sessions
            for group in session.groups
            for shot in group.shots
        }
        return [shot for shot in self.shots if shot.path not in assigned]


def parse_filename_timestamp(
    filename: str,
) -> tuple[tuple[int, int, int] | None, tuple[int, int, int] | None]:
    """Return (year, month, day) and (hour, minute, second).

    A dated name such as 2026-09-30 14_30_22.png fills both. A clock-only name
    such as shot_143022.png fills the time and leaves the date empty. Invalid
    calendar dates and clock values count as missing.
    """

    dated = _CAPTURED_AT.search(filename)
    if dated is not None:
        year, month, day, hour, minute, second = (int(part) for part in dated.groups())
        if _real_moment(year, month, day, hour, minute, second):
            return (year, month, day), (hour, minute, second)

    match = _TIMESTAMP.search(filename)
    if match is None:
        return None, None
    hour, minute, second = (int(part) for part in match.groups())
    if hour > 23 or minute > 59 or second > 59:
        return None, None
    return None, (hour, minute, second)


def _real_moment(year: int, month: int, day: int, hour: int, minute: int, second: int) -> bool:
    try:
        datetime(year, month, day, hour, minute, second)
    except ValueError:
        return False
    return True


def shot_sort_key(shot: Shot) -> tuple:
    """Timed files first. Dated names sort by calendar day, then clock time.

    Clock-only names sort by time of day among themselves. Untimed files follow, by name.
    """

    if shot.timestamp is None:
        return (1, 0, 0, 0, 0, 0, 0, shot.filename.lower())
    hour, minute, second = shot.timestamp
    if shot.captured_on is None:
        return (0, 0, 0, 0, hour, minute, second, shot.filename.lower())
    year, month, day = shot.captured_on
    return (0, year, month, day, hour, minute, second, shot.filename.lower())
