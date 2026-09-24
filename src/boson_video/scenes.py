"""Cut a frame sequence into scenes and find the looks that keep coming back.

Plain arithmetic on small thumbnails: no model, tens of milliseconds.

Storyboard frames are 2-10 s apart, so "motion" and "a new picture" have to be
told apart without seeing the motion. The key signal is the *still-pixel change*:
first learn which pixels normally stay put in this video (the typical
frame-to-frame change of every pixel), then ask what fraction of those pixels
changed clearly. A host's gestures or a speaker's webcam box live in pixels that
always move, so they don't count; a new slide rewrites pixels that never move.
On the calibration videos this separates same-slide pairs (<= 0.001) from
different slides (>= 0.016), and one talking-head shot (<= 0.013) from a cut (>= 0.29).

- A hard cut is a change nobody would call motion: the colours or the still
  pixels mostly changed.
- A soft cut is a change that stands out from its neighbours (a new slide in a
  still deck), so a steadily moving shot doesn't cut on every frame.
- Scenes that resemble each other share a look; a look filling a large share of
  the video is the base shot (the host, the podcast camera) and says little that
  the audio doesn't.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from .timeline import Frame, Scene

SIG_W, SIG_H = 64, 36  # layout / colour / detail signatures
PIX_W, PIX_H = 128, 72  # still-pixel change

STILL_ACTIVITY = 0.01  # a pixel is still if its median frame-to-frame change is below this
PIXEL_CHANGED = 0.10  # ...and it changed if it moved by more than this (about 25 grey levels)
MIN_STILL_SHARE = 0.20  # below this share of still pixels, the still signal is ignored

HARD = {"color": 0.25, "still": 0.25}  # either alone means a different picture
HARD_LAYOUT, HARD_LAYOUT_COLOR = 0.20, 0.12  # or the picture rearranged and recoloured
SOFT_RATIO = 3.0  # a soft cut is this many times the neighbouring changes...
SOFT_MIN = {"still": 0.01, "layout": 0.04, "color": 0.06}  # ...and at least this big
SAME_LOOK = {"layout": 0.12, "color": 0.15, "still": 0.006}  # two views of one look differ less
BASE_SHARE = 0.50  # a look filling this much of the video is the base shot,
BASE_SHARE_RECURRING = 0.30  # or this much if it keeps coming back (host between cutaways)

_GREY = np.array([0.299, 0.587, 0.114], dtype=np.float32)


class Signatures:
    def __init__(self, pixels: list[np.ndarray]):
        n = len(pixels)
        small = np.stack(
            [np.asarray(Image.fromarray(p).resize((SIG_W, SIG_H), Image.BOX)) for p in pixels]
        ).astype(np.float32) / 255
        grey = small @ _GREY
        layout = grey.reshape(n, -1)
        layout = layout - layout.mean(axis=1, keepdims=True)
        self.layout = layout / (np.linalg.norm(layout, axis=1, keepdims=True) + 1e-6)
        gx = np.abs(np.diff(grey, axis=2))[:, :-1, :]
        gy = np.abs(np.diff(grey, axis=1))[:, :, :-1]
        self.detail = (gx + gy).reshape(n, -1).mean(axis=1)  # how much is drawn on the frame
        q = np.minimum((small * 4).astype(np.int32), 3)
        bins = (q[..., 0] * 16 + q[..., 1] * 4 + q[..., 2]).reshape(n, -1)
        color = np.stack([np.bincount(b, minlength=64) for b in bins]).astype(np.float32)
        self.color = color / color.sum(axis=1, keepdims=True)

        fine = np.stack(
            [np.asarray(Image.fromarray(p).convert("L").resize((PIX_W, PIX_H), Image.BOX)) for p in pixels]
        ).astype(np.int16)
        if n > 1:
            activity = np.median(np.abs(np.diff(fine, axis=0)), axis=0) / 255
        else:
            activity = np.zeros(fine.shape[1:])
        still = activity < STILL_ACTIVITY
        self.still_share = float(still.mean())
        self.still_px = fine[:, still]  # (n, m): each frame's normally-still pixels, 0-255

    def between(self, a, b) -> dict[str, np.ndarray]:
        """Distances in [0, 1] between frames a[i] and b[i], one array per signal."""
        a, b = np.atleast_1d(a), np.atleast_1d(b)
        return {
            "layout": np.clip((1 - np.einsum("ij,ij->i", self.layout[a], self.layout[b])) / 2, 0, 1),
            "color": 1 - np.minimum(self.color[a], self.color[b]).sum(axis=1),
            "still": _changed(self.still_px[a], self.still_px[b]) if self.uses_still else np.zeros(len(a)),
        }

    @property
    def uses_still(self) -> bool:
        return self.still_share >= MIN_STILL_SHARE and self.still_px.shape[1] > 0


def _changed(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fraction of pixels that moved clearly between x[i] and y[i] (rows of 0-255 values)."""
    return (np.abs(x - y) > PIXEL_CHANGED * 255).mean(axis=-1)


