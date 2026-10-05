"""Where videos live on disk, and loading and saving them.

One folder per video: `index.html` (the page), `timeline.json` (the document, see
docs/timeline-format.md), `sheets/<n>.jpg` (the thumbnail sheets, so frames can be cut without
rebuilding), `frames/` (full-resolution frames, fetched on demand), `status.json` (a build in
progress) and `notes.json` (questions asked in the page). The CLI keeps `./out`; the plugin uses
`BOSON_VIDEO_HOME`, by default `~/.boson-video`.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .render import render
from .timeline import Sheet, Timeline
from .youtube import YouTubeError, parse_video_id


def home() -> Path:
    return Path(os.environ.get("BOSON_VIDEO_HOME") or Path.home() / ".boson-video").expanduser()


def key(ref: str) -> str:
    """A video's folder name: its YouTube id, or a local file's name without the extension."""
    if Path(ref).expanduser().is_file():
        return re.sub(r"[^A-Za-z0-9_-]+", "_", Path(ref).stem)[:64] or "video"
    try:
        return parse_video_id(ref)
    except YouTubeError:
        return re.sub(r"[^A-Za-z0-9_-]+", "_", ref.strip())[:64]


def folder(name: str, root: Path | None = None) -> Path:
    return (root or home()) / name


def exists(name: str, root: Path | None = None) -> bool:
    return (folder(name, root) / "timeline.json").exists()


def load(name: str, root: Path | None = None, with_sheets: bool = False) -> Timeline:
    where = folder(name, root)
    data = json.loads((where / "timeline.json").read_text(encoding="utf-8"))
    sheets = []
    if with_sheets:
        for i, size in enumerate(data.get("sheets", [])):
            path = where / "sheets" / f"{i}.jpg"
            if path.exists():
                sheets.append(Sheet(path.read_bytes(), size["width"], size["height"]))
    return Timeline.from_json(data, sheets)


def save(tl: Timeline, where: Path) -> Path:
    """Write the page, the document and the sheets; returns the page."""
    where.mkdir(parents=True, exist_ok=True)
    page = where / "index.html"
    page.write_text(render(tl), encoding="utf-8")
    (where / "timeline.json").write_text(json.dumps(tl.to_json(), ensure_ascii=False, indent=1), encoding="utf-8")
    if tl.sheets:
        (where / "sheets").mkdir(exist_ok=True)
        for i, sheet in enumerate(tl.sheets):
            path = where / "sheets" / f"{i}.jpg"
            if not path.exists() or path.stat().st_size != len(sheet.jpeg):
                path.write_bytes(sheet.jpeg)
    return page


def videos(root: Path | None = None) -> list[dict]:
    """Every video in the library, newest first: key, title, channel, duration, language."""
    out = []
    for tj in (root or home()).glob("*/timeline.json"):
        try:
            data = json.loads(tj.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        v = data.get("video", {})
        out.append({"key": tj.parent.name, "title": v.get("title", ""), "channel": v.get("channel", ""),
                    "duration": v.get("duration", 0), "language": data.get("language"),
                    "words": bool(data.get("transcript")), "mtime": tj.stat().st_mtime})
    return sorted(out, key=lambda x: x["mtime"], reverse=True)
