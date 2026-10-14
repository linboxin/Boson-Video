"""boson-video send <youtube link>: read a YouTube video on a server without the server touching YouTube.

YouTube serves the words and the pictures only to a browser it trusts (captions, the transcript
panel and the streams all carry its tokens), so a server can't fetch them, and getting around that
is ruled out. This computer does the two light parts, the scene map (about a second) and the sound
(seconds; about 50 MB for 2½ hours), and sends them in one file. The server transcribes, writes,
checks and serves the page; it never asks YouTube for anything.

The file is a zip with nothing compressed, so its size on the wire is its size on disk:
  timeline.json   the scene map: video, frames, scenes, chapters, heat, captions, sheet sizes
  sheets/<n>.jpg  the storyboard sheets the scene map was cut from (WebP from YouTube)
  audio.<ext>     the sound as YouTube gave it
  audio.lang      the language YouTube labels the sound with (may be empty)
The server checks every part (receive) before anything is kept.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from . import audio, library
from .timeline import Sheet, Timeline
from .youtube import YouTubeError, parse_video_id

SCENE_KEYS = ("format", "version", "video", "frames", "scenes", "chapters", "heat", "captions", "sheets", "timings_ms")
SCENE_TIMINGS = ("page", "thumbnails", "decode", "scenes", "total")
MAX_SHEETS = 400  # a 4-hour video has about 30
MAX_TIMELINE = 20 * 2**20
_SHEET = re.compile(r"^sheets/(\d{1,3})\.jpg$")


class SendError(ValueError):
    pass


# ---- this computer ---------------------------------------------------------------------------------


def pack(tl: Timeline, sound: Path, out: Path, lang: str = "") -> Path:
    """The scene map, its sheets and the sound in one uncompressed zip at `out`."""
    data = {k: v for k, v in tl.to_json().items() if k in SCENE_KEYS}
    data["timings_ms"] = {k: v for k, v in tl.timings.items() if k in SCENE_TIMINGS}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        z.writestr("timeline.json", json.dumps(data, ensure_ascii=False))
        for i, sheet in enumerate(tl.sheets):
            z.writestr(f"sheets/{i}.jpg", sheet.jpeg)
        z.write(sound, f"audio{sound.suffix.lower()}")
        z.writestr("audio.lang", lang)
    return out


def prepare(link: str, say=print) -> tuple[Timeline, Path, str]:
    """The scene map and the sound for `link`: from this computer's library when it has both
    (a video already read or sent from here), else made and fetched into the library, so sending it
    again doesn't ask YouTube twice (repeated downloads bring on its "not a bot" check)."""
    from .pipeline import build

    vid = parse_video_id(link)
    local = library.folder(vid)
    cached = audio._downloaded(local)
    if library.exists(vid) and cached:
        tl = library.load(vid, with_sheets=True)
        if tl.sheets:
            lang = (local / "audio.lang").read_text(encoding="utf-8").strip() if (local / "audio.lang").exists() else ""
            say(f"using the copy already on this computer ({local})")
            return tl, cached[0], lang
    t0 = time.perf_counter()
    tl = build(link)
    library.save(tl, local)
    say(f"{tl.video.title} · {_clock(tl.video.duration)}: scene map in {time.perf_counter() - t0:.1f} s")
    t0 = time.perf_counter()
    sound = audio.fetch_youtube(vid, local)
    lang = (local / "audio.lang").read_text(encoding="utf-8").strip() if (local / "audio.lang").exists() else ""
    say(f"sound in {time.perf_counter() - t0:.1f} s ({sound.stat().st_size / 2**20:.0f} MB)")
    return tl, sound, lang


def send(link: str, server: str, code: str, wait: bool = False, say=print) -> str:
    """Send `link` to `server` (invite `code`); returns the page's address."""
    import httpx

    server = server.rstrip("/")
    with tempfile.TemporaryDirectory(prefix="boson-send-") as tmp:
        tl, sound, lang = prepare(link, say)
        bundle = pack(tl, sound, Path(tmp) / "send.zip", lang)
        size = bundle.stat().st_size
        with httpx.Client(timeout=httpx.Timeout(30, write=600, read=120), follow_redirects=False) as client:
            r = client.post(f"{server}/api/join", json={"code": code}, headers={"X-BV": "1"})
            if r.status_code != 200:
                raise SendError(_said(r, "the server didn't take that invite code"))
            t0 = time.perf_counter()
            with bundle.open("rb") as f:
                r = client.post(f"{server}/api/send", content=f,
                                headers={"X-BV": "1", "Content-Type": "application/zip", "Content-Length": str(size)})
            if r.status_code != 200:
                raise SendError(_said(r, "the server refused it"))
            key = r.json()["key"]
            say(f"sent {size / 2**20:.0f} MB in {time.perf_counter() - t0:.1f} s")
            page = f"{server}/v/{key}"
            if wait:
                _follow(client, server, key, say)
    return page