def detect(frames: list[Frame], pixels: list[np.ndarray], duration: float) -> list[Scene]:
    if not frames:
        return []
    sig = Signatures(pixels)
    p = np.arange(len(frames) - 1)
    step = sig.between(p, p + 1)  # step[c][i]: change from frame i to i + 1
    starts = [0] + find_cuts(sig, step)
    groups = [list(range(a, b)) for a, b in zip(starts, starts[1:] + [len(frames)])]
    looks = assign_looks(groups, sig)
    groups, looks = _merge_adjacent(groups, looks)
    found = _build(frames, groups, looks, sig.detail, duration)
    for s in found:
        s.changes = _changes(s.frames, sig)
    return found


def find_cuts(sig: Signatures, step: dict[str, np.ndarray]) -> list[int]:
    """Indices of the frames that start a new scene."""
    n = len(sig.detail)
    if n < 2:
        return []
    p = np.arange(n - 2)
    skip = sig.between(p, p + 2)  # skip[c][i]: change from frame i to i + 2
    cuts = []
    for i in range(n - 1):
        hard = (
            step["color"][i] >= HARD["color"]
            or step["still"][i] >= HARD["still"]
            or (step["layout"][i] >= HARD_LAYOUT and step["color"][i] >= HARD_LAYOUT_COLOR)
        )
        around = [q for q in (i - 2, i - 1, i + 1, i + 2) if 0 <= q < n - 1]
        soft = any(
            step[c][i] >= SOFT_MIN[c]
            and step[c][i] >= SOFT_RATIO * (float(np.mean(step[c][around])) if around else 0.0)
            # it must last: a gesture into a still corner is gone by the next frame
            and (i + 1 >= n - 1 or skip[c][i] >= 0.5 * step[c][i])
            for c in SOFT_MIN
        )
        if hard or soft:
            cuts.append(i + 1)
    return cuts


def assign_looks(groups: list[list[int]], sig: Signatures) -> list[int]:
    """Give each scene a look id: it joins the closest earlier scene it resembles."""
    score = _scene_similarity(groups, sig)
    looks: list[int] = []
    for b in range(len(groups)):
        a = int(np.argmin(score[b, :b])) if b else -1
        if a >= 0 and score[b, a] <= 1.0:
            looks.append(looks[a])
        else:
            looks.append(max(looks) + 1 if looks else 0)
    return looks


