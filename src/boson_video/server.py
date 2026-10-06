"""boson-video serve: the website, on this computer. Paste a YouTube link and read the video,
with the video playing beside the page and a working ask box.

A page opened as a file can't embed YouTube's player or call a model, so this small server
serves the library on 127.0.0.1, builds a pasted link in the background (jobs.py, the same
builder the plugin uses), and answers questions (study.answer). Every question and its answer
is kept in <video>/notes.json, so what you asked is there next time. It listens only on this
computer: YouTube downloads stay on the user's side (DIRECTION, "Not now").
"""

from __future__ import annotations

import html
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import jobs, library, study
from .timeline import Timeline
from .youtube import YouTubeError, parse_video_id

_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_FRAME = re.compile(r"^\d+(-thumb)?\.jpg$")
STALE = 600  # a build not running here whose status hasn't moved for this long has stopped (s)
STAGES = {"queued": "Starting", "scenes": "Mapping the scenes", "words": "Transcribing the words",
          "screens": "Reading what is on screen", "summary": "Writing the summary"}
_lock = threading.Lock()  # notes.json is written by one request at a time


def load(folder: Path) -> Timeline:
    """The video in this folder (without the sheet images; answering doesn't need them)."""
    return library.load(folder.name, folder.parent)


def notes(folder: Path) -> list[dict]:
    path = folder / "notes.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def build_status(root: Path, name: str) -> dict:
    """Where a video's build is, for the website: stage, whether its page exists, seconds left."""
    state = jobs.status(name, root)
    now = time.time()
    out = {"key": name, "stage": state.get("stage", "missing"), "page": library.exists(name, root)}
    eta = state.get("words_eta") if out["stage"] == "words" else state.get("screens_eta") if out["stage"] == "screens" else None
    if eta and eta - now >= 1:  # past the estimate, say nothing rather than "1 s left" for a minute
        out["eta_s"] = round(eta - now)
    for k in ("error", "failed_at", "note"):
        if state.get(k):
            out[k] = state[k]
    if out["stage"] in STAGES and not jobs.running(name) and now - state.get("updated", now) > STALE:
        out["stage"] = "stopped"  # the process that ran it ended (the plugin's, or an earlier server)
    return out