def _follow(client, server: str, key: str, say) -> None:
    """Report the server's stages until it is done (Ctrl+C stops watching, not the server)."""
    last = None
    try:
        while True:
            r = client.get(f"{server}/api/video/{key}")
            if r.status_code != 200:
                say(_said(r, "stopped following the server"))
                return
            st = r.json().get("status", {})
            stage = st.get("stage")
            if stage != last:
                say(f"server: {stage}" + (f" ({st['note']})" if st.get("note") else "")
                    + (f": {st['error']}" if st.get("error") else "")
                    + "".join(f"\n  {why}" for why in (st.get("lacking") or {}).values()))
                last = stage
            if stage in ("done", "error", "missing"):
                return
            time.sleep(2)
    except KeyboardInterrupt:
        say("stopped watching; the server carries on")


def _said(r, fallback: str) -> str:
    if r.is_redirect:
        return f"{fallback}: the site is at {r.headers.get('location', '?')}; use --to with that address"
    try:
        return f"{fallback}: {r.json()['error']}"
    except (ValueError, KeyError, TypeError):
        return f"{fallback} (HTTP {r.status_code})"


def _clock(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def settings_path() -> Path:
    return library.home() / "send.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="boson-video send",
        description="Read a YouTube video on a Boson server: this computer makes the scene map and fetches the "
                    "sound (seconds), the server does the rest. The server never contacts YouTube.")
    ap.add_argument("link", help="YouTube link or id")
    ap.add_argument("--to", help="the server's address (remembered; default: BOSON_SERVER or the last one used)")
    ap.add_argument("--code", help="your invite code (remembered with the address)")
    ap.add_argument("--wait", action="store_true", help="follow the server until the page is done")
    args = ap.parse_args(argv)
    saved = {}
    if settings_path().exists():
        try:
            saved = json.loads(settings_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            saved = {}
    server = args.to or os.environ.get("BOSON_SERVER") or saved.get("server")
    if not server:
        print("boson-video send: which server? Add --to https://your-boson-site", file=sys.stderr)
        return 2
    code = args.code or (saved.get("code") if saved.get("server") == server else None)
    if not code:
        if not sys.stdin.isatty():
            print("boson-video send: add --code YOUR-CODE", file=sys.stderr)
            return 2
        code = input("Invite code: ").strip()
    try:
        page = send(args.link, server, code, args.wait)
    except (SendError, YouTubeError, audio.AudioError) as e:
        print(f"boson-video send: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # network trouble: say so in one line
        import httpx

        if isinstance(e, httpx.HTTPError):
            print(f"boson-video send: couldn't reach {server}: {e}", file=sys.stderr)
            return 1
        raise
    library.atomic_text(settings_path(), json.dumps({"server": server, "code": code}))
    os.chmod(settings_path(), 0o600)  # the invite code: for this account only
    print(page)
    return 0


# ---- the server ------------------------------------------------------------------------------------


def receive(bundle: Path, max_bytes: int) -> tuple[Timeline, str, str]:
    """Check a sent zip: (the scene map with its sheets, the sound's name in the zip, its language label).

    Only the four expected kinds of member, stored uncompressed, within `max_bytes` in all; the
    scene map must be a YouTube video's, each sheet a picture of the size the map says. Anything else
    is refused (SendError) before a byte is kept."""
    try:
        z = zipfile.ZipFile(bundle)
    except (zipfile.BadZipFile, OSError):
        raise SendError("that isn't a file `boson-video send` makes") from None
    with z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        if len(names) != len(set(names)):
            raise SendError("a part appears twice")
        if sum(i.file_size for i in infos) > max_bytes:
            raise SendError("too large")
        sounds = [n for n in names if re.fullmatch(r"audio\.[a-z0-9]{2,5}", n) and n != "audio.lang"]
        for i in infos:
            if i.compress_type != zipfile.ZIP_STORED:
                raise SendError("compressed parts aren't accepted")
            if not (i.filename in ("timeline.json", "audio.lang") or _SHEET.match(i.filename) or i.filename in sounds):
                raise SendError(f"unexpected part: {i.filename[:60]}")
        if len(sounds) != 1 or Path(sounds[0]).suffix not in audio.AUDIO_SUFFIXES:
            raise SendError("one sound file is needed")
        if "timeline.json" not in names or z.getinfo("timeline.json").file_size > MAX_TIMELINE:
            raise SendError("the scene map is missing")
        try:
            data = json.loads(z.read("timeline.json"))
            tl = _scene_map(data)
        except (ValueError, TypeError, KeyError, AttributeError, YouTubeError) as e:
            raise SendError(f"the scene map doesn't read: {str(e)[:120]}") from None
        declared = data.get("sheets") or []
        if len(declared) > MAX_SHEETS:
            raise SendError("too many sheets")
        for n, size in enumerate(declared):
            name = f"sheets/{n}.jpg"
            if name not in names:
                raise SendError(f"{name} is missing")
            jpeg = z.read(name)
            if _picture_size(jpeg) != (size["width"], size["height"]):
                raise SendError(f"{name} isn't the picture the scene map describes")
            tl.sheets.append(Sheet(jpeg, size["width"], size["height"]))
        if any(_SHEET.match(n) and int(_SHEET.match(n).group(1)) >= len(declared) for n in names):
            raise SendError("a sheet the scene map doesn't mention")
        if any(not 0 <= f.sheet < len(tl.sheets) for f in tl.frames):
            raise SendError("a frame points at a missing sheet")
        if not z.getinfo(sounds[0]).file_size:
            raise SendError("the sound is empty")
        lang = z.read("audio.lang").decode("utf-8", "replace").strip()[:20] if "audio.lang" in names else ""
    return tl, sounds[0], lang


def extract(bundle: Path, name: str, dst: Path) -> None:
    """Copy one checked part of the zip to `dst`, streamed and atomic."""
    part = dst.with_name(f".{dst.name}.{os.getpid()}.part")
    with zipfile.ZipFile(bundle) as z, z.open(name) as src, part.open("wb") as out:
        shutil.copyfileobj(src, out, 1 << 20)
    part.replace(dst)


def _scene_map(data: dict) -> Timeline:
    """Only the scene stage, from a computer we don't control: the words, the summary and the
    rest are made here."""
    if not isinstance(data, dict):
        raise ValueError("not an object")
    kept = {k: data[k] for k in SCENE_KEYS if k in data}
    video = kept.get("video")
    if not isinstance(video, dict):
        raise ValueError("no video")
    vid = parse_video_id(str(video.get("id") or ""))
    kept["video"] = {
        "title": _text(video.get("title"), 300), "channel": _text(video.get("channel"), 200),
        "duration": float(video.get("duration")), "url": f"https://www.youtube.com/watch?v={vid}", "id": vid,
        "description": _text(video.get("description"), 10_000),
    }
    if not 0 < kept["video"]["duration"] <= 24 * 3600:
        raise ValueError("an impossible length")
    timings = kept.get("timings_ms") or {}
    kept["timings_ms"] = {k: float(timings[k]) for k in SCENE_TIMINGS if isinstance(timings, dict) and k in timings}
    for k, most in (("frames", 20_000), ("scenes", 5_000), ("chapters", 500), ("heat", 1_000), ("captions", 200)):
        if not isinstance(kept.get(k, []), list) or len(kept.get(k, [])) > most:
            raise ValueError(f"too many {k}")
    tl = Timeline.from_json(kept, [])
    for c in tl.captions:
        c.lang, c.kind, c.name = _text(c.lang, 20), _text(c.kind, 10), _text(c.name, 100)
    for f in tl.frames:
        f.index, f.sheet, f.x, f.y, f.w, f.h = int(f.index), int(f.sheet), int(f.x), int(f.y), int(f.w), int(f.h)
        f.t = float(f.t)
    n = len(tl.frames)
    for s in tl.scenes:
        s.index, s.key, s.look, s.start, s.end = int(s.index), int(s.key), int(s.look), float(s.start), float(s.end)
        s.frames, s.changes = [int(i) for i in s.frames], [int(i) for i in s.changes]
        if s.kind not in ("new", "repeat", "base") or not all(0 <= i < n for i in [*s.frames, *s.changes, s.key]):
            raise ValueError("a scene that doesn't fit its frames")
    for c in tl.chapters:
        c.start, c.title = float(c.start), _text(c.title, 300)
    for h in tl.heat:
        h.start, h.duration, h.intensity = float(h.start), float(h.duration), float(h.intensity)
    return tl


def _text(x, limit: int) -> str:
    if x is None:
        return ""
    if not isinstance(x, str):
        raise ValueError("text expected")
    return x[:limit]


def _picture_size(data: bytes) -> tuple[int, int] | None:
    """A sheet's size: YouTube's storyboards are WebP (kept under .jpg), our own mosaics JPEG."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as im:
            return im.size if im.format in ("JPEG", "WEBP") else None
    except (UnidentifiedImageError, OSError, ValueError):
        return None
