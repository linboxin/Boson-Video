"""Join the words, the picture, and the frame into moments (DIRECTION: the moment is the unit).

Scenes, passages, and screens stay the measurements. A moment is the span a person or an AI
cites: what was said while one picture-code was true, the lines new at its frame, and that frame.

Codes, in the order a scene is walked:

- **state**: the picture holds. The first frame of a new scene, and a whole base or repeat shot.
- **delta**: a later build step of the same scene. `text` is only the lines added then.
- **trajectory**: the screen changed on every sample, several samples in a row, with text on each
  (a demo, scrolling code, an animated diagram), so one still would lie. The frames are samples
  along the path; the range is worth watching. A run of changes with no text on screen is a
  person or a camera moving (a speaker at a podium, 2026-10-06), so it stays state and delta.
- **seek**: the picture changed, the screen was read, and still no full-resolution frame of this
  step exists. The document doesn't hold it: open the original range.

A moment whose screen hasn't been read yet keeps its picture code and has no frame; that is "not
read yet", not a seek. The frame is any full-resolution frame on disk for that second (OCR may
have found no text in it: a photo, a face, a chart without labels).
"""

from __future__ import annotations

from pathlib import Path

from .timeline import Moment, Screen, Timeline

TRAJECTORY_RUN = 4  # this many samples in a row, each different from the one before: motion


def assemble(tl: Timeline, where: Path | None = None) -> list[Moment]:
    """Fill `tl.moments` from the scenes, the transcript, and the screens. Returns them."""
    tl.moments = build(tl, where)
    return tl.moments


def build(tl: Timeline, where: Path | None = None) -> list[Moment]:
    screens = {round(s.t, 2): s for s in tl.screens}
    read = "screens" in tl.timings  # the screen read ran, so a step without a frame is a real gap
    found: list[Moment] = []
    for scene in tl.scenes:
        cuts = _cuts(tl, scene)
        if scene.kind != "new" or len(cuts) <= 1:
            t = cuts[0][0] if cuts else scene.start
            found.append(_moment(tl, scene.start, scene.end, "state", scene.index, t, screens.get(round(t, 2)), where))
            continue
        moving = _moving(scene, lambda f: bool(getattr(screens.get(round(tl.frames[f].t, 2)), "text", "")))
        for i, (t, f) in enumerate(cuts):
            end = cuts[i + 1][0] if i + 1 < len(cuts) else scene.end
            m = _moment(tl, scene.start if i == 0 else t, end, "state" if i == 0 else "delta", scene.index, t,
                        screens.get(round(t, 2)), where)
            if f in moving:
                m.code = "trajectory"
            elif read and not m.image:
                m.code = "seek"
            found.append(m)
    return found


def _cuts(tl: Timeline, scene) -> list[tuple[float, int]]:
    indexes = scene.changes or ([scene.frames[0]] if scene.frames else [])
    return [(tl.frames[i].t, i) for i in indexes if 0 <= i < len(tl.frames)]


def _moving(scene, shows_text) -> set[int]:
    """Frames inside runs of TRAJECTORY_RUN or more samples that each changed from the one before
    and each have text on screen. Measured in samples, not seconds: thumbnails come every 2, 5, or
    10 s depending on the length."""
    changed = {f for f in scene.changes if shows_text(f)}
    out: set[int] = set()
    run: list[int] = []
    for f in scene.frames + [None]:
        if f is not None and f in changed:
            run.append(f)
            continue
        if len(run) >= TRAJECTORY_RUN:
            out.update(run)
        run = []
    return out


def _moment(tl: Timeline, start: float, end: float, code: str, scene: int, t: float, screen: Screen | None,
            where: Path | None) -> Moment:
    passages = [i for i, s in enumerate(tl.transcript) if start <= (s.start + s.end) / 2 < end]
    image = screen.image if screen else ""
    if not image and where is not None and (where / "frames" / f"{int(t * 1000)}.jpg").exists():
        image = f"frames/{int(t * 1000)}.jpg"
    return Moment(round(start, 2), round(end, 2), code, scene, round(t, 2), passages,
                  screen.text if screen else "", image)
