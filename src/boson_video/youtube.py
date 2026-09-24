"""YouTube: everything one watch-page request tells us, without downloading the video.

The watch page carries two JSON blobs:
- ytInitialPlayerResponse: title, duration, caption tracks, and the storyboard spec
  (the seek-bar preview thumbnails YouTube has already rendered for the video).
- ytInitialData: chapters and the "most replayed" heatmap.

YouTube's internal player API answers faster (~170 ms against ~800 ms for the page),
but it turns scripted clients away ("Sign in to confirm you're not a bot"), so the
page is the dependable source. In a browser extension this step is free: the page
is already loaded.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from .timeline import CaptionTrack, Chapter, HeatPoint, Video

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_PLAYER = re.compile(r"ytInitialPlayerResponse\s*=\s*\{")
_DATA = re.compile(r"ytInitialData\"?\]?\s*=\s*\{")


class YouTubeError(RuntimeError):
    pass


def parse_video_id(ref: str) -> str:
    """Accept a bare id or any common YouTube link form and return the 11-char id."""
    ref = ref.strip()
    if _ID.match(ref):
        return ref
    u = urlparse(ref if "://" in ref else "https://" + ref)
    host = (u.hostname or "").lower()
    for prefix in ("www.", "m.", "music."):
        host = host.removeprefix(prefix)
    parts = [p for p in u.path.split("/") if p]
    candidate = None
    if host == "youtu.be" and parts:
        candidate = parts[0]
    elif host in ("youtube.com", "youtube-nocookie.com"):
        if parts[:1] == ["watch"]:
            candidate = parse_qs(u.query).get("v", [None])[0]
        elif len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v", "e"):
            candidate = parts[1]
    if candidate and _ID.match(candidate):
        return candidate
    raise YouTubeError(f"not a YouTube video link or id: {ref!r}")


@dataclass
class StoryboardLevel:
    """One resolution of the seek-bar thumbnails: `count` frames on `cols` x `rows` sheets."""

    level: int
    width: int
    height: int
    count: int
    cols: int
    rows: int
    interval_ms: int  # 0 means the frames are spread evenly over the video
    url_template: str  # "$M" stands for the sheet number

    @property
    def per_sheet(self) -> int:
        return self.cols * self.rows

    @property
    def sheet_count(self) -> int:
        return -(-self.count // self.per_sheet)

    def sheet_url(self, m: int) -> str:
        return self.url_template.replace("$M", str(m))

    def frame_time(self, k: int, duration: float) -> float:
        t = k * self.interval_ms / 1000 if self.interval_ms else k * duration / self.count
        return min(t, max(duration - 0.5, 0.0))


def parse_storyboard(spec: str) -> list[StoryboardLevel]:
    """Parse `playerStoryboardSpecRenderer.spec`.

    Format: `BASE|w#h#count#cols#rows#interval_ms#name#sigh|...`, one `|` field per
    level (0 = smallest). BASE contains `$L` (level) and `$N` (name, which may contain `$M`).
    """
    parts = spec.split("|")
    base = urljoin("https://i.ytimg.com/", parts[0])
    levels = []
    for level, raw in enumerate(parts[1:]):
        f = raw.split("#")
        if len(f) != 8:
            continue
        try:
            w, h, count, cols, rows, interval = map(int, f[:6])
        except ValueError:
            continue
        if not (w and h and count and cols and rows):
            continue
        url = base.replace("$L", str(level)).replace("$N", f[6]) + "&sigh=" + f[7]
        levels.append(StoryboardLevel(level, w, h, count, cols, rows, interval, url))
    return levels


def pick_level(levels: list[StoryboardLevel], choice: int | None = None) -> StoryboardLevel:
    """The requested level, else the sharpest one (fewest seconds per frame wins ties)."""
    if not levels:
        raise YouTubeError("this video has no storyboard thumbnails")
    if choice is not None:
        for lv in levels:
            if lv.level == choice:
                return lv
        raise YouTubeError(f"no storyboard level {choice}; have {[lv.level for lv in levels]}")
    return max(levels, key=lambda lv: (lv.width * lv.height, lv.count))


@dataclass
class WatchPage:
    video: Video
    levels: list[StoryboardLevel]
    chapters: list[Chapter]
    heat: list[HeatPoint]
    captions: list[CaptionTrack]


async def load(client: httpx.AsyncClient, video_id: str) -> WatchPage:
    r = await client.get(f"https://www.youtube.com/watch?v={video_id}", headers=HEADERS)
    r.raise_for_status()
    if "consent." in r.url.host:
        raise YouTubeError("YouTube sent a cookie-consent page instead of the video (EU region)")
    return parse_watch_page(r.text, video_id)


def parse_watch_page(html: str, video_id: str) -> WatchPage:
    player = _json_at(html, _PLAYER)
    if player is None:
        raise YouTubeError("the watch page had no player data (YouTube changed or blocked it)")
    data = _json_at(html, _DATA) or {}
    video = parse_video(player, video_id)
    spec = ((player.get("storyboards") or {}).get("playerStoryboardSpecRenderer") or {}).get("spec")
    if not spec:
        live = "playerLiveStoryboardSpecRenderer" in (player.get("storyboards") or {})
        raise YouTubeError("live streams aren't supported yet" if live else "no storyboard for this video")
    return WatchPage(
        video=video,
        levels=parse_storyboard(spec),
        chapters=parse_chapters(data),
        heat=parse_heatmap(data),
        captions=parse_captions(player),
    )


def parse_video(player: dict, video_id: str) -> Video:
    status = player.get("playabilityStatus") or {}
    if status.get("status", "OK") != "OK":
        raise YouTubeError(f"YouTube won't show this video: {status.get('reason') or status.get('status')}")
    d = player.get("videoDetails") or {}
    return Video(
        title=d.get("title", ""),
        channel=d.get("author", ""),
        duration=float(d.get("lengthSeconds") or 0),
        url=f"https://www.youtube.com/watch?v={video_id}",
        id=video_id,
    )


def parse_chapters(data: dict) -> list[Chapter]:
    """Creator chapters if present, else YouTube's auto chapters."""
    groups: dict[str, list] = {}
    for entry in _walk_dicts(data):
        key, value = entry.get("key"), entry.get("value")
        if isinstance(key, str) and key.endswith("CHAPTERS") and isinstance(value, dict):
            groups.setdefault(key, value.get("chapters") or [])
    raw = groups.get("DESCRIPTION_CHAPTERS") or next(iter(groups.values()), None)
    if raw is None:
        raw = [{"chapterRenderer": c} for c in _walk_key(data, "chapterRenderer")]
    out, seen = [], set()
    for item in raw:
        c = item.get("chapterRenderer") or {}
        start, title = c.get("timeRangeStartMillis"), _text(c.get("title"))
        if start is None or (start, title) in seen:
            continue
        seen.add((start, title))
        out.append(Chapter(int(start) / 1000, title))
    return sorted(out, key=lambda c: c.start)


