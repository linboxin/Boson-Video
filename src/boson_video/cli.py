"""boson-video <youtube link | id | video file>  ->  out/<id>/index.html + timeline.json

The page is written twice: once with the scene map (about a second), then again
with the words once the speech is transcribed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import webbrowser
from pathlib import Path

import httpx

from . import library
from .ask import AskError, ask
from .audio import AudioError
from .checker import CheckError
from .env import load_env
from .local import LocalVideoError
from .pipeline import add_summary, add_words, build
from .scenes import profile
from .speech import SpeechError
from .timeline import Segment, Timeline, Video
from . import writer
from .writer import WriterError
from .youtube import YouTubeError


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # A YouTube id can start with a dash (-Ggc37xLj_Y), which the option parser would take for an
    # option; as a full link it can't be mistaken.
    argv = [f"https://www.youtube.com/watch?v={a}" if re.fullmatch(r"-[A-Za-z0-9_-]{10}", a) else a for a in argv]
    for stream in (sys.stdout, sys.stderr):  # Chinese titles on a Windows console
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if argv[:1] == ["ask"]:
        return ask_main(argv[1:])
    if argv[:1] == ["serve"]:
        return serve_main(argv[1:])
    if argv[:1] == ["mcp"]:
        from .mcp_server import main as mcp_main  # the plugin; stdout carries the protocol

        mcp_main()
        return 0
    ap = argparse.ArgumentParser(
        prog="boson-video",
        description="Read a video like a document: scenes in about a second, then the words.",
    )
    ap.add_argument("source", help="YouTube link or id, or a local video file")
    ap.add_argument("-o", "--out", help="where videos are kept (default: BOSON_VIDEO_HOME, else ~/.boson-video)")
    ap.add_argument("--level", type=int, help="storyboard level to use (default: the sharpest)")
    ap.add_argument("--no-words", action="store_true", help="scenes only; skip the speech")
    ap.add_argument("--lang", help="speech language, e.g. zh_CN or en_US (default: guessed from the title)")
    ap.add_argument("--fresh-audio", action="store_true", help="download the audio again even if it is cached")
    ap.add_argument("--no-summary", action="store_true", help="scenes and words only; skip the summary")
    ap.add_argument("--no-screens", action="store_true", help="don't read the text on screen")
    ap.add_argument("--effort", default="low", choices=["instant", "low", "medium", "high"],
                    help="how hard Mercury thinks while writing the summary (default: low)")
    ap.add_argument("--open", action="store_true", help="open the page in your browser")
    args = ap.parse_args(argv)

    load_env()
    started = time.perf_counter()
    try:
        tl = build(args.source, args.level)
    except (YouTubeError, LocalVideoError, httpx.HTTPError) as e:
        print(f"boson-video: {e}", file=sys.stderr)
        return 1

    folder = _home(args) / library.key(args.source)
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

    from . import screens

    if not args.no_screens and screens.available():
        t0 = time.perf_counter()
        tl.screens, laps = screens.read(tl, folder)
        tl.timings.update(laps)
        tl.timings["screens"] = round((time.perf_counter() - t0) * 1000, 1)
        _write(tl, folder)
        print(f"screen read in {time.perf_counter() - t0:.1f} s: {len(tl.screens)} moments, "
              f"{sum(1 for x in tl.screens if x.text)} with screen text, {sum(1 for x in tl.screens if x.subtitles)} with burned-in subtitles")
    if args.no_summary or not tl.transcript:
        return 0
    if not os.environ.get("INCEPTION_API_KEY"):
        print("no summary: no writing key (INCEPTION_API_KEY in .env). The page has the scenes, the words and "
              "search; your own AI can read the whole video through the plugin (boson-video mcp).")
        return 0
    try:
        stats = add_summary(tl, args.effort)
    except (WriterError, CheckError) as e:
        if writer.last_bad_reply:
            (folder / "writer-bad-reply.json").write_text(json.dumps(writer.last_bad_reply, ensure_ascii=False, indent=1))
        print(f"boson-video: no summary: {e}", file=sys.stderr)
        return 1
    _write(tl, folder)
    if "error" in stats:
        print(f"boson-video: no translation or glossary: {stats['error']}", file=sys.stderr)
    s = tl.summary
    print(f"summary ready in {time.perf_counter() - started:.2f} s: {len(s.sections)} sections, "
          f"{len(s.sentences())} sentences, {sum(x.check == 'supported' for x in s.sentences())} checked ✓ by {s.checker} "
          f"({_stages(tl, 'write', 'study', 'check')}; {stats['write']['output_tokens']} tokens written, ${stats['write']['cost_usd']:.4f})")
    if tl.terms or tl.translation:
        extra = sum(stats.get(k, {}).get("cost_usd", 0) for k in ("translate", "glossary"))
        print(f"study ready: {len(tl.terms)} terms, {len(tl.translation) - tl.translation.count('')} passages "
              f"in English (${extra:.4f})")
    print(f"read it with questions: boson-video serve --open {tl.video.id or folder.name}")
    return 0


def ask_main(argv: list[str]) -> int:
    """boson-video ask <video link | id | file> "question": the moments that answer it (Jev)."""
    ap = argparse.ArgumentParser(prog="boson-video ask", description="Find the moment in a video that answers a question.")
    ap.add_argument("source", help="the video, as given to boson-video before (its page must exist)")
    ap.add_argument("question")
    ap.add_argument("-o", "--out", help="where videos are kept (default: BOSON_VIDEO_HOME, else ~/.boson-video)")
    args = ap.parse_args(argv)
    load_env()
    path = _home(args) / library.key(args.source) / "timeline.json"
    if not path.exists():
        print(f"boson-video: run `boson-video {args.source}` first (no {path})", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = [Segment(**s) for s in data.get("transcript", [])]
    video = Video(**data["video"])
    try:
        found = ask(segments, args.question)
    except AskError as e:
        print(f"boson-video: {e}", file=sys.stderr)
        return 1
    print(f'"{args.question}": {found["verdict"]} (exists {found["exists"]:.2f}, {found["seconds"]:.2f} s)')
    for i, p in found["moments"]:
        seg = segments[i]
        print(f"  {_clock(seg.start):>7}  {p:.2f}  {seg.text[:90]}")
    if found["moments"] and found["verdict"] != "not in this video":
        print(video.link(segments[found["moments"][0][0]].start))
    return 0


def serve_main(argv: list[str]) -> int:
    """boson-video serve: the pages with the video playing beside them and a working ask box."""
    from .server import serve

    ap = argparse.ArgumentParser(prog="boson-video serve", description="Serve the pages on this computer, with asking.")
    ap.add_argument("-o", "--out", help="where videos are kept (default: BOSON_VIDEO_HOME, else ~/.boson-video)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", metavar="VIDEO", nargs="?", const="", help="open the library, or one video, in the browser")
    args = ap.parse_args(argv)
    load_env()
    httpd = serve(_home(args), args.port)
    base = f"http://127.0.0.1:{args.port}/"
    print(f"serving {_home(args).resolve()} at {base} (Ctrl+C stops)")
    if args.open is not None:
        target = base
        if args.open:
            target += f"v/{library.key(args.open)}/"
        webbrowser.open(target)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _home(args) -> Path:
    """Where videos are kept: -o if given, else the same place the plugin uses."""
    return Path(args.out).expanduser() if args.out else library.home()


def _clock(t: float) -> str:
    t = int(t)
    h, m, s = t // 3600, t // 60 % 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _write(tl: Timeline, folder: Path) -> Path:
    return library.save(tl, folder)


def _stages(tl: Timeline, *names: str) -> str:
    return " · ".join(f"{n} {tl.timings[n] / 1000:.2f} s" for n in names if n in tl.timings)


if __name__ == "__main__":
    raise SystemExit(main())
