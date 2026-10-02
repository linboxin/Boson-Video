"""boson-video <youtube link | id | video file>  ->  out/<id>/index.html + timeline.json

The page is written twice: once with the scene map (about a second), then again
with the words once the speech is transcribed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

import httpx

from .audio import AudioError
from .local import LocalVideoError
from .pipeline import add_words, build
from .render import render
from .scenes import profile
from .speech import SpeechError
from .timeline import Timeline
from .youtube import YouTubeError


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="boson-video",
        description="Read a video like a document: scenes in about a second, then the words.",
    )
    ap.add_argument("source", help="YouTube link or id, or a local video file")
    ap.add_argument("-o", "--out", default="out", help="output folder (default: ./out)")
    ap.add_argument("--level", type=int, help="storyboard level to use (default: the sharpest)")
    ap.add_argument("--no-words", action="store_true", help="scenes only; skip the speech")
    ap.add_argument("--lang", help="speech language, e.g. zh_CN or en_US (default: guessed from the title)")
    ap.add_argument("--fresh-audio", action="store_true", help="download the audio again even if it is cached")
    ap.add_argument("--open", action="store_true", help="open the page in your browser")
    args = ap.parse_args(argv)

    started = time.perf_counter()
    try:
        tl = build(args.source, args.level)
    except (YouTubeError, LocalVideoError, httpx.HTTPError) as e:
        print(f"boson-video: {e}", file=sys.stderr)
        return 1

    folder = Path(args.out) / (tl.video.id or Path(tl.video.url).stem)
    page = _write(tl, folder)
    v = tl.video
    headline, _ = profile(tl.scenes, v.duration)
    new = sum(1 for s in tl.scenes if s.kind == "new")
    print(f"{v.title} · {v.channel + ' · ' if v.channel else ''}{int(v.duration // 60)}:{int(v.duration % 60):02d}")
    print(headline)
    print(f"{len(tl.frames)} frames → {len(tl.scenes)} scenes ({new} new visuals)")
    print(f"scenes ready in {time.perf_counter() - started:.2f} s ({_stages(tl, 'page', 'thumbnails', 'decode', 'scenes')})")
    print(page)
    if args.open:
        webbrowser.open(page.resolve().as_uri())

    if args.no_words:
        return 0
    try:
        add_words(tl, folder, args.lang, args.fresh_audio)
    except (AudioError, SpeechError, LocalVideoError) as e:
        print(f"boson-video: no words: {e}", file=sys.stderr)
        return 1
    _write(tl, folder)
    chars = sum(len(s.text) for s in tl.transcript)
    print(f"words ready in {time.perf_counter() - started:.2f} s: {len(tl.transcript)} passages, "
          f"{chars} characters, {tl.language} ({_stages(tl, 'audio download', 'audio prep', 'speech')})")
    return 0


def _write(tl: Timeline, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    page = folder / "index.html"
    page.write_text(render(tl), encoding="utf-8")
    (folder / "timeline.json").write_text(json.dumps(tl.to_json(), ensure_ascii=False, indent=1), encoding="utf-8")
    return page


def _stages(tl: Timeline, *names: str) -> str:
    return " · ".join(f"{n} {tl.timings[n] / 1000:.2f} s" for n in names if n in tl.timings)


if __name__ == "__main__":
    raise SystemExit(main())