def parse_heatmap(data: dict) -> list[HeatPoint]:
    for markers in _walk_key(data, "markers"):
        if isinstance(markers, list) and markers and "intensityScoreNormalized" in markers[0]:
            return [
                HeatPoint(
                    int(m["startMillis"]) / 1000,
                    int(m["durationMillis"]) / 1000,
                    float(m["intensityScoreNormalized"]),
                )
                for m in markers
            ]
    old = list(_walk_key(data, "heatMarkerRenderer"))  # older page layout
    return [
        HeatPoint(
            int(m["timeRangeStartMillis"]) / 1000,
            int(m["markerDurationMillis"]) / 1000,
            float(m["heatMarkerIntensityScoreNormalized"]),
        )
        for m in old
    ]


def parse_captions(player: dict) -> list[CaptionTrack]:
    renderer = (player.get("captions") or {}).get("playerCaptionsTracklistRenderer") or {}
    return [
        CaptionTrack(
            lang=t.get("languageCode", ""),
            kind="asr" if t.get("kind") == "asr" else "manual",
            name=_text(t.get("name")),
        )
        for t in renderer.get("captionTracks") or []
    ]


def _json_at(html: str, marker: re.Pattern) -> dict | None:
    m = marker.search(html)
    if not m:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(html, m.end() - 1)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _text(o) -> str:
    if not isinstance(o, dict):
        return ""
    return o.get("simpleText") or "".join(r.get("text", "") for r in o.get("runs") or [])


def _walk_dicts(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk_dicts(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk_dicts(v)


def _walk_key(o, key: str):
    for d in _walk_dicts(o):
        if key in d:
            yield d[key]
