#!/usr/bin/env python3
"""Align clock-time screenshots with a transcript of timed segments.

Transcript times are seconds from the moment a recording started. Screenshot
times are wall-clock values (HH:MM:SS). The recording start clock time is
the bridge between those two clocks.

Each segment owns a half-open window [start, end). A screenshot belongs to
the segment that contains its offset from the recording start. Screenshots
that miss every window are reported on their own, outside the topics.

Standard library only. Run from the repository root:

    python aligner.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


# Defaults match the synthetic sample set. Override them from the command line.
DEFAULT_RECORDING_START = "14:00:00"
DEFAULT_TRANSCRIPT = Path("sample_data/transcript.json")
DEFAULT_SCREENSHOTS = Path("sample_data/screenshots.csv")
DEFAULT_OUTPUT = Path("reports/evidence_report.md")

SECONDS_PER_DAY = 24 * 60 * 60
SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass
class Segment:
    """One transcript slice, plus the screenshots that landed inside it."""

    source_index: int
    start_seconds: float
    end_seconds: float
    topic: str
    text: str
    screenshots: list["Screenshot"] = field(default_factory=list)


@dataclass
class Screenshot:
    """One valid screenshot row, already converted to an offset from start."""

    source_row: int
    filename: str
    clock_time: str
    offset_seconds: float


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        recording_start = parse_clock_time(args.recording_start)
    except ValueError as exc:
        print(f"error: recording start {exc}", file=sys.stderr)
        return 1

    transcript_path = resolve_path(args.transcript)
    screenshots_path = resolve_path(args.screenshots)
    output_path = resolve_path(args.output, prefer_script_dir=False)

    segments, transcript_errors = load_transcript(
        transcript_path, args.duration_seconds
    )
    if transcript_errors:
        for message in transcript_errors:
            print(f"error: {message}", file=sys.stderr)
        return 1

    screenshots, row_errors = load_screenshots(screenshots_path, recording_start)
    if row_errors and screenshots is None:
        # The file itself could not be read. Row-level problems are different:
        # those still produce a report, with the bad rows listed in it.
        for message in row_errors:
            print(f"error: {message}", file=sys.stderr)
        return 1

    assign_screenshots(segments, screenshots or [])
    report = render_report(
        recording_start=args.recording_start,
        segments=segments,
        screenshots=screenshots or [],
        row_errors=row_errors,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    for message in row_errors:
        print(f"warning: {message}", file=sys.stderr)

    assigned = sum(len(segment.screenshots) for segment in segments)
    print(
        f"Wrote {output_path} "
        f"({assigned} assigned, {len(screenshots or []) - assigned} outside segments)"
    )
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Align timestamped screenshots with a transcript and write a "
            "Markdown report grouped by topic."
        )
    )
    parser.add_argument(
        "--recording-start",
        default=DEFAULT_RECORDING_START,
        help="Clock time when the recording began, as HH:MM:SS (default: %(default)s)",
    )
    parser.add_argument(
        "--transcript",
        type=Path,
        default=DEFAULT_TRANSCRIPT,
        help="Transcript JSON path (default: %(default)s)",
    )
    parser.add_argument(
        "--screenshots",
        type=Path,
        default=DEFAULT_SCREENSHOTS,
        help="Screenshot CSV path (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Markdown report path (default: %(default)s)",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=None,
        help=(
            "Used only when the last segment has no end_seconds. "
            "The last window then ends at this many seconds after the recording start."
        ),
    )
    return parser.parse_args(argv)


def resolve_path(path: Path, prefer_script_dir: bool = True) -> Path:
    """Find a default sample file even when the working directory is not the repo root.

    Explicit paths that already exist are used as given. Relative defaults that
    are missing from the working directory are tried beside this script.
    Output paths stay relative to the working directory so the report lands
    where the command was run.
    """

    if path.is_absolute() or path.exists() or not prefer_script_dir:
        return path
    beside_script = SCRIPT_DIR / path
    if beside_script.exists():
        return beside_script
    return path


def parse_clock_time(value: str) -> int:
    """Return seconds since midnight for a strict HH:MM:SS clock time."""

    text = value.strip()
    parts = text.split(":")
    if len(parts) != 3 or any(len(part) != 2 or not part.isdigit() for part in parts):
        raise ValueError(f"'{value}' is not a 24-hour HH:MM:SS time")
    hours, minutes, seconds = (int(part) for part in parts)
    if hours > 23 or minutes > 59 or seconds > 59:
        raise ValueError(f"'{value}' is not a valid clock time")
    return hours * 3600 + minutes * 60 + seconds


def format_clock_time(total_seconds: float) -> str:
    """Format a seconds-since-midnight value as HH:MM:SS, wrapping at midnight."""

    whole = int(round(total_seconds)) % SECONDS_PER_DAY
    hours, remainder = divmod(whole, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_offset(seconds: float) -> str:
    """Format a signed duration as HH:MM:SS."""

    sign = "-" if seconds < 0 else ""
    whole = int(round(abs(seconds)))
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{sign}{hours:02d}:{minutes:02d}:{secs:02d}"


def clock_plus(recording_start: str, delta_seconds: float) -> str:
    return format_clock_time(parse_clock_time(recording_start) + delta_seconds)


def load_transcript(
    path: Path, duration_seconds: float | None
) -> tuple[list[Segment], list[str]]:
    """Load segments and resolve each one's time window.

    Windows are half-open: a segment covers start_seconds <= t < end_seconds.
    When end_seconds is omitted, the window runs up to the next segment. The
    final segment needs its own end_seconds, or --duration-seconds.
    """

    if duration_seconds is not None and duration_seconds <= 0:
        return [], ["--duration-seconds must be greater than zero"]

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], [f"transcript file not found: {path}"]
    except json.JSONDecodeError as exc:
        return [], [f"transcript is not valid JSON: {exc}"]
    except OSError as exc:
        return [], [f"could not read transcript: {exc}"]

    if not isinstance(payload, list):
        return [], ["transcript must be a JSON list of segments"]
    if not payload:
        return [], ["transcript contains no segments"]

    raw_segments: list[Segment] = []
    errors: list[str] = []
    # end_seconds is filled in after we know the time order. None marks
    # "infer this end from the following segment".
    pending_ends: list[float | None] = []

    for index, item in enumerate(payload, start=1):
        label = f"transcript segment {index}"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        start, start_error = require_number(item.get("start_seconds"), f"{label} start_seconds")
        topic, topic_error = require_text(item.get("topic"), f"{label} topic")
        text, text_error = require_text(item.get("text"), f"{label} text")
        for message in (start_error, topic_error, text_error):
            if message:
                errors.append(message)
        if start is None or topic is None or text is None:
            continue
        if start < 0:
            errors.append(f"{label} start_seconds must be zero or greater")
            continue

        end: float | None
        if "end_seconds" in item and item["end_seconds"] is not None:
            end, end_error = require_number(item["end_seconds"], f"{label} end_seconds")
            if end_error:
                errors.append(end_error)
                continue
            if end is not None and end <= start:
                errors.append(f"{label} end_seconds must be greater than start_seconds")
                continue
        else:
            end = None

        raw_segments.append(
            Segment(
                source_index=index,
                start_seconds=start,
                end_seconds=end if end is not None else start,
                topic=topic,
                text=text,
            )
        )
        pending_ends.append(end)

    if errors:
        return [], errors

    order = sorted(range(len(raw_segments)), key=lambda i: (raw_segments[i].start_seconds, raw_segments[i].source_index))
    segments = [raw_segments[i] for i in order]
    ends = [pending_ends[i] for i in order]

    for position, segment in enumerate(segments):
        inferred = ends[position]
        if inferred is None:
            if position + 1 < len(segments):
                inferred = segments[position + 1].start_seconds
            elif duration_seconds is not None:
                inferred = duration_seconds
            else:
                errors.append(
                    f"transcript segment {segment.source_index} is the last segment "
                    "and needs end_seconds or --duration-seconds"
                )
                continue
            if inferred <= segment.start_seconds:
                errors.append(
                    f"transcript segment {segment.source_index} has an empty window; "
                    "the following segment must start later, or --duration-seconds "
                    "must be greater than this segment's start"
                )
                continue
        segment.end_seconds = inferred

    if errors:
        return [], errors

    for previous, current in zip(segments, segments[1:]):
        if current.start_seconds < previous.end_seconds:
            errors.append(
                f"transcript segments {previous.source_index} and {current.source_index} "
                f"overlap between {current.start_seconds:g}s and {previous.end_seconds:g}s"
            )
    if errors:
        return [], errors
    return segments, []


def load_screenshots(
    path: Path, recording_start_seconds: int
) -> tuple[list[Screenshot] | None, list[str]]:
    """Read screenshot rows.

    A fatal file problem returns ``(None, errors)``. Bad data rows are skipped
    and described in ``errors`` while the valid rows are still returned, so
    one broken line does not throw away the rest of the file.
    """

    try:
        handle = path.open(newline="", encoding="utf-8-sig")
    except FileNotFoundError:
        return None, [f"screenshots file not found: {path}"]
    except OSError as exc:
        return None, [f"could not read screenshots: {exc}"]

    screenshots: list[Screenshot] = []
    errors: list[str] = []
    with handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return None, [f"{path} is missing a header row with filename and clock_time"]
        fieldnames = [name.strip() for name in reader.fieldnames if name]
        if "filename" not in fieldnames or "clock_time" not in fieldnames:
            found = ", ".join(fieldnames) if fieldnames else "(none)"
            return None, [
                f"{path} must have filename and clock_time columns (found: {found})"
            ]

        for row_number, row in enumerate(reader, start=2):
            normalized = {(key or "").strip(): (value or "").strip() for key, value in row.items()}
            if not any(normalized.values()):
                continue
            filename = normalized.get("filename", "")
            clock_time = normalized.get("clock_time", "")
            label = f"{path.name} row {row_number}"
            if not filename:
                errors.append(f"{label}: missing filename")
                continue
            if not clock_time:
                errors.append(f"{label}: missing clock_time")
                continue
            try:
                clock_seconds = parse_clock_time(clock_time)
            except ValueError as exc:
                errors.append(f"{label}: {exc}")
                continue
            # Same-day clock math. A stamp earlier than the recording start is
            # before the recording, not wrapped onto the next day.
            offset = clock_seconds - recording_start_seconds
            screenshots.append(
                Screenshot(
                    source_row=row_number,
                    filename=filename,
                    clock_time=format_clock_time(clock_seconds),
                    offset_seconds=offset,
                )
            )
    return screenshots, errors


def assign_screenshots(segments: list[Segment], screenshots: list[Screenshot]) -> None:
    """Place each screenshot into the unique window that contains its offset."""

    for shot in screenshots:
        for segment in segments:
            if segment.start_seconds <= shot.offset_seconds < segment.end_seconds:
                segment.screenshots.append(shot)
                break
    for segment in segments:
        segment.screenshots.sort(key=lambda shot: (shot.offset_seconds, shot.filename))


def outside_reason(shot: Screenshot, segments: list[Segment]) -> str:
    if not segments or shot.offset_seconds < segments[0].start_seconds:
        if shot.offset_seconds < 0:
            return "before the recording started"
        return "before the first segment"
    if shot.offset_seconds >= segments[-1].end_seconds:
        return "after the last segment"
    return "in a gap between segments"


def render_report(
    recording_start: str,
    segments: list[Segment],
    screenshots: list[Screenshot],
    row_errors: list[str],
) -> str:
    assigned_ids = {id(shot) for segment in segments for shot in segment.screenshots}
    outside = [shot for shot in screenshots if id(shot) not in assigned_ids]
    outside.sort(key=lambda shot: (shot.offset_seconds, shot.filename))

    topics: dict[str, list[Segment]] = {}
    for segment in segments:
        topics.setdefault(segment.topic, []).append(segment)

    lines = [
        "# Evidence report",
        "",
        f"Recording start: {recording_start}",
        "",
        f"- Segments: {len(segments)}",
        f"- Screenshots assigned: {len(screenshots) - len(outside)}",
        f"- Screenshots outside every segment: {len(outside)}",
        f"- Rows skipped: {len(row_errors)}",
        "",
        "A screenshot is assigned when its offset from the recording start falls",
        "inside a segment window. The window includes the segment start and runs",
        "up to, but not including, the segment end. A time that lands exactly on",
        "a boundary belongs to the following segment.",
        "",
    ]

    for topic, topic_segments in topics.items():
        lines.append(f"## {topic}")
        lines.append("")
        for segment in topic_segments:
            start_clock = clock_plus(recording_start, segment.start_seconds)
            end_clock = clock_plus(recording_start, segment.end_seconds)
            lines.append(f"### {start_clock}–{end_clock}")
            lines.append("")
            for paragraph in segment.text.splitlines() or [""]:
                lines.append(f"> {paragraph}")
            lines.append("")
            if segment.screenshots:
                for shot in segment.screenshots:
                    lines.append(
                        f"- {shot.filename} — {shot.clock_time} "
                        f"(offset {format_offset(shot.offset_seconds)})"
                    )
            else:
                lines.append("No screenshots fall in this window.")
            lines.append("")

    lines.append("## Outside every segment")
    lines.append("")
    if outside:
        lines.append("These screenshots do not fall inside any transcript window.")
        lines.append("")
        for shot in outside:
            lines.append(
                f"- {shot.filename} — {shot.clock_time} "
                f"(offset {format_offset(shot.offset_seconds)}) — "
                f"{outside_reason(shot, segments)}"
            )
    else:
        lines.append("None.")
    lines.append("")

    if row_errors:
        lines.append("## Skipped rows")
        lines.append("")
        lines.append("These rows were left out of the alignment.")
        lines.append("")
        for message in row_errors:
            lines.append(f"- {message}")
        lines.append("")

    return "\n".join(lines)


def require_number(value: object, label: str) -> tuple[float | None, str | None]:
    # bool is a subclass of int, but JSON true/false are not durations.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, f"{label} must be a number"
    return float(value), None


def require_text(value: object, label: str) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or not value.strip():
        return None, f"{label} must be a non-empty string"
    return value.strip(), None


if __name__ == "__main__":
    sys.exit(main())
