"""boson-video web: the product. One page: paste a YouTube link or drop a video file, then talk to
it. The summary comes first; answers cite their moments and show the frames.

Invite-only, without accounts. `boson-video invite` makes a code; the code lets a browser in (a
signed cookie) and is counted against a daily limit of new videos and of questions. Each code
sees the videos it opened. Videos are built in the background by jobs.py into BOSON_VIDEO_HOME,
the same home as the command line and the plugin.

`--hosted` is for a server: YouTube links are refused there, because YouTube downloads stay on the
user's side (docs/DIRECTION.md); uploads still work, and videos already built can be read. The
interface is app/index.html, app/app.css and app/app.js: plain JS, no libraries.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from . import frames, jobs, library, study, writer
from .scenes import profile
from .timeline import Timeline
from .youtube import YouTubeError, parse_video_id

APP = Path(__file__).with_name("app")
COOKIE = "bv"
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I/L to misread
VIDEO_TYPES = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
UPLOAD_MAX = int(os.environ.get("BOSON_UPLOAD_MAX_MB", "2048")) * 1024 * 1024
NO_CACHE = {"Cache-Control": "no-cache"}
_KEY = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_FRAME = re.compile(r"^\d+(-thumb)?\.jpg$")
_SHEET = re.compile(r"^\d+\.jpg$")
_lock = threading.Lock()  # invites, per-code state and notes are written one at a time
_cache: dict[str, tuple[float, Timeline, list[dict]]] = {}  # key → (mtime, document, sheet sizes)
_tries: dict[str, list[float]] = {}  # invite attempts per address, against guessing


# ---- invite codes and what each code has done ---------------------------------------------------


def invites(root: Path) -> dict[str, dict]:
    path = root / "invites.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def make_invite(root: Path, label: str = "", per_day: int = 10, asks_per_day: int = 100) -> str:
    code = "-".join("".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(2))
    with _lock:
        codes = invites(root)
        codes[code] = {"label": label, "per_day": per_day, "asks_per_day": asks_per_day, "made": time.strftime("%Y-%m-%d")}
        _write_json(root / "invites.json", codes)
    return code


def revoke(root: Path, code: str) -> bool:
    code = normal(code)
    with _lock:
        codes = invites(root)
        if code not in codes:
            return False
        codes[code]["revoked"] = True
        _write_json(root / "invites.json", codes)
    return True


def normal(code: str) -> str:
    """"abcd efgh", "ABCD-EFGH" and "abcdefgh" are the same code."""
    c = re.sub(r"[^A-Z0-9]", "", code.upper())
    return f"{c[:4]}-{c[4:]}" if len(c) == 8 else c


def code_id(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()[:16]


def _secret(root: Path) -> bytes:
    path = root / "web-secret"
    if not path.exists():
        root.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    return path.read_bytes().strip()


def _sign(root: Path, cid: str) -> str:
    return f"{cid}.{hmac.new(_secret(root), cid.encode(), hashlib.sha256).hexdigest()[:32]}"


def who(request: Request) -> tuple[str, dict] | None:
    """The code this browser came in with, if it is still good: (its id, its limits)."""
    root = request.app.state.root
    cid, _, _ = (request.cookies.get(COOKIE) or "").partition(".")
    if not cid or not hmac.compare_digest(request.cookies.get(COOKIE, ""), _sign(root, cid)):
        return None
    for code, info in invites(root).items():
        if code_id(code) == cid and not info.get("revoked"):
            return cid, info
    return None


def state(root: Path, cid: str) -> dict:
    """{"videos": [keys, newest first], "day": "YYYY-MM-DD", "built": n, "asked": n}"""
    path = root / "codes" / f"{cid}.json"
    st = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"videos": []}
    if st.get("day") != time.strftime("%Y-%m-%d"):
        st.update(day=time.strftime("%Y-%m-%d"), built=0, asked=0)
    return st


def _save_state(root: Path, cid: str, st: dict) -> None:
    (root / "codes").mkdir(parents=True, exist_ok=True)
    _write_json(root / "codes" / f"{cid}.json", st)


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)  # a new computer has no home folder yet
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _admit(root: Path, cid: str, info: dict, key: str) -> str | None:
    """Add `key` to this code's videos, counting it if it is a new build; the refusal, if over the limit."""
    with _lock:
        st = state(root, cid)
        new = not library.exists(key, root) and not jobs.running(key)
        if new and st["built"] >= info.get("per_day", 10):
            return f"This code has added {st['built']} new videos today, its limit. Videos already here still open."
        st["built"] += new
        st["videos"] = [key] + [k for k in st["videos"] if k != key]
        _save_state(root, cid, st)
    return None


