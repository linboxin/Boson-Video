"""Building a video in the background, so no plugin call waits for a download or transcription.

`start` returns at once; a thread builds the scenes, saves the page, transcribes, saves again,
and writes the summary if there is a writing key. Progress goes to `status.json` in the video's
folder, so any process can read it: stage, when it started, an estimate of when the words will
be ready, and the error if one stopped it.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from . import library, llm

_running: dict[Path, Future] = {}
_lock = threading.Lock()
_pool: ThreadPoolExecutor | None = None


def words_estimate(duration: float) -> float:
    """Seconds from start to words (an estimate from measured runs, 2026-10-04): about 5 s of
    download plus, per minute of video, 0.75 s with SenseVoice on a 12-thread laptop or 0.35 s
    with Apple's transcriber on an M5."""
    per_minute = 0.35 if sys.platform == "darwin" else 0.75
    return 5 + per_minute * duration / 60


def status(name: str, root: Path | None = None) -> dict:
    """{"stage": "queued" | "scenes" | "words" | "screens" | "summary" | "done" | "error" | "missing", ...}"""
    where = library.folder(name, root)
    path = where / "status.json"
    for _ in range(20):
        if not path.exists():
            break
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):  # being replaced this instant (Windows)
            time.sleep(0.025)
    if library.exists(name, root):
        return {"stage": "done"}
    return {"stage": "missing"}


def running(name: str, root: Path | None = None) -> bool:
    with _lock:
        task = _running.get(library.folder(name, root).resolve())
        return bool(task and not task.done())


def start(ref: str, root: Path | None = None, words: bool = True, title: str | None = None) -> str:
    """Start building `ref` (a link, id or file) unless it is built or building; returns its key.
    `title` names an uploaded file, which is kept under its hash rather than its own name."""
    name = library.key(ref)
    root = (root or library.home()).resolve()
    where = library.folder(name, root)
    with _lock:
        task = _running.get(where)
        if task and not task.done():
            return name
        state = status(name, root)
        if state["stage"] == "done" and (not words or _complete(name, root)):
            return name
        # Persist the input before enqueueing: the hosted app resumes unfinished uploads on startup.
        if Path(ref).expanduser().is_file():
            ref = str(Path(ref).expanduser().resolve())
        library.atomic_text(where / "job.json", json.dumps({"ref": ref, "words": words, "title": title}))
        _write_status(where, stage="queued", started=time.time())
        global _pool
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=max(1, int(os.environ.get("BOSON_BUILD_WORKERS", "1"))),
                                       thread_name_prefix="build")
        for old in [key for key, task in _running.items() if task.done()]:
            del _running[old]
        _running[where] = _pool.submit(_build, ref, name, root, words, title)
    return name


def resume(root: Path, hosted: bool = False) -> int:
    """Resume interrupted jobs. Hosted recovery only reads uploads inside this data volume.

    Errors remain errors until retried by the user; a restart must not retry a permanent failure.
    Run one application process per data volume (the queue and locks are process-local).
    """
    count = 0
    for path in sorted(root.glob("*/job.json")):
        if status(path.parent.name, root).get("stage") in ("done", "error"):
            continue
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
            ref = job["ref"]
            if not isinstance(ref, str):
                continue
            source = Path(ref).expanduser()
            if hosted and not (source.is_file() and source.resolve().is_relative_to((root / "uploads").resolve())):
                continue
            if library.key(ref) != path.parent.name:
                continue
            start(ref, root, words=bool(job.get("words", True)), title=job.get("title"))
            count += 1
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return count


def wait(name: str, seconds: float, root: Path | None = None, until: tuple[str, ...] = ("done", "error")) -> dict:
    """Wait up to `seconds` for the build to reach one of `until`; returns the status either way."""
    deadline = time.monotonic() + seconds
    while True:
        state = status(name, root)
        if state["stage"] in until or time.monotonic() >= deadline:
            return state
        time.sleep(0.25)


def _complete(name: str, root: Path | None) -> bool:
    """Built as far as this computer can: words, the screen read if OCR is installed, and the
    summary if there is a writing key (a video first opened without one gets it later)."""
    from . import screens

    try:
        data = json.loads((library.folder(name, root) / "timeline.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    timings = data.get("timings_ms", {})
    return ((bool(data.get("transcript")) or "words total" in timings)
            and ("screens" in timings or not screens.available())
            and (bool(data.get("summary")) or not data.get("transcript") or not llm.configured()))


def screens_estimate(moments: int) -> float:
    """Seconds to read the screen (estimate from 88 moments in 54 s, 2026-10-04)."""
    return 5 + 0.6 * moments


def _write_status(where: Path, **fields) -> None:
    where.mkdir(parents=True, exist_ok=True)
    tmp = where / f"status.{os.getpid()}.{threading.get_ident()}.tmp"  # one per writer
    tmp.write_text(json.dumps({**fields, "updated": time.time()}, ensure_ascii=False), encoding="utf-8")
    for _ in range(40):  # Windows refuses the replace while a reader has the file open
        try:
            os.replace(tmp, where / "status.json")
            return
        except PermissionError:
            time.sleep(0.025)
    tmp.unlink(missing_ok=True)


def _build(ref: str, name: str, root: Path | None, words: bool, title: str | None = None) -> None:
    from . import frames, screens
    from .pipeline import add_summary, add_words, build  # heavy imports stay off the plugin's start-up

    where = library.folder(name, root)
    started = time.time()
    stage = "scenes"
    try:
        _write_status(where, stage=stage, started=started)
        if library.exists(name, root):
            tl = library.load(name, root, with_sheets=True)
        else:
            tl = build(ref)
            if title:
                tl.video.title = title
            library.save(tl, where)
        if words and not tl.transcript and "words total" not in tl.timings:
            stage = "words"
            _write_status(where, stage=stage, started=started, words_eta=started + words_estimate(tl.video.duration))
            add_words(tl, where, say=lambda text: _write_status(where, stage=stage, started=started, note=text))
            library.save(tl, where)
        if words and "screens" not in tl.timings and screens.available():
            stage = "screens"
            count = len(frames.moments(tl, 0.0, None, limit=10**6))
            _write_status(where, stage=stage, started=started, screens_eta=time.time() + screens_estimate(count))
            t0 = time.perf_counter()
            tl.screens, laps = screens.read(tl, where)
            tl.timings.update(laps)
            tl.timings["screens"] = round((time.perf_counter() - t0) * 1000, 1)
            library.save(tl, where)
        if tl.transcript and tl.summary is None and llm.configured():
            stage = "summary"
            _write_status(where, stage=stage, started=started)
            try:
                add_summary(tl, where=where)
                library.save(tl, where)
            except Exception as e:  # the summary is an extra; the words are what the plugin needs
                _write_status(where, stage="done", started=started, note=f"no summary: {e}")
                return
        why = {}
        if tl.transcript and tl.summary is None and not llm.configured():
            why["note"] = ("No summary, English or terms: this server has no INCEPTION_API_KEY (Mercury writes them). "
                           "Put it in .env, or in ~/.boson-video/.env, restart, and open the video again.")
        _write_status(where, stage="done", started=started, seconds=round(time.time() - started, 1), **why)
    except Exception as e:
        _write_status(where, stage="error", started=started, failed_at=stage, error=str(e).strip().splitlines()[0][:300],
                      trace=traceback.format_exc()[-1500:])