def make_handler(root: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet; errors still go to stderr
            pass

        def _send(self, status: int, body: bytes, kind: str, cache: str = "no-store") -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _folder(self, vid: str | None) -> Path | None:
            if not vid or not _ID.match(vid):
                return None
            folder = root / vid
            return folder if (folder / "timeline.json").exists() else None

        def _same_origin(self) -> bool:
            """Any web page you visit could post here and spend your API credits, so only JSON
            sent by our own pages counts: a cross-site page can't send JSON without asking first,
            and the Host check stops a rebound DNS name."""
            host = (self.headers.get("Host") or "").split(":")[0]
            origin = self.headers.get("Origin")
            json_body = (self.headers.get("Content-Type") or "").split(";")[0].strip() == "application/json"
            local_origin = origin is None or urlparse(origin).hostname in ("127.0.0.1", "localhost")
            return json_body and local_origin and host in ("127.0.0.1", "localhost")

        def do_GET(self):
            url = urlparse(self.path)
            parts = [p for p in url.path.split("/") if p]
            if not parts:
                return self._send(200, library_page(root).encode(), "text/html; charset=utf-8")
            if parts[0] == "v" and len(parts) == 2 and (folder := self._folder(parts[1])):
                if not url.path.endswith("/"):
                    self.send_response(301)
                    self.send_header("Location", url.path + "/")
                    return self.end_headers()
                return self._send(200, (folder / "index.html").read_bytes(), "text/html; charset=utf-8")
            if (parts[0] == "v" and len(parts) == 4 and parts[2] == "frames" and _FRAME.match(parts[3])
                    and (folder := self._folder(parts[1])) and (folder / "frames" / parts[3]).is_file()):
                # a frame's name is its time, and it never changes once fetched
                return self._send(200, (folder / "frames" / parts[3]).read_bytes(), "image/jpeg", "max-age=86400")
            if parts == ["api", "status"]:
                vid = parse_qs(url.query).get("v", [None])[0]
                if not vid or not _ID.match(vid):
                    return self._json(400, {"error": "which video?"})
                return self._json(200, build_status(root, vid))
            if parts == ["api", "notes"]:
                folder = self._folder(parse_qs(url.query).get("v", [None])[0])
                return self._json(200, notes(folder)) if folder else self._json(404, {"error": "no such video"})
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            url = urlparse(self.path)
            if url.path not in ("/api/ask", "/api/open"):
                return self._send(404, b"not found", "text/plain")
            if not self._same_origin():
                return self._json(403, {"error": "accepted only from the pages themselves"})
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            except json.JSONDecodeError:
                return self._json(400, {"error": "send JSON"})
            if url.path == "/api/open":
                return self._open(req)
            folder = self._folder(req.get("v"))
            question = (req.get("q") or "").strip()[:500]
            if not folder or not question:
                return self._json(400, {"error": "a video id and a question, please"})
            try:
                result = study.answer(load(folder), question)
            except study.StudyError as e:
                return self._json(502, {"error": str(e)})
            except Exception as e:  # anything else still answers, so the page can say what went wrong
                return self._json(500, {"error": f"{type(e).__name__}: {str(e)[:200]}"})
            with _lock:
                kept = notes(folder)
                kept.insert(0, result)
                (folder / "notes.json").write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
            self._json(200, result)

        def _open(self, req: dict) -> None:
            """Start building a pasted YouTube link (or carry on with it) and say where it stands.
            Only YouTube links: a path typed here would read files on this computer."""
            try:
                vid = parse_video_id(str(req.get("url") or "")[:500])
            except YouTubeError:
                return self._json(400, {"error": "Paste a YouTube link, like https://www.youtube.com/watch?v=qbReD1cGykQ"})
            name = jobs.start(f"https://www.youtube.com/watch?v={vid}", root)
            self._json(200, build_status(root, name))

    return Handler


LIBRARY_CSS = """
:root{--bg:#f4f5f7;--fg:#14171c;--muted:#5b626e;--line:#dde1e7;--card:#fff;--accent:#2450c2;--bad:#c0362c}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f1115;--fg:#e7e9ee;--muted:#9ba2ae;--line:#2a2f38;--card:#171a20;--accent:#86a6ff;--bad:#ff7a6e;color-scheme:dark}}
:root[data-theme=dark]{--bg:#0f1115;--fg:#e7e9ee;--muted:#9ba2ae;--line:#2a2f38;--card:#171a20;--accent:#86a6ff;--bad:#ff7a6e;color-scheme:dark}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
main{max-width:760px;margin:0 auto;padding:40px 16px}
h1{font-size:26px;margin:0}h2{font-size:15px;margin:32px 0 10px;color:var(--muted);font-weight:600}
.lede{margin:4px 0 20px;color:var(--muted)}
form{display:flex;gap:8px;flex-wrap:wrap}
input{flex:1 1 280px;min-width:0;padding:11px 12px;font:inherit;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:10px}
input:focus{outline:2px solid var(--accent);outline-offset:1px}
button{padding:11px 18px;font:inherit;font-weight:600;color:#fff;background:var(--accent);border:0;border-radius:10px;cursor:pointer}
button:disabled{opacity:.6;cursor:default}
#open-status{min-height:1.5em;margin:10px 0 0;color:var(--muted);font-size:14px}#open-status.bad{color:var(--bad)}
ul{list-style:none;margin:0;padding:0;display:grid;gap:8px}
li{display:grid;gap:2px;padding:12px 14px;background:var(--card);border:1px solid var(--line);border-radius:10px}
li a{color:var(--fg);font-weight:600;text-decoration:none}li a:hover{color:var(--accent)}li span{color:var(--muted);font-size:13px}
.note{margin-top:28px;color:var(--muted);font-size:13px}
"""

LIBRARY_JS = """
const form = document.getElementById("open-form"), input = document.getElementById("open-url");
const button = form.querySelector("button"), msg = document.getElementById("open-status");
const STAGES = %s;
const say = (text, bad) => { msg.textContent = text; msg.classList.toggle("bad", !!bad); };
form.addEventListener("submit", async e => {
  e.preventDefault();
  const url = input.value.trim();
  if (!url) return;
  button.disabled = true; say("Starting…");
  try {
    const r = await fetch("/api/open", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) });
    const s = await r.json();
    if (!r.ok) throw new Error(s.error || "That link couldn't be opened.");
    follow(s.key);
  } catch (err) { say(err.message, true); button.disabled = false; }
});
async function follow(key) {
  for (;;) {
    let s;
    try { s = await (await fetch("/api/status?v=" + encodeURIComponent(key))).json(); }
    catch { say("Lost the connection to boson-video serve.", true); button.disabled = false; return; }
    if (s.stage === "error") { say("Stopped while " + (STAGES[s.failed_at] || s.failed_at || "building").toLowerCase() + ": " + s.error, true); button.disabled = false; return; }
    if (s.stage === "stopped") { say("That build stopped before it finished. Open the link again to carry on.", true); button.disabled = false; return; }
    if (s.page) { location.href = "/v/" + encodeURIComponent(key) + "/"; return; }
    say((STAGES[s.stage] || "Working") + "…");
    await new Promise(r => setTimeout(r, 700));
  }
}
"""


def library_page(root: Path) -> str:
    """The website's front page: a box to paste a YouTube link, then every video built so far, newest first."""
    rows = []
    for tj in sorted(root.glob("*/timeline.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            v = json.loads(tj.read_text(encoding="utf-8"))["video"]
        except (json.JSONDecodeError, KeyError):
            continue
        d = int(v.get("duration", 0))
        asked = len(notes(tj.parent))
        stage = build_status(root, tj.parent.name)["stage"]
        rows.append(
            f'<li><a href="/v/{html.escape(tj.parent.name)}/">{html.escape(v.get("title") or tj.parent.name)}</a>'
            f'<span>{html.escape(v.get("channel") or "")} · {d // 60}:{d % 60:02d}'
            f'{f" · {asked} question" + ("s" if asked != 1 else "") if asked else ""}'
            f'{" · " + STAGES[stage].lower() + "…" if stage in STAGES else ""}</span></li>'
        )
    items = "".join(rows) or "<li><span>Nothing yet. Paste a link above.</span></li>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Boson-Video</title>
<style>{LIBRARY_CSS}</style>
</head><body><main>
<h1>Boson-Video</h1>
<p class="lede">Read any video like a document: what was said and shown, each line tied to its second.</p>
<form id="open-form"><input id="open-url" type="text" inputmode="url" autocomplete="off" autofocus
 placeholder="Paste a YouTube link" aria-label="YouTube link"><button type="submit">Read it</button></form>
<p id="open-status" role="status"></p>
<h2>Your videos</h2><ul>{items}</ul>
<p class="note">Runs on this computer. The scene map comes first, in seconds; the words follow, under a minute for a
half-hour video. Your own AI can read the same videos through the plugin (<code>boson-video mcp</code>).</p>
</main><script>{LIBRARY_JS % json.dumps(STAGES)}</script></body></html>"""


def serve(root: Path, port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(root))
