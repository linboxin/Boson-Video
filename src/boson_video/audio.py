"""Audio for the speech track: fetch it, convert it to 16 kHz mono, cut it at pauses.

Speech-to-text runs on several pieces at once, so total time is about one piece's
time. Cutting at pauses (silences ffmpeg finds) keeps words whole at the seams.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
import wave
from pathlib import Path

from .local import ffmpeg

RATE = 16_000  # what speech models want; also small and fast to cut
SPEECH_FORMAT = "worstaudio[acodec!=none]/bestaudio"  # speech needs little bitrate; small files arrive sooner
SEAM_WINDOW = 20.0  # look this far (seconds) either side of an even split for a pause


class AudioError(RuntimeError):
    pass


def fetch_youtube(video_id: str, folder: Path, fresh: bool = False) -> Path:
    """Download only the audio track (cached in `folder` unless `fresh`)."""
    folder.mkdir(parents=True, exist_ok=True)
    cached = sorted(p for p in folder.glob("audio.*") if p.suffix not in (".wav", ".part"))
    if cached and not fresh:
        return cached[0]
    for old in cached:
        old.unlink()
    cmd = [
        sys.executable, "-m", "yt_dlp", "-f", SPEECH_FORMAT, "--js-runtimes", "node",
        "-o", str(folder / "audio.%(ext)s"), "--no-progress", "--quiet", "--no-warnings",
        "--print", "after_move:filepath", f"https://www.youtube.com/watch?v={video_id}",
    ]
    # YouTube changes which formats it offers from one request to the next and
    # sometimes offers none, so one retry after a pause is worth it.
    for attempt in range(2):
        done = subprocess.run(cmd, capture_output=True, text=True)
        lines = done.stdout.strip().splitlines()
        if done.returncode == 0 and lines:
            return Path(lines[-1])
        if attempt == 0:
            time.sleep(2)
    raise AudioError(f"yt-dlp could not fetch the audio: {done.stderr.strip()[-300:]}")


def to_wav(src: Path, dst: Path) -> Path:
    """Any audio or video file -> 16 kHz mono 16-bit WAV."""
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(src),
           "-vn", "-ac", "1", "-ar", str(RATE), "-sample_fmt", "s16", str(dst)]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        raise AudioError(f"ffmpeg could not read the audio of {src}: {done.stderr.strip()[-300:]}")
    return dst


def duration(wav: Path) -> float:
    with wave.open(str(wav)) as w:
        return w.getnframes() / w.getframerate()


def silences(wav: Path, noise_db: int = -35, min_len: float = 0.35) -> list[tuple[float, float]]:
    """Pauses in the audio as (start, end) seconds."""
    cmd = [ffmpeg(), "-hide_banner", "-nostdin", "-i", str(wav),
           "-af", f"silencedetect=noise={noise_db}dB:d={min_len}", "-f", "null", "-"]
    err = subprocess.run(cmd, capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: (-?[\d.]+)", err)]
    return list(zip(starts, ends))


def plan_pieces(total: float, pauses: list[tuple[float, float]], n: int) -> list[tuple[float, float]]:
    """Split [0, total] into n pieces, moving each seam to the nearest pause within the window."""
    n = max(1, n)
    seams = []
    for k in range(1, n):
        target = total * k / n
        middles = [(a + b) / 2 for a, b in pauses if abs((a + b) / 2 - target) <= SEAM_WINDOW]
        seams.append(min(middles, key=lambda m: abs(m - target)) if middles else target)
    edges = [0.0] + sorted(seams) + [total]
    return [(a, b) for a, b in zip(edges, edges[1:]) if b - a > 0.05]


def piece_count(total: float, workers: int = 8, min_piece: float = 90.0) -> int:
    """Enough pieces to keep `workers` busy, none shorter than `min_piece` seconds."""
    return max(1, min(workers, int(total // min_piece)))


def cut(wav: Path, pieces: list[tuple[float, float]], folder: Path) -> list[tuple[Path, float]]:
    """Write each piece as its own WAV; returns (path, start offset) pairs."""
    out = []
    with wave.open(str(wav)) as src:
        rate, width, channels = src.getframerate(), src.getsampwidth(), src.getnchannels()
        for i, (a, b) in enumerate(pieces):
            src.setpos(int(a * rate))
            frames = src.readframes(int((b - a) * rate))
            path = folder / f"piece-{i:02d}.wav"
            with wave.open(str(path), "wb") as dst:
                dst.setnchannels(channels)
                dst.setsampwidth(width)
                dst.setframerate(rate)
                dst.writeframes(frames)
            out.append((path, a))
    return out
