"""What was shown, as text in the document: the screen read at the moments the scene map picks.

The scene map knows where something new appears (new scenes and their build steps; repeats are
the same picture and are skipped). Those frames are fetched at full resolution (frames.py) and
read by OCR (ocr.py). Two rules keep the text honest:

- **Burned-in subtitles are kept apart.** They are the speech written out, not what the picture
  shows: a centred line in the bottom band of the frame, in words rather than numbers. They go to
  `Screen.subtitles` (useful to correct and score the transcript), never into `Screen.text`.
- **A build step is credited only with what it adds.** A slide that builds line by line repeats
  its earlier lines on every frame; each frame keeps the lines new since the previous frame of the
  same scene, so the document says when each line appeared.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from . import frames as frames_mod
from . import ocr
from .timeline import Screen, Timeline

MIN_SCORE = 0.6  # OCR confidence below this is usually noise
SUBTITLE_BAND = 0.82  # a subtitle's middle sits below this share of the frame's height
_CJK = re.compile(r"[㐀-鿿]")
_KEY = re.compile(r"[\W_]+")


def read(tl: Timeline, where: Path) -> tuple[list[Screen], dict]:
    """Every new visual and build step, read; returns the screens and timings in ms.

    Frames are read as they arrive, so fetching and reading overlap."""
    clock = time.perf_counter()
    picked = frames_mod.moments(tl, 0.0, None, limit=10**6)
    reader = ocr.Reader()

    def ready(shot) -> None:
        if shot.sharp:  # thumbnails are too small to read
            reader.submit(shot.path)

    shots = frames_mod.grab(tl, where, [m.t for m in picked], [m.label for m in picked], on_shot=ready)
    fetch_ms = (time.perf_counter() - clock) * 1000
    texts = reader.finish()
    by_time = {round(sh.t, 2): sh for sh in shots if sh.sharp}
    pairs = [(m, by_time[round(m.t, 2)]) for m in picked if round(m.t, 2) in by_time]
    screens, seen = [], {}
    for m, sh in pairs:
        row = texts.get(str(sh.path))
        if not row:
            continue
        shown, subtitles = split_lines(row["lines"], row["w"], row["h"])
        previous = seen.get(m.scene, set()) if m.label == "build step" else set()
        new = [line for line in shown if _KEY.sub("", line.lower()) not in previous]
        seen[m.scene] = {_KEY.sub("", line.lower()) for line in shown}
        if new or subtitles:
            screens.append(Screen(round(sh.t, 2), m.scene, "\n".join(new), "\n".join(subtitles),
                                  sh.path.relative_to(where).as_posix()))
    total = (time.perf_counter() - clock) * 1000
    return screens, {"frames fetch": round(fetch_ms, 1), "screen text after fetch": round(total - fetch_ms, 1)}


def split_lines(lines: list, w: int, h: int) -> tuple[list[str], list[str]]:
    """OCR lines -> (what the picture shows, top to bottom; burned-in subtitles)."""
    kept = [ln for ln in lines if ln[5] >= MIN_SCORE and len(ln[4].strip()) > 1]
    shown, subtitles = [], []
    for x0, y0, x1, y1, text, _ in sorted(kept, key=lambda ln: (round(ln[1] / max(h * 0.02, 1)), ln[0])):
        middle_y, middle_x = (y0 + y1) / 2, (x0 + x1) / 2
        wordy = bool(_CJK.search(text)) or len(re.findall(r"[A-Za-z]{2,}", text)) >= 3
        if middle_y > SUBTITLE_BAND * h and abs(middle_x - w / 2) < 0.15 * w and wordy:
            subtitles.append(text.strip())
        else:
            shown.append(text.strip())
    return shown, subtitles


def available() -> bool:
    return ocr.available()
