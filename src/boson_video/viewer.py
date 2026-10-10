"""The video's page inside the user's AI app (MCP Apps): the page `boson-video web` shows, fed by the
plugin instead of a server. Apps that support MCP Apps (Claude, ChatGPT, Cursor, VS Code) show it in
the chat when `video_open` runs: the player, the ribbon, the readout, and the Summary, Transcript,
Terms, Scenes and Ask tabs. The page is app/app.css and app/app.js with app/mcp.js in front, which
asks the plugin for the document, frames and sheets through tools only the page can call, and sends
questions to the chat, where the user's own AI answers them. Apps without MCP Apps (a terminal) get
the text as before.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from PIL import Image

from . import jobs, library, web

APP = Path(__file__).parent / "app"
URI = "ui://boson-video/video.html"
# The YouTube player plays inside the page; everything else reaches it as data from the plugin.
FRAMES = ["https://www.youtube.com", "https://www.youtube-nocookie.com"]
RESOURCES = ["https://www.youtube.com", "https://s.ytimg.com", "https://i.ytimg.com"]
WIDTH = 640  # pictures go to the page at most this wide (a 1280 px frame is four times the bytes)


def page() -> str:
    """One self-contained document: the product page's style and script, with the bridge to the app first."""
    css, js, bridge = ((APP / name).read_text(encoding="utf-8") for name in ("app.css", "app.js", "mcp.js"))
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<meta name="color-scheme" content="light dark">\n<title>Video</title>\n'
            f"<style>\n{css}</style>\n</head>\n<body>\n<div id=\"root\"></div>\n"
            f"<script>\n{bridge}</script>\n<script>\n{js}</script>\n</body>\n</html>\n")


def document(video: str, since: str = "") -> dict:
    """The document as the page reads it, with the build's progress. `since` is the version the page
    already has: when nothing changed the answer is only that, since the page asks every 1.5 s."""
    key, root = library.key(video), library.home()
    status = jobs.status(key, root)
    hit = web.cached(root, key)
    version = hashlib.sha1(json.dumps([hit[0] if hit else 0, status], sort_keys=True).encode()).hexdigest()[:12]
    if since and since == version:
        return {"same": True, "version": version}
    doc = web.document(hit[1], key, hit[2]) if hit else {"key": key}
    return {**doc, "status": status, "version": version}


def picture(video: str, t: float) -> bytes | None:
    """The sharpest picture of second `t` on disk (web.picture), as a JPEG at most WIDTH wide. Whole
    seconds only, so a page can't make a thumbnail file for every millisecond."""
    key, root = library.key(video), library.home()
    tl = web.load(root, key)
    if tl is None:
        return None
    second = float(int(max(0.0, min(float(t), tl.video.duration - 0.5))))
    path = web.picture(tl, root / key, second)
    return _jpeg(path) if path else None


def sheet(video: str, index: int) -> bytes | None:
    """One thumbnail sheet, as stored; the page cuts the ribbon's previews from it."""
    path = library.folder(library.key(video)) / "sheets" / f"{int(index)}.jpg"
    return path.read_bytes() if int(index) >= 0 and path.is_file() else None


def _jpeg(path: Path) -> bytes:
    with Image.open(path) as im:
        if im.width > WIDTH:
            im = im.resize((WIDTH, round(im.height * WIDTH / im.width)))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=80)
    return buf.getvalue()
