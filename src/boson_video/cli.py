"""boson-video <youtube link | id | video file>  ->  out/<id>/index.html + timeline.json"""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

import httpx

from .local import LocalVideoError
from .pipeline import build
from .render import render
from .scenes import profile
from .youtube import YouTubeError


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="boson-video",
        description="See what happens in a video, and when, in about a second.",
    )
    ap.add_argument("source", help="YouTube link or id, or a local video file")
    ap.add_argument("-o", "--out", default="out", help="output folder (default: ./out)")
    ap.add_argument("--level", type=int, help="storyboard level to use (default: the sharpest)")
    ap.add_argument("--open", action="store_true", help="open the page in your browser")
    args = ap.parse_args(argv)

    started = time.perf_counter()
    try:
        tl = build(args.source, args.level)
    except (YouTubeError, LocalVideoError, httpx.HTTPError) as e:
        print(f"boson-video: {e}", file=sys.stderr)
        return 1

    folder = Path(args.out) / (tl.video.id or Path(tl.video.url).stem)
    folder.mkdir(parents=True, exist_ok=True)
    page = folder / "index.html"
    page.write_text(render(tl), encoding="utf-8")
    (folder / "timeline.json").write_text(json.dumps(tl.to_json(), ensure_ascii=False, indent=1), encoding="utf-8")
    wall = time.perf_counter() - started

    v = tl.video
    headline, _ = profile(tl.scenes, v.duration)
    new = sum(1 for s in tl.scenes if s.kind == "new")
    stages = " · ".join(f"{k} {ms / 1000:.2f} s" for k, ms in tl.timings.items() if k != "total")
    print(f"{v.title} · {v.channel + ' · ' if v.channel else ''}{int(v.duration // 60)}:{int(v.duration % 60):02d}")
    print(headline)
    print(f"{len(tl.frames)} frames → {len(tl.scenes)} scenes ({new} new visuals)")
    print(f"{stages} → page written in {wall:.2f} s")
    print(page)
    if args.open:
        webbrowser.open(page.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
