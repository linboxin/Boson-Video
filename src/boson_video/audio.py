"""Audio for the speech track: fetch it, convert it to 16 kHz mono, cut it at pauses.

Speech-to-text runs on several pieces at once, so total time is about one piece's
time. Cutting at pauses (silences ffmpeg finds) keeps words whole at the seams.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

from .local import ffmpeg

AUDIO_SUFFIXES = {".m4a", ".webm", ".mp4", ".opus", ".ogg", ".mp3", ".aac", ".mka", ".weba"}
RATE = 16_000  # what speech models want; also small and fast to cut
# Speech needs little bitrate, and small files arrive sooner. YouTube now adds auto-dubbed
# tracks (an English dub of a Chinese talk), so the track marked "original" comes first.
SPEECH_FORMAT = "worstaudio[acodec!=none][format_note*=original]/worstaudio[acodec!=none]/bestaudio"
SEAM_WINDOW = 20.0  # look this far (seconds) either side of an even split for a pause


class AudioError(RuntimeError):
    pass


def js_runtimes() -> list[str]:
    """yt-dlp solves YouTube's JavaScript challenges with an outside runtime: the Deno that comes
    with the package (`deno` on PyPI), else Node if this computer has it."""
    try:
        import deno

        return ["--js-runtimes", f"deno:{deno.find_deno_bin()}"]
    except (ImportError, OSError, RuntimeError):
        node = shutil.which("node")
        return ["--js-runtimes", f"node:{node}"] if node else []


def fetch_youtube(video_id: str, folder: Path, fresh: bool = False) -> Path:
    """Download only the audio track (cached in `folder` unless `fresh`)."""
    folder.mkdir(parents=True, exist_ok=True)
    cached = _downloaded(folder)
    if cached and not fresh:
        return cached[0]
    for old in cached:
        old.unlink()
    cmd = [
        sys.executable, "-m", "yt_dlp", "-f", SPEECH_FORMAT, *js_runtimes(),
        "-o", str(folder / "audio.%(ext)s"), "--no-progress", "--quiet", "--no-warnings",
        "--print", "after_move:%(language)s", f"https://www.youtube.com/watch?v={video_id}",
    ]
    # YouTube changes which formats it offers from one request to the next and
    # sometimes offers none, so one retry after a pause is worth it.
    for attempt in range(2):
        done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        # Find the file on disk rather than trusting the printed path: on Windows a
        # non-ASCII folder name comes back garbled.
        got = _downloaded(folder)
        if done.returncode == 0 and got:
            lines = done.stdout.strip().splitlines()
            (folder / "audio.lang").write_text(lines[-1].strip() if lines else "", encoding="utf-8")
            return got[0]
        if attempt == 0:
            time.sleep(2)
    raise AudioError(f"yt-dlp could not fetch the audio: {done.stderr.strip()[-300:]}")


def _downloaded(folder: Path) -> list[Path]:
    """The downloaded audio file, by extension (the folder also holds audio.lang and partial files)."""
    return sorted(p for p in folder.glob("audio.*") if p.suffix.lower() in AUDIO_SUFFIXES)


def to_wav(src: Path, dst: Path) -> Path:
    """Any audio or video file -> 16 kHz mono 16-bit WAV."""
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(src),
           "-vn", "-ac", "1", "-ar", str(RATE), "-sample_fmt", "s16", str(dst)]
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
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
    err = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
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


def track_language(folder: Path) -> str | None:
    """The speech locale from the language YouTube labels the audio track with ("zh-Hant" -> zh_CN).

    Better than guessing from the title: a Chinese talk can have an English title. None when
    YouTube gave no label.
    """
    path = folder / "audio.lang"
    tag = path.read_text(encoding="utf-8").strip().lower() if path.exists() else ""
    base = tag.split("-")[0]
    return {"zh": "zh_CN", "yue": "yue_CN", "en": "en_US", "ja": "ja_JP", "ko": "ko_KR"}.get(base)