# ---- the document, as the page reads it -----------------------------------------------------------


def load(root: Path, key: str) -> Timeline | None:
    hit = _load(root, key)
    return hit[1] if hit else None


def _load(root: Path, key: str) -> tuple[float, Timeline, list[dict]] | None:
    """The video and its sheets' sizes (the images stay on disk; the page fetches them)."""
    path = root / key / "timeline.json"
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    hit = _cache.get(key)
    if hit and hit[0] == mtime:
        return hit
    data = json.loads(path.read_text(encoding="utf-8"))
    _cache[key] = (mtime, Timeline.from_json(data, []), data.get("sheets", []))
    return _cache[key]


def document(tl: Timeline, key: str, sheets: list[dict] | None = None) -> dict:
    n = len(tl.transcript)
    english = tl.translation if len(tl.translation) == n else [""] * n

    def at(evidence: list[int]) -> float | None:
        ok = [tl.transcript[i].start for i in evidence if 0 <= i < n]
        return min(ok) if ok else None

    def sentence(x) -> dict:
        return {"text": x.text, "en": x.text_en, "t": at(x.evidence), "check": x.check,
                "p": round(x.check_p, 2), "note": x.check_note}

    summary = None
    if tl.summary:
        summary = {
            "tldr": [sentence(x) for x in tl.summary.tldr],
            "sections": [{"title": sec.title, "en": sec.title_en, "t": sec.start, "end": sec.end,
                          "sentences": [sentence(x) for x in sec.sentences]} for sec in tl.summary.sections],
            "writer": tl.summary.writer, "checker": tl.summary.checker,
        }
    headline, stats = profile(tl.scenes, tl.video.duration) if tl.scenes else ("", {})
    timings = {k: round(v / 1000, 2) for k, v in tl.timings.items()
               if k in ("total", "words total", "screens", "write", "study", "check")}
    return {
        "key": key,
        "video": {"title": tl.video.title, "channel": tl.video.channel, "duration": tl.video.duration,
                  "yt": tl.video.id, "file": not tl.video.id},
        "headline": headline,
        "dense": len(tl.scenes) >= 30 and stats.get("median_scene_s", 99) <= 4,  # fast cutting: a grid reads better
        "captions": [f"{c.lang}{' (auto)' if c.kind == 'asr' else ''}" for c in tl.captions],
        "timings": timings,
        # thumbnails cut from the sheets in the browser: [t, sheet, x, y, w, h]
        "frames": [[f.t, f.sheet, f.x, f.y, f.w, f.h] for f in tl.frames],
        "sheets": [{"url": f"/media/{key}/sheets/{i}.jpg", "w": s["width"], "h": s["height"]}
                   for i, s in enumerate(sheets or [])],
        "scenes": [{"start": s.start, "end": s.end, "kind": s.kind, "key": s.key, "look": s.look,
                    "changes": s.changes} for s in tl.scenes],
        "language": tl.language,
        "english": writer.language_name(tl.language) == "English",
        "transcriber": tl.transcriber,
        "chapters": [{"t": c.start, "title": c.title} for c in tl.chapters],
        "heat": [{"t": h.start, "d": h.duration, "v": h.intensity} for h in tl.heat],
        "visuals": [s.start for s in tl.scenes if s.kind == "new"],
        "transcript": [{"t": s.start, "e": s.end, "text": s.text, "en": en} for s, en in zip(tl.transcript, english)],
        "screens": [{"t": sc.t, "text": sc.text, "img": f"/media/{key}/{sc.image}"}
                    for sc in tl.screens if sc.text and sc.image],
        "terms": [{"term": t.term, "heard": t.heard, "en": t.en, "reading": t.reading, "explain": t.explain,
                   "said": t.said.text, "said_en": t.said.text_en, "check": t.said.check, "p": round(t.said.check_p, 2),
                   "t": at(t.said.evidence), "mentions": len(t.mentions),
                   "first": tl.transcript[t.mentions[0]].start if t.mentions else at(t.said.evidence)}
                  for t in tl.terms],
        "questions": tl.questions,
        "summary": summary,
    }


