"""Frames for an AI to look at: which moments, and the picture at full resolution.

The scene map already knows where something new appears: the first frame of every new scene
and each visible build step inside it (`Scene.changes`). Repeats are skipped; they really are
the same picture (checked on `slFa9Vx3crw`). Times are the thumbnail times, the moments known
to show that state.

Full resolution comes from the video itself, one frame per needed second: yt-dlp gives the
address of the video-only stream and ffmpeg reads just that second from it (no whole-file
download). A local file is read directly. If that fails, the thumbnail is cut from the sheets.
Frames are cached in `frames/` and sent about 1280 px wide.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .local import ffmpeg
from .timeline import Timeline

WIDTH = 1280
STREAM_FORMAT = "bv*[height<=1080][vcodec^=avc1]/bv*[height<=1080]/bv*"
STREAM_TTL = 3 * 3600  # YouTube's stream addresses expire after a few hours


@dataclass
class Moment:
    t: float
    label: str  # "new visual", "build step", or "requested"
    scene: int | None = None


@dataclass
class Shot:
    t: float
    path: Path
    sharp: bool  # full resolution (True) or a thumbnail (False)
    label: str = ""


def moments(tl: Timeline, start: float = 0.0, end: float | None = None, limit: int = 6) -> list[Moment]:
    """New visuals and their build steps between start and end, spread evenly if there are too many."""
    end = tl.video.duration if end is None else end
    found = []
    for s in tl.scenes:
        if s.kind != "new":
            continue
        for k, f in enumerate(s.changes or [s.frames[0]]):
            t = tl.frames[f].t
            if start <= t < end:
                found.append(Moment(t, "new visual" if k == 0 else "build step", s.index))
    if len(found) <= limit:
        return found
    firsts = [m for m in found if m.label == "new visual"]
    pool = firsts if len(firsts) >= limit else found
    step = len(pool) / limit
    return [pool[int(i * step)] for i in range(limit)]


def label_at(tl: Timeline, t: float) -> str:
    for s in tl.scenes:
        if s.start <= t < s.end:
            return {"new": "new visual", "repeat": "seen before", "base": "base shot"}[s.kind]
    return ""


def grab(tl: Timeline, where: Path, times: list[float], labels: list[str] | None = None) -> list[Shot]:
    """The picture at each time: full resolution when it can be fetched, else the thumbnail."""
    out_dir = where / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    labels = labels or [label_at(tl, t) for t in times]
    clamped = [max(0.0, min(t, tl.video.duration - 0.5)) for t in times]
    missing = [t for t in clamped if not (out_dir / f"{int(t * 1000)}.jpg").exists()]
    source = None
    if missing:
        try:
            source = _source(tl, where)
        except (RuntimeError, OSError, subprocess.SubprocessError):
            source = None  # thumbnails, below

    def one(i: int) -> Shot | None:
        t = clamped[i]
        sharp = out_dir / f"{int(t * 1000)}.jpg"
        if not sharp.exists() and source:
            try:
                _ffmpeg_frame(source, t, sharp)
            except (RuntimeError, OSError, subprocess.SubprocessError):
                pass
        if sharp.exists():
            return Shot(t, sharp, True, labels[i])
        thumb = out_dir / f"{int(t * 1000)}-thumb.jpg"
        return Shot(t, thumb, False, labels[i]) if _thumbnail(tl, where, t, thumb) else None

    with ThreadPoolExecutor(4) as pool:
        return [s for s in pool.map(one, range(len(clamped))) if s]


def _source(tl: Timeline, where: Path) -> str:
    """A path or URL ffmpeg can seek in: the local file, or YouTube's video-only stream."""
    if not tl.video.id:
        return tl.video.url
    cache = where / "stream.json"
    if cache.exists():
        saved = json.loads(cache.read_text(encoding="utf-8"))
        if time.time() - saved.get("at", 0) < STREAM_TTL:
            return saved["url"]
    cmd = [sys.executable, "-m", "yt_dlp", "-g", "-f", STREAM_FORMAT, "--js-runtimes", "node", "--no-warnings",
           f"https://www.youtube.com/watch?v={tl.video.id}"]
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    lines = [x for x in done.stdout.splitlines() if x.startswith("http")]
    if done.returncode != 0 or not lines:
        raise RuntimeError(f"yt-dlp gave no video stream: {done.stderr.strip()[-200:]}")
    cache.write_text(json.dumps({"url": lines[-1], "at": time.time()}), encoding="utf-8")
    return lines[-1]


def _ffmpeg_frame(source: str, t: float, dst: Path) -> None:
    tmp = dst.with_suffix(".part.jpg")
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-ss", f"{t:.2f}", "-i", source,
           "-frames:v", "1", "-vf", f"scale='min({WIDTH},iw)':-2", "-q:v", "3", str(tmp)]
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if done.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg could not read the frame at {t:.0f} s: {done.stderr.strip()[-200:]}")
    tmp.replace(dst)


def _thumbnail(tl: Timeline, where: Path, t: float, dst: Path) -> bool:
    """Cut the thumbnail at or before t out of its saved sheet."""
    before = [f for f in tl.frames if f.t <= t + 0.01] or tl.frames[:1]
    if not before:
        return False
    f = before[-1]
    sheet = where / "sheets" / f"{f.sheet}.jpg"
    if not sheet.exists():
        return False
    with Image.open(sheet) as im:
        crop = im.crop((f.x, f.y, f.x + f.w, f.y + f.h))
        buf = io.BytesIO()
        crop.convert("RGB").save(buf, "JPEG", quality=90)
    dst.write_bytes(buf.getvalue())
    return True
