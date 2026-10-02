"""Source -> Timeline, timing every stage."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import httpx

from . import audio, local, scenes, speech, storyboard, youtube
from .timeline import Timeline


class Stopwatch:
    def __init__(self) -> None:
        self.start = self.last = time.perf_counter()
        self.laps: dict[str, float] = {}

    def lap(self, name: str) -> None:
        now = time.perf_counter()
        self.laps[name] = round((now - self.last) * 1000, 1)
        self.last = now

    def total(self) -> float:
        return round((time.perf_counter() - self.start) * 1000, 1)


def build(source: str, level: int | None = None) -> Timeline:
    """A YouTube link/id or a local file -> Timeline with scenes."""
    if Path(source).expanduser().is_file():
        return from_file(str(Path(source).expanduser()))
    return asyncio.run(from_youtube(source, level))


async def from_youtube(ref: str, level: int | None = None) -> Timeline:
    clock = Stopwatch()
    video_id = youtube.parse_video_id(ref)
    async with httpx.AsyncClient(http2=True, timeout=20, follow_redirects=True) as client:
        # Open the thumbnail host's connection while YouTube is still generating
        # the page (~0.1 s saved on the sheets).
        warm = asyncio.create_task(_warm(client, video_id))
        page = await youtube.load(client, video_id)
        clock.lap("page")
        lv = youtube.pick_level(page.levels, level)
        await warm
        data = await storyboard.fetch_sheets(client, lv)
        clock.lap("thumbnails")
    sheets, frames, pixels = storyboard.cut_frames(lv, data, page.video.duration)
    clock.lap("decode")
    found = scenes.detect(frames, pixels, page.video.duration)
    clock.lap("scenes")
    clock.laps["total"] = clock.total()
    return Timeline(
        video=page.video,
        frames=frames,
        sheets=sheets,
        scenes=found,
        chapters=page.chapters,
        heat=page.heat,
        captions=page.captions,
        timings=clock.laps,
    )


def from_file(path: str) -> Timeline:
    clock = Stopwatch()
    video, sheets, frames, pixels = local.load(path)
    clock.lap("decode")
    found = scenes.detect(frames, pixels, video.duration)
    clock.lap("scenes")
    clock.laps["total"] = clock.total()
    return Timeline(video=video, frames=frames, sheets=sheets, scenes=found, timings=clock.laps)


def add_words(tl: Timeline, folder: Path, locale: str | None = None, fresh_audio: bool = False) -> None:
    """Fill in what was said: fetch the audio, cut it at pauses, transcribe the pieces at once."""
    clock = Stopwatch()
    folder.mkdir(parents=True, exist_ok=True)
    if tl.video.id:
        src = audio.fetch_youtube(tl.video.id, folder, fresh=fresh_audio)
        clock.lap("audio download")
    else:
        src = Path(tl.video.url)
    wav = audio.to_wav(src, folder / "audio16k.wav")
    total = audio.duration(wav)
    plan = audio.plan_pieces(total, audio.silences(wav), audio.piece_count(total))
    pieces = audio.cut(wav, plan, folder)
    clock.lap("audio prep")
    locale = locale or speech.guess_locale(tl.video.title)
    speech.ensure(locale)
    tl.transcript = speech.transcribe(pieces, locale)
    tl.language = locale
    clock.lap("speech")
    for path, _ in pieces:
        path.unlink(missing_ok=True)
    wav.unlink(missing_ok=True)
    tl.timings.update(clock.laps)
    tl.timings["words total"] = clock.total()


async def _warm(client: httpx.AsyncClient, video_id: str) -> None:
    try:
        await client.get(f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg", headers=youtube.HEADERS)
    except httpx.HTTPError:
        pass