def picture(tl: Timeline, where: Path, t: float) -> Path | None:
    """The sharpest picture of second `t` already on disk: the last full-resolution frame of its
    scene at or before it (a repeated scene shows its first appearance), else the thumbnail."""
    scene = next((s for s in tl.scenes if s.start <= t < s.end), None)
    if scene is not None and scene.kind == "repeat":
        first = next((s for s in tl.scenes if s.look == scene.look and s.kind == "new"), None)
        scene, t = (first, first.end) if first else (scene, t)
    if scene is not None:
        best = None
        for m in frames.moments(tl, scene.start, scene.end, limit=10**6):
            path = where / "frames" / f"{int(max(0.0, min(m.t, tl.video.duration - 0.5)) * 1000)}.jpg"
            if m.t <= t + 0.5 and path.exists():
                best = path
        if best:
            return best
    (where / "frames").mkdir(parents=True, exist_ok=True)
    thumb = where / "frames" / f"{int(t * 1000)}-thumb.jpg"
    return thumb if thumb.exists() or frames._thumbnail(tl, where, t, thumb) else None


def notes(where: Path) -> list[dict]:
    path = where / "notes.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def cards(root: Path, cid: str) -> list[dict]:
    out = []
    for key in state(root, cid)["videos"]:
        video = {}
        try:
            video = json.loads((root / key / "timeline.json").read_text(encoding="utf-8"))["video"]
        except (OSError, json.JSONDecodeError, KeyError):
            pass
        out.append({"key": key, "title": video.get("title") or "", "channel": video.get("channel") or "",
                    "duration": video.get("duration") or 0, "stage": jobs.status(key, root).get("stage"),
                    "poster": f"https://i.ytimg.com/vi/{video['id']}/mqdefault.jpg" if video.get("id") else f"/media/{key}/poster"})
    return out


# ---- routes ---------------------------------------------------------------------------------------


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status)


def _post_guard(request: Request) -> JSONResponse | None:
    """Only our own page posts here: a custom header can't be sent cross-site without a preflight we
    never answer, and the Origin, when sent, must be this site, or the public address in front of
    it (BOSON_PUBLIC_URL: a free *.vercel.app name forwarding to this server)."""
    origin = request.headers.get("origin")
    ours = {request.headers.get("host"), urlparse(os.environ.get("BOSON_PUBLIC_URL", "")).netloc} - {None, ""}
    if request.headers.get("x-bv") != "1" or (origin and urlparse(origin).netloc not in ours):
        return _error(403, "requests are accepted only from the page itself")
    return None


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return body if isinstance(body, dict) else {}


async def page(request: Request) -> Response:
    return FileResponse(APP / "index.html", headers=NO_CACHE)


async def asset(request: Request) -> Response:
    name = request.path_params["name"]
    if name not in ("app.css", "app.js"):
        return Response("not found", 404)
    return FileResponse(APP / name, headers=NO_CACHE)


async def me(request: Request) -> Response:
    hosted = request.app.state.hosted
    found = who(request)
    if not found:
        return JSONResponse({"in": False, "hosted": hosted})
    return JSONResponse({"in": True, "hosted": hosted, "videos": cards(request.app.state.root, found[0])})


async def join(request: Request) -> Response:
    if bad := _post_guard(request):
        return bad
    root, ip = request.app.state.root, request.client.host if request.client else "?"
    now = time.time()
    _tries[ip] = [x for x in _tries.get(ip, []) if now - x < 600] + [now]
    if len(_tries[ip]) > 20:
        return _error(429, "Too many tries. Wait a few minutes.")
    code = normal((await _json_body(request)).get("code") or "")
    info = invites(root).get(code)
    if not info or info.get("revoked"):
        return _error(403, "That code doesn't work.")
    response = JSONResponse({"in": True})
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(COOKIE, _sign(root, code_id(code)), max_age=180 * 86400, httponly=True, samesite="lax",
                        secure=https, path="/")
    return response


