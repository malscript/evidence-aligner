# evidence-aligner

Two small tools for organizing synthetic, timestamped screenshots.

The command-line aligner matches screenshot clock times to a transcript and writes a Markdown report grouped by topic. The desktop organizer lets you build sessions and buckets from a folder of files, then export a Word document.

All sample data in this repository is synthetic. The transcript, clock times, filenames, and images were invented for demonstration. They do not describe a real recording, meeting, or project.

## Command-line aligner

### The problem

A recording has two clocks. The transcript is timed in seconds from the moment the recording started. Screenshots are stamped with wall-clock times such as `14:06:50`. The aligner uses the recording's start clock time to put those on one timeline, then groups the screenshots under the transcript topic they belong to.

### How alignment works

Pass the clock time when the recording began (`HH:MM:SS`). Each transcript segment has `start_seconds` measured from that instant, so a segment at 90 seconds is shown as recording-start plus 90 seconds.

Each segment owns a window that **includes its start and stops just before its end**. A screenshot whose offset from the recording start falls in that window is assigned to the segment. A time that lands exactly on a boundary belongs to the following segment.

- If a segment includes `end_seconds`, that value closes the window.
- If `end_seconds` is omitted, the window runs until the next segment starts.
- The last segment needs `end_seconds`, or pass `--duration-seconds` to close it.

Screenshots before the first segment, after the last segment, or in a gap between windows are listed under **Outside every segment** instead of being forced into a topic. Rows with a missing filename or a clock time that is not `HH:MM:SS` are skipped, named in the report, and printed as warnings. A transcript that is not usable stops the command before a report is written.

The sample recording starts at `14:00:00`. The transcript has six segments across three topics (Welcome, Feature tour, Closing). `sample_data/screenshots.csv` lists the same ten filenames as `sample_images/`, with clock times spread across that transcript.

### Run it

From the repository root. The aligner uses the Python standard library only.

```bash
python aligner.py
```

That reads the sample files and writes `reports/evidence_report.md`. The same command with the defaults written out:

```bash
python aligner.py \
  --recording-start 14:00:00 \
  --transcript sample_data/transcript.json \
  --screenshots sample_data/screenshots.csv \
  --output reports/evidence_report.md
```

## Desktop organizer

The organizer is a CustomTkinter window. It does not read the transcript. It treats **every file** in a folder as a screenshot and sorts the list by the timestamp in the filename.

**Timestamp pattern** is optional. Leave it blank and press **Apply**, and two shapes are read:

- `yyyy-MM-dd HH_mm_ss`, as in `2026-09-30 14_30_22.png`. An underscore may stand in for the space.
- `HHmmss`, as in `shot_143022.png` (14:30:22).

To match a capture tool, type its pattern and press **Apply**. You can paste the whole token `${capturetime:d"yyyy-MM-dd HH_mm_ss"}`; the quotes are stripped. Tokens are `yyyy` or `yy` (year), `MM` (month), `dd` (day), `HH` (hour), `mm` (minute), and `ss` (second). Any other character, including `-`, `_`, and spaces, must appear in the filename as written. A custom pattern is used on its own, so a file that does not match it is listed with no time. Dated names sort by calendar day, then clock time. Shots do not have to be a fixed interval apart.

`sample_images/` is the default folder. Nine of the files are small synthetic PNG images. `shot_141105.png` is a text placeholder on purpose: on export, real images are embedded and a non-image file is inserted as its filename. Every screenshot, image or not, gets a caption with its filename and timestamp.

You can:

- choose a different screenshots folder
- set a timestamp pattern, or leave it blank for the built-in filename shapes
- add sessions, and add as many buckets as you need inside each session (the name is whatever you type when you add it)
- preview a screenshot and choose which bucket it goes into
- assign selected screenshots to the current bucket
- move screenshots up or down inside a bucket
- return screenshots to the unassigned list
- see everything that is still unassigned
- export the assigned screenshots to a `.docx` file (one heading per session, one subheading per bucket)

Sessions live in the window until you close it or reload the folder. Reload clears them.

### Install and run

From the repository root:

```bash
pip install -r requirements.txt
python gui/app.py
```

`requirements.txt` installs `python-docx` for Word export and `customtkinter` for the window. CustomTkinter is built on Tkinter. On Debian or Ubuntu, if Python was installed without Tk, add the system package:

```bash
sudo apt install python3-tk
```

The window opens on `sample_images/`. A session is the top section of the Word document. A bucket is a pile of screenshots inside that session, and you can add as many buckets as you need. Select a file and click **Preview**. The preview lists every bucket. **Bucket into …** drops the screenshot into the one you picked, then moves on to the next file that is still unassigned. **Export assigned to Word** writes every bucket into one document and asks where to save it. The suggested path is `reports/screenshot_organizer.docx`. Unassigned screenshots are left out; the app asks before doing that.

## Layout

```text
aligner.py                     command-line alignment
gui/app.py                     desktop organizer
gui/theme.py                   window colors, fonts, and buttons
gui/dialogs.py                 dark prompts for notices and yes/no questions
gui/preview.py                 screenshot preview and bucketing
gui/model.py                   folders, sessions, buckets, filename timestamps
gui/export_docx.py             Word export
sample_data/transcript.json    synthetic transcript
sample_data/screenshots.csv    synthetic screenshot clock times
sample_images/                 synthetic screenshot files for the organizer
requirements.txt               python-docx and customtkinter
```