def _scene_similarity(groups: list[list[int]], sig: Signatures) -> np.ndarray:
    """score[b, a] <= 1 means scenes a and b show the same look (compared on a few frames each).

    Layout and colour are compared for every pair with one matrix product; the
    costlier still-pixel check runs only on pairs that already pass those two.
    The still-pixel tolerance is tight: two "Demo" slides with one different line
    differ by ~0.016, while a host's returns differ by ~0 (their gestures sit in
    pixels that are never still).
    """
    views = [sorted({g[0], g[len(g) // 2], g[-1]}) for g in groups]
    owner = np.concatenate([[s] * len(v) for s, v in enumerate(views)])
    v = np.concatenate(views)
    layout = np.clip((1 - sig.layout[v] @ sig.layout[v].T) / 2, 0, 1)
    hist = sig.color[v]
    color = np.empty_like(layout)
    for s in range(0, len(v), 128):  # histogram intersection, in chunks to bound memory
        color[s : s + 128] = 1 - np.minimum(hist[s : s + 128, None, :], hist[None, :, :]).sum(axis=2)
    norm = np.maximum(layout / SAME_LOOK["layout"], color / SAME_LOOK["color"])
    norm[owner[:, None] == owner[None, :]] = np.inf
    if sig.uses_still:
        px = sig.still_px[v][:, ::4]  # every 4th still pixel is plenty for a fraction
        for r in range(len(v) - 1):
            cols = np.nonzero(norm[r, r + 1 :] <= 1.0)[0] + r + 1
            if len(cols):
                worse = np.maximum(norm[r, cols], _changed(px[cols], px[r]) / SAME_LOOK["still"])
                norm[r, cols] = worse
                norm[cols, r] = worse
    n = len(groups)
    score = np.full((n, n), np.inf)
    np.minimum.at(score, (owner[:, None].repeat(len(v), 1), owner[None, :].repeat(len(v), 0)), norm)
    return score


def _changes(group: list[int], sig: Signatures) -> list[int]:
    """Frames of a scene that show something the previous shown frame didn't (e.g. slide builds)."""
    shown = [group[0]]
    for f in group[1:]:
        d = sig.between(shown[-1], f)
        if sig.uses_still:
            visible = d["still"][0] >= SOFT_MIN["still"]
        else:
            visible = d["layout"][0] >= 0.1 or d["color"][0] >= 0.1
        if visible:
            shown.append(f)
    return shown


def _merge_adjacent(groups: list[list[int]], looks: list[int]) -> tuple[list[list[int]], list[int]]:
    """Neighbouring scenes with the same look are one scene (e.g. a gesture that tripped a cut)."""
    out_g: list[list[int]] = []
    out_l: list[int] = []
    for g, lk in zip(groups, looks):
        if out_l and out_l[-1] == lk:
            out_g[-1] = out_g[-1] + g
        else:
            out_g.append(list(g))
            out_l.append(lk)
    return out_g, out_l


def profile(scenes: list[Scene], duration: float) -> tuple[str, dict[str, float]]:
    """One sentence on what the picture contributes, plus the numbers behind it."""
    total = max(duration, 1e-6)
    base = sum(s.duration for s in scenes if s.kind == "base") / total
    base_looks = len({s.look for s in scenes if s.kind == "base"})
    new = sum(1 for s in scenes if s.kind == "new")
    shot = float(np.median([s.duration for s in scenes])) if scenes else 0.0
    stats = {"base_share": round(base, 3), "new_visuals": new, "median_scene_s": round(shot, 1)}
    if base >= 0.7:
        what = "One shot fills" if base_looks == 1 else f"{base_looks} recurring shots fill"
        text = f"{what} {base:.0%} of the video: what matters is what's said."
    elif len(scenes) >= 30 and shot <= 4:
        text = f"Fast cutting ({len(scenes)} shots, median {shot:.0f} s): a montage or music video."
    else:
        text = f"{new} distinct visuals: the picture carries information."
    return text, stats


def _build(frames, groups, looks, detail, duration) -> list[Scene]:
    scenes = []
    for k, (g, lk) in enumerate(zip(groups, looks)):
        start = frames[g[0]].t
        end = frames[groups[k + 1][0]].t if k + 1 < len(groups) else max(duration, frames[g[-1]].t)
        key = max(g, key=lambda f: (round(float(detail[f]), 3), f))  # most detail; later wins ties
        scenes.append(Scene(k, start, end, g, key, lk))
    total = max(duration, 1e-6)
    share: dict[int, float] = {}
    count: dict[int, int] = {}
    for s in scenes:
        share[s.look] = share.get(s.look, 0.0) + s.duration / total
        count[s.look] = count.get(s.look, 0) + 1
    seen: set[int] = set()
    for s in scenes:
        if share[s.look] >= BASE_SHARE or (share[s.look] >= BASE_SHARE_RECURRING and count[s.look] > 1):
            s.kind = "base"
        elif s.look in seen:
            s.kind = "repeat"
        seen.add(s.look)
    return scenes