async def open_link(request: Request) -> Response:
    if bad := _post_guard(request):
        return bad
    if not (found := who(request)):
        return _error(401, "Enter your invite code first.")
    root, hosted = request.app.state.root, request.app.state.hosted
    try:
        vid = parse_video_id((await _json_body(request)).get("link") or "")
    except YouTubeError:
        return _error(400, "That doesn't look like a YouTube link.")
    if hosted and not library.exists(vid, root):
        return _error(403, "YouTube videos are added through the browser extension on this site. Upload a video file instead.")
    if refusal := _admit(root, *found, vid):
        return _error(429, refusal)
    if not hosted:  # on a server, a half-built video stays as it is: finishing it would download from YouTube
        jobs.start(f"https://www.youtube.com/watch?v={vid}", root)
    return JSONResponse({"key": vid})


async def upload(request: Request) -> Response:
    if bad := _post_guard(request):
        return bad
    if not (found := who(request)):
        return _error(401, "Enter your invite code first.")
    root = request.app.state.root
    name = unquote(request.headers.get("x-name") or "video.mp4")[:200]
    ext = Path(name).suffix.lower()
    if ext not in VIDEO_TYPES:
        return _error(400, f"Upload a video file ({', '.join(sorted(VIDEO_TYPES))}).")
    if int(request.headers.get("content-length") or 0) > UPLOAD_MAX:
        return _error(413, f"Videos up to {UPLOAD_MAX // 2**20} MB.")
    folder = root / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    tmp, digest, size = folder / f".part-{secrets.token_hex(6)}", hashlib.sha256(), 0
    with tmp.open("wb") as f:
        async for chunk in request.stream():
            size += len(chunk)
            if size > UPLOAD_MAX:
                break
            digest.update(chunk)
            f.write(chunk)
    if not 0 < size <= UPLOAD_MAX:
        tmp.unlink(missing_ok=True)
        return _error(413 if size else 400, f"Videos up to {UPLOAD_MAX // 2**20} MB." if size else "The file was empty.")
    key = digest.hexdigest()[:12]  # 12 characters: never a YouTube id, which has 11
    path = folder / f"{key}{ext}"
    if path.exists():
        tmp.unlink()
    else:
        tmp.replace(path)
    if refusal := _admit(root, *found, key):
        return _error(429, refusal)
    jobs.start(str(path), root, title=Path(name).stem[:120] or "Video")
    return JSONResponse({"key": key})


def _mine(request: Request) -> tuple[Path, str, str] | Response:
    """(home, code id, video key) when this browser may see the video in the path."""
    if not (found := who(request)):
        return _error(401, "Enter your invite code first.")
    root, key = request.app.state.root, request.path_params.get("key", "")
    if not _KEY.match(key) or key not in state(root, found[0])["videos"]:
        return _error(404, "No such video.")
    return root, found[0], key


async def video(request: Request) -> Response:
    if isinstance(mine := _mine(request), Response):
        return mine
    root, cid, key = mine
    status = jobs.status(key, root)
    hit = await run_in_threadpool(_load, root, key)
    if hit is None:
        return JSONResponse({"key": key, "status": status})
    asked = [x for x in notes(root / key) if x.get("by") == cid]
    return JSONResponse({**document(hit[1], key, hit[2]), "status": status, "notes": asked[::-1]})


async def ask(request: Request) -> Response:
    if bad := _post_guard(request):
        return bad
    if not (found := who(request)):
        return _error(401, "Enter your invite code first.")
    root, (cid, info) = request.app.state.root, found
    body = await _json_body(request)
    key, question = str(body.get("key") or ""), (body.get("q") or "").strip()[:500]
    if not question or not _KEY.match(key) or key not in state(root, cid)["videos"]:
        return _error(400, "A video and a question, please.")
    tl = await run_in_threadpool(load, root, key)
    if tl is None or not tl.transcript:
        return _error(409, "The words aren't ready yet. Ask again in a moment.")
    with _lock:
        st = state(root, cid)
        if st["asked"] >= info.get("asks_per_day", 100):
            return _error(429, f"This code has asked {st['asked']} questions today, its limit.")
        st["asked"] += 1
        _save_state(root, cid, st)
    try:
        result = await run_in_threadpool(study.answer, tl, question, where=root / key)
    except study.StudyError as e:
        return _error(502, f"Couldn't answer: {e}")
    except Exception as e:  # still an answer the page can show
        return _error(500, f"Couldn't answer: {type(e).__name__}: {str(e)[:200]}")
    times = [a["t"] for a in result["answer"] if a.get("t") is not None] + [m["t"] for m in result["moments"]]
    shown: dict[str, float] = {}
    for t in times:
        path = await run_in_threadpool(picture, tl, root / key, t)
        if path and path.name not in shown and len(shown) < 4:
            shown[path.name] = t
    result["frames"] = [{"t": t, "img": f"/media/{key}/frames/{name}"} for name, t in sorted(shown.items(), key=lambda x: x[1])]
    result["by"] = cid
    with _lock:
        kept = notes(root / key)
        kept.insert(0, result)
        _write_json(root / key / "notes.json", kept)
    return JSONResponse(result)


