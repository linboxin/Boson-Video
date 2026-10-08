"""Local video files: build our own storyboard with ffmpeg.

ffmpeg decodes only keyframes (`-skip_frame nokey`), which skips almost all of
the decoding work, and keeps at most one frame every few seconds. The frames are
then packed into JPEG mosaics so the renderer treats them exactly like YouTube
storyboard sheets.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from .timeline import Frame, Sheet, Video

FRAME_W = 320
MIN_GAP = 2.0  # seconds between kept frames...
MAX_FRAMES = 400  # ...widened for long videos so the page stays light
COLS, ROWS = 5, 5  # frames per mosaic sheet


class LocalVideoError(RuntimeError):
    pass


def ffmpeg() -> str:
    """The ffmpeg installed on this computer, else the one that comes with the package
    (imageio-ffmpeg), so the plugin works on a computer that never installed ffmpeg."""
    for candidate in _installed():
        if candidate and Path(candidate).exists():
            return str(candidate)
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        raise LocalVideoError("ffmpeg not found; install it (e.g. `brew install ffmpeg`)") from None


def _installed() -> list:
    return [shutil.which("ffmpeg"), Path.home() / ".local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg",
            "/usr/local/bin/ffmpeg", Path.home() / "scoop/shims/ffmpeg.exe"]


def probe_duration(path: str) -> float:
    err = subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", "-i", path], capture_output=True).stderr
    m = re.search(rb"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if not m:
        raise LocalVideoError(f"ffmpeg can't read a duration from {path}")
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


def load(path: str) -> tuple[Video, list[Sheet], list[Frame], list[np.ndarray]]:
    if not Path(path).is_file():
        raise LocalVideoError(f"no such file: {path}")
    duration = probe_duration(path)
    gap = max(MIN_GAP, duration / MAX_FRAMES)
    vf = rf"select='isnan(prev_selected_t)+gte(t-prev_selected_t\,{gap:.3f})',scale={FRAME_W}:-2,showinfo"
    cmd = [ffmpeg(), "-hide_banner", "-nostdin", "-skip_frame", "nokey", "-i", path, "-an", "-sn",
           "-vf", vf, "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    err = proc.stderr.decode("utf-8", "replace")
    if proc.returncode != 0:
        raise LocalVideoError(f"ffmpeg failed on {path}: {err.strip().splitlines()[-1] if err.strip() else '?'}")
    times = [float(t) for t in re.findall(r"pts_time:\s*(-?[\d.]+)", err)]
    size = re.search(r"\bs:(\d+)x(\d+)", err)
    if not times or not size:
        raise LocalVideoError(f"no video frames found in {path}")
    w, h = int(size.group(1)), int(size.group(2))
    raw = np.frombuffer(proc.stdout, np.uint8)
    n = min(len(times), raw.size // (w * h * 3))
    pixels = list(raw[: n * w * h * 3].reshape(n, h, w, 3))
    sheets, frames = _mosaics(pixels, times[:n], w, h)
    video = Video(title=Path(path).stem, channel="", duration=duration, url=str(Path(path).resolve()))
    return video, sheets, frames, pixels


def _mosaics(pixels: list[np.ndarray], times: list[float], w: int, h: int) -> tuple[list[Sheet], list[Frame]]:
    per = COLS * ROWS
    sheets, frames = [], []
    for m in range(0, len(pixels), per):
        chunk = pixels[m : m + per]
        rows = -(-len(chunk) // COLS)
        canvas = Image.new("RGB", (COLS * w, rows * h))
        for i, p in enumerate(chunk):
            x, y = (i % COLS) * w, (i // COLS) * h
            canvas.paste(Image.fromarray(p), (x, y))
            frames.append(Frame(len(frames), max(times[m + i], 0.0), len(sheets), x, y, w, h))
        buf = io.BytesIO()
        canvas.save(buf, "JPEG", quality=80)
        sheets.append(Sheet(buf.getvalue(), canvas.width, canvas.height))
    return sheets, frames
