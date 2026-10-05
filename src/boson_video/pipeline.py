"""Source -> Timeline, timing every stage."""

from __future__ import annotations

import asyncio
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from . import audio, checker, local, mercury, scenes, sensevoice, speech, storyboard, study, writer, youtube
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
    """Fill in what was said: fetch the audio, then transcribe it on this computer.

    On a Mac, Apple's transcriber runs on pieces cut at pauses, all at once. Elsewhere
    SenseVoice transcribes the stretches of speech its voice detector finds.
    """
    clock = Stopwatch()
    folder.mkdir(parents=True, exist_ok=True)
    if tl.video.id:
        src = audio.fetch_youtube(tl.video.id, folder, fresh=fresh_audio)
        clock.lap("audio download")
    else:
        src = Path(tl.video.url)
    wav = audio.to_wav(src, folder / "audio16k.wav")
    locale = locale or audio.track_language(folder) or speech.guess_locale(tl.video.title, tl.video.description)
    if sys.platform == "darwin":
        total = audio.duration(wav)
        plan = audio.plan_pieces(total, audio.silences(wav), audio.piece_count(total))
        pieces = audio.cut(wav, plan, folder)
        clock.lap("audio prep")
        speech.ensure(locale)
        tl.transcript = speech.transcribe(pieces, locale)
        tl.transcriber = "Apple SpeechAnalyzer"
        clock.lap("speech")
        for path, _ in pieces:
            path.unlink(missing_ok=True)
    else:
        clock.lap("audio prep")
        try:
            tl.transcript, laps = sensevoice.transcribe(wav, locale)
        except sensevoice.SenseVoiceError as e:
            raise speech.SpeechError(str(e)) from None
        tl.transcriber = sensevoice.model_for(locale)
        clock.laps.update(laps)
        clock.last = time.perf_counter()
    tl.language = locale
    wav.unlink(missing_ok=True)
    tl.timings.update(clock.laps)
    tl.timings["words total"] = clock.total()


def add_summary(tl: Timeline, effort: str = "low") -> dict:
    """Write the summary, the English transcript and the glossary at once (Mercury), then check
    every cited sentence (Jev). The summary is required; the other two are extras, so a failure
    there is reported and the page goes on without it."""
    clock = Stopwatch()
    names = speech.names(tl.video.title, tl.video.channel, tl.video.description) + speech.title_terms(tl.video.title)
    language = writer.language_name(tl.language)
    extras: dict = {}
    with ThreadPoolExecutor(3) as pool:
        summary = pool.submit(writer.write, tl, names, effort)
        english = pool.submit(study.translate, tl, names) if language != "English" else None
        terms = pool.submit(study.glossary, tl, names, language)
        tl.summary, write_stats = summary.result()
        if language != "English":  # the writer sometimes skips the English; fill what's missing
            write_stats["english_filled"] = study.fill_summary_english(tl, names)
        clock.lap("write")
        try:
            if english:
                tl.translation, extras["translate"] = english.result()
            tl.terms, tl.questions, extras["glossary"] = terms.result()
        except mercury.MercuryError as e:
            extras["error"] = str(e)
    clock.lap("study")
    check_stats = checker.check(tl)
    clock.lap("check")
    tl.timings.update(clock.laps)
    return {"write": write_stats, "check": check_stats, **extras}


async def _warm(client: httpx.AsyncClient, video_id: str) -> None:
    try:
        await client.get(f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg", headers=youtube.HEADERS)
    except httpx.HTTPError:
        pass