async def media(request: Request) -> Response:
    if isinstance(mine := _mine(request), Response):
        return mine
    root, _, key = mine
    where, kind, rest = root / key, request.path_params["kind"], request.path_params.get("rest", "")
    if kind == "frames" and _FRAME.match(rest) and (where / "frames" / rest).exists():
        return FileResponse(where / "frames" / rest)
    if kind == "sheets" and _SHEET.match(rest) and (where / "sheets" / rest).exists():
        return FileResponse(where / "sheets" / rest, headers={"Cache-Control": "private, max-age=86400"})
    tl = await run_in_threadpool(load, root, key)
    if tl is None:
        return Response("not found", 404)
    if kind in ("at", "poster"):
        t = int(rest) / 1000 if kind == "at" and rest.isdigit() else next(
            (s.start for s in tl.scenes if s.kind == "new"), 0.0)
        path = await run_in_threadpool(picture, tl, where, min(t, max(0.0, tl.video.duration - 0.5)))
        return FileResponse(path) if path else Response("not found", 404)
    if kind == "video" and not tl.video.id:
        path = Path(tl.video.url).resolve()
        if path.is_relative_to((root / "uploads").resolve()) and path.exists():
            return FileResponse(path)
    return Response("not found", 404)


def make_app(root: Path, hosted: bool = False) -> Starlette:
    app = Starlette(routes=[
        Route("/", page),
        Route("/v/{key}", page),
        Route("/app/{name}", asset),
        Route("/api/me", me),
        Route("/api/join", join, methods=["POST"]),
        Route("/api/open", open_link, methods=["POST"]),
        Route("/api/upload", upload, methods=["POST"]),
        Route("/api/ask", ask, methods=["POST"]),
        Route("/api/video/{key}", video),
        Route("/media/{key}/{kind}", media),
        Route("/media/{key}/{kind}/{rest}", media),
    ])
    app.state.root, app.state.hosted = root, hosted
    return app


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    from .env import load_env

    ap = argparse.ArgumentParser(prog="boson-video web", description="The product: invite-only, one page per video.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--hosted", action="store_true",
                    help="running on a server: refuse YouTube links (they come through the browser extension)")
    args = ap.parse_args(argv or [])
    load_env()
    from .env import missing

    for line in missing():
        print(f"warning: {line}. Put the key in .env here or in ~/.boson-video/.env", flush=True)
    root = library.home()
    if not invites(root):
        print(f"first invite code (yours): {make_invite(root, 'owner', per_day=50, asks_per_day=500)}")
    print(f"boson-video web on http://{args.host}:{args.port}{' (hosted: uploads only)' if args.hosted else ''}", flush=True)
    uvicorn.run(make_app(root, args.hosted), host=args.host, port=args.port, log_level="warning",
                proxy_headers=True, forwarded_allow_ips="*")
    return 0


def invite_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="boson-video invite", description="Invite codes for boson-video web.")
    ap.add_argument("label", nargs="?", default="", help="who it is for (only you see it)")
    ap.add_argument("--per-day", type=int, default=10, help="new videos a day (default 10)")
    ap.add_argument("--asks", type=int, default=100, help="questions a day (default 100)")
    ap.add_argument("--list", action="store_true", help="list the codes")
    ap.add_argument("--revoke", metavar="CODE", help="stop a code working")
    args = ap.parse_args(argv or [])
    root = library.home()
    if args.revoke:
        print("revoked" if revoke(root, args.revoke) else "no such code")
        return 0
    if args.list:
        for code, info in invites(root).items():
            st = state(root, code_id(code))
            print(f"{code}  {info.get('label') or '-':<16} {len(st['videos'])} videos  "
                  f"{info['per_day']} videos/{info['asks_per_day']} questions a day  made {info['made']}"
                  f"{'  REVOKED' if info.get('revoked') else ''}")
        return 0
    print(make_invite(root, args.label, args.per_day, args.asks))
    return 0
