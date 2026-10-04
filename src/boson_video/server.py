"""boson-video serve: the pages, on this computer, with the video playing beside them and a
working ask box.

A page opened as a file can't embed YouTube's player or call a model, so this small server
serves `out/` on 127.0.0.1 and answers questions (study.answer). Every question and its answer
is kept in out/<video>/notes.json, so what you asked is there next time.
"""

from __future__ import annotations

import html
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import study
from .timeline import Segment, Sentence, Term, Timeline, Video

_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_lock = threading.Lock()  # notes.json is written by one request at a time


def load(folder: Path) -> Timeline:
    """Enough of timeline.json to answer questions: the video, the transcript, its English."""
    data = json.loads((folder / "timeline.json").read_text(encoding="utf-8"))
    tl = Timeline(video=Video(**data["video"]), frames=[], sheets=[])
    tl.transcript = [Segment(**s) for s in data.get("transcript", [])]
    tl.translation = data.get("translation", [])
    tl.language = data.get("language")
    tl.terms = [Term(**{**t, "said": Sentence(**t["said"])}) for t in data.get("terms", [])]
    return tl


def notes(folder: Path) -> list[dict]:
    path = folder / "notes.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def make_handler(root: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet; errors still go to stderr
            pass

        def _send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _folder(self, vid: str | None) -> Path | None:
            if not vid or not _ID.match(vid):
                return None
            folder = root / vid
            return folder if (folder / "timeline.json").exists() else None

        def do_GET(self):
            url = urlparse(self.path)
            parts = [p for p in url.path.split("/") if p]
            if not parts:
                return self._send(200, library(root).encode(), "text/html; charset=utf-8")
            if parts[0] == "v" and len(parts) == 2 and (folder := self._folder(parts[1])):
                if not url.path.endswith("/"):
                    self.send_response(301)
                    self.send_header("Location", url.path + "/")
                    return self.end_headers()
                return self._send(200, (folder / "index.html").read_bytes(), "text/html; charset=utf-8")
            if parts == ["api", "notes"]:
                folder = self._folder(parse_qs(url.query).get("v", [None])[0])
                return self._json(200, notes(folder)) if folder else self._json(404, {"error": "no such video"})
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            url = urlparse(self.path)
            if url.path != "/api/ask":
                return self._send(404, b"not found", "text/plain")
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            except json.JSONDecodeError:
                return self._json(400, {"error": "send JSON: {\"v\": id, \"q\": question}"})
            folder = self._folder(req.get("v"))
            question = (req.get("q") or "").strip()[:500]
            if not folder or not question:
                return self._json(400, {"error": "a video id and a question, please"})
            try:
                result = study.answer(load(folder), question)
            except study.StudyError as e:
                return self._json(502, {"error": str(e)})
            with _lock:
                kept = notes(folder)
                kept.insert(0, result)
                (folder / "notes.json").write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
            self._json(200, result)

    return Handler


def library(root: Path) -> str:
    """Every video built so far, newest first."""
    rows = []
    for tj in sorted(root.glob("*/timeline.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            v = json.loads(tj.read_text(encoding="utf-8"))["video"]
        except (json.JSONDecodeError, KeyError):
            continue
        d = int(v.get("duration", 0))
        asked = len(notes(tj.parent))
        rows.append(
            f'<li><a href="/v/{html.escape(tj.parent.name)}/">{html.escape(v.get("title") or tj.parent.name)}</a>'
            f'<span>{html.escape(v.get("channel") or "")} · {d // 60}:{d % 60:02d}'
            f'{f" · {asked} question" + ("s" if asked != 1 else "") if asked else ""}</span></li>'
        )
    items = "".join(rows) or "<li>Nothing yet. Run <code>boson-video &lt;link&gt;</code> first.</li>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Library · Boson-Video</title>
<style>:root{{--bg:#f4f5f7;--fg:#14171c;--muted:#5b626e;--line:#dde1e7;--card:#fff;--accent:#2450c2}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0f1115;--fg:#e7e9ee;--muted:#9ba2ae;--line:#2a2f38;--card:#171a20;--accent:#86a6ff;color-scheme:dark}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}}
main{{max-width:760px;margin:0 auto;padding:32px 16px}}h1{{font-size:22px;margin:0 0 16px}}
ul{{list-style:none;margin:0;padding:0;display:grid;gap:8px}}
li{{display:grid;gap:2px;padding:12px 14px;background:var(--card);border:1px solid var(--line);border-radius:10px}}
a{{color:var(--fg);font-weight:600;text-decoration:none}}a:hover{{color:var(--accent)}}span{{color:var(--muted);font-size:13px}}</style>
</head><body><main><h1>Your videos</h1><ul>{items}</ul></main></body></html>"""


def serve(root: Path, port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(root))
