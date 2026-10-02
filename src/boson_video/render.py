"""One self-contained HTML page: the video as a vertical timeline of scenes.

Frames are shown straight from the sprite sheets (CSS background offsets), so
nothing is re-encoded and the page works offline. Each scene is a row, and what
was said during it sits in the same row; the summary will join it there.
"""

from __future__ import annotations

import base64
import html

from . import __version__
from .scenes import profile
from .timeline import Frame, Scene, Timeline


def render(tl: Timeline) -> str:
    v = tl.video
    headline, stats = profile(tl.scenes, v.duration)
    dense = len(tl.scenes) >= 30 and stats["median_scene_s"] <= 4  # fast cutting: a grid reads better
    frame_s = _spacing(tl.frames)
    sheets_css = "\n".join(
        f".s{i}{{background-image:url(data:image/jpeg;base64,{base64.b64encode(s.jpeg).decode()})}}"
        for i, s in enumerate(tl.sheets)
    )
    chapters = sorted(tl.chapters, key=lambda c: c.start)
    rows, ci = [], 0
    for s in tl.scenes:
        while ci < len(chapters) and chapters[ci].start <= s.start + 0.5:
            rows.append(f'<h2 class="chapter">{_e(chapters[ci].title)}</h2>')
            ci += 1
        rows.append(_scene_row(tl, s, dense))
    if dense and tl.transcript:
        rows.append('<h2 class="chapter said-all">What\'s said</h2>' + _said(tl, tl.transcript))
    timings = " · ".join(f"{k} {ms / 1000:.2f} s" for k, ms in tl.timings.items() if k != "total")
    total = tl.timings.get("total")
    title = _e(v.title or "Untitled video")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Boson-Video</title>
<style>
:root{{--bg:#f7f7f5;--fg:#1c1c1e;--muted:#6e6e73;--line:#e3e3df;--card:#fff;--new:#2f6fed;--repeat:#9aa3b5;--base:#c3c6cc;--heat:#e8590c}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#141416;--fg:#ececef;--muted:#9a9aa3;--line:#2b2b30;--card:#1c1c20;--new:#6c9cff;--repeat:#5f6675;--base:#44474f;--heat:#ff8a3d}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}}
main{{max-width:1080px;margin:0 auto;padding:28px 16px 64px}}
a{{color:inherit}}
header h1{{font-size:22px;line-height:1.3;margin:0 0 4px}}
header h1 a{{text-decoration:none}}
.meta{{color:var(--muted);font-size:14px}}
.headline{{font-size:17px;margin:16px 0 4px}}
.stats{{color:var(--muted);font-size:13px}}
.bar{{margin:20px 0 8px;position:relative}}
.bar svg{{display:block;width:100%;height:56px}}
.legend{{display:flex;gap:16px;flex-wrap:wrap;color:var(--muted);font-size:12px;margin-bottom:24px}}
.legend i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}}
h2.chapter{{font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);margin:28px 0 8px;padding-top:12px;border-top:1px solid var(--line)}}
.scene{{display:grid;grid-template-columns:88px minmax(0,1fr);gap:4px 16px;padding:14px 0;border-bottom:1px solid var(--line)}}
.when{{font-variant-numeric:tabular-nums;font-size:13px;color:var(--muted)}}
.when a{{font-weight:600;color:var(--fg);text-decoration:none}}
.when a:hover{{text-decoration:underline}}
.body{{display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap;min-width:0}}
.f{{display:block;background-repeat:no-repeat;border-radius:6px;flex:none;box-shadow:0 0 0 1px var(--line)}}
.strip{{display:flex;flex-wrap:wrap;gap:6px;max-width:100%}}
.strip .f{{border-radius:3px;opacity:.9}}
.strip .f:hover{{opacity:1;box-shadow:0 0 0 2px var(--new)}}
.scene.base,.scene.repeat{{padding:8px 0}}
.scene.base .body,.scene.repeat .body{{align-items:center}}
.note{{color:var(--muted);font-size:13px}}
.said{{grid-column:2;max-width:74ch;display:grid;gap:8px;margin-top:6px;font-size:15.5px;line-height:1.75}}
.said p{{margin:0}}
.said a{{font-size:12px;color:var(--muted);text-decoration:none;font-variant-numeric:tabular-nums;margin-right:8px}}
.said a:hover{{text-decoration:underline}}
.dense .said-all{{grid-column:1/-1}}
.dense > .said{{grid-column:1/-1}}
.scenes.dense{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:18px 14px}}
.dense .scene{{display:block;border:0;padding:0}}
.dense .when{{margin-bottom:4px}}
.dense .when br{{display:none}}
.dense .when a{{margin-right:6px}}
.dense h2.chapter{{grid-column:1/-1}}
footer{{margin-top:40px;color:var(--muted);font-size:12px}}
@media (max-width:560px){{.scene{{grid-template-columns:1fr}}.said{{grid-column:1}}}}
{sheets_css}
</style>
</head>
<body>
<main>
<header>
<h1><a href="{_e(v.link(0))}">{title}</a></h1>
<div class="meta">{_e(v.channel)}{" · " if v.channel else ""}{_clock(v.duration)}</div>
<p class="headline">{_e(headline)}</p>
<div class="stats">{len(tl.frames)} frames (one per {frame_s:.0f} s) → {len(tl.scenes)} scenes, {sum(1 for s in tl.scenes if s.kind == "new")} new visuals{_captions_note(tl)}{_words_note(tl)}</div>
</header>
<div class="bar">{_bar(tl)}</div>
<div class="legend"><span><i style="background:var(--new)"></i>new visual</span><span><i style="background:var(--repeat)"></i>seen before</span><span><i style="background:var(--base)"></i>base shot (host / camera)</span>{'<span><i style="background:var(--heat)"></i>most replayed</span>' if tl.heat else ""}</div>
<div class="scenes{" dense" if dense else ""}">
{"".join(rows)}
</div>
<footer>Built from the video's own storyboard thumbnails{" and its audio, transcribed on this Mac" if tl.transcript else "; nothing was downloaded but those"}. Ready in {total / 1000 if total else 0:.2f} s ({timings}). boson-video {__version__}</footer>
</main>
</body>
</html>
"""


def _scene_row(tl: Timeline, s: Scene, dense: bool = False) -> str:
    v = tl.video
    when = (
        f'<div class="when"><a href="{_e(v.link(s.start))}">{_clock(s.start)}</a><br>'
        f"{_duration(s.duration)}</div>"
    )
    key = tl.frames[s.key]
    if dense:
        body = f'<div class="body">{_frame(tl, key, 0.6, v.link(key.t))}</div>'
    elif s.kind == "new":
        steps = [tl.frames[i] for i in s.changes if i != s.key] if len(s.changes) > 1 else []
        strip = "".join(_frame(tl, f, 0.3, v.link(f.t)) for f in steps)
        body = f'<div class="body">{_frame(tl, key, 1.0, v.link(key.t))}'
        body += f'<div class="strip">{strip}</div></div>' if strip else "</div>"
    else:
        if s.kind == "base":
            share = sum(o.duration for o in tl.scenes if o.look == s.look) / max(v.duration, 1e-6)
            note = f"Base shot ({share:.0%} of the video): the picture it keeps returning to."
        else:
            first = next(o for o in tl.scenes if o.look == s.look)
            note = f'Same picture as <a href="#s{first.index}">{_clock(first.start)}</a>.'
        body = f'<div class="body">{_frame(tl, key, 0.4, v.link(key.t))}<span class="note">{note}</span></div>'
    said = "" if dense else _said(tl, tl.said_during(s.start, s.end))
    return f'<section class="scene {s.kind}" id="s{s.index}">{when}{body}{said}</section>'


def _said(tl: Timeline, segments) -> str:
    """What was said, one paragraph per stretch of speech, each linked to its second."""
    if not segments:
        return ""
    lang = (tl.language or "").replace("_", "-")
    paras = "".join(
        f'<p><a href="{_e(tl.video.link(g.start))}">{_clock(g.start)}</a>{_e(g.text)}</p>' for g in segments
    )
    return f'<div class="said" lang="{_e(lang)}">{paras}</div>'


def _words_note(tl: Timeline) -> str:
    if not tl.transcript:
        return ""
    language = {"zh": "Chinese", "en": "English", "yue": "Cantonese"}.get((tl.language or "").split("_")[0], tl.language)
    return f" · words: {len(tl.transcript)} passages in {language}, transcribed on this Mac"


def _frame(tl: Timeline, f: Frame, scale: float, href: str) -> str:
    sh = tl.sheets[f.sheet]
    style = (
        f"width:{f.w * scale:.0f}px;height:{f.h * scale:.0f}px;"
        f"background-size:{sh.width * scale:.0f}px {sh.height * scale:.0f}px;"
        f"background-position:-{f.x * scale:.0f}px -{f.y * scale:.0f}px"
    )
    return f'<a class="f s{f.sheet}" style="{style}" href="{_e(href)}" title="{_clock(f.t)}"></a>'


def _bar(tl: Timeline) -> str:
    """Scenes as coloured blocks on one line, the heatmap above, chapter ticks below."""
    dur = max(tl.video.duration, 1e-6)
    color = {"new": "var(--new)", "repeat": "var(--repeat)", "base": "var(--base)"}
    parts = []
    for s in tl.scenes:
        x, w = 1000 * s.start / dur, max(1000 * s.duration / dur - 0.6, 0.6)
        parts.append(
            f'<a href="#s{s.index}"><rect x="{x:.1f}" y="24" width="{w:.1f}" height="20" rx="1.5" '
            f'fill="{color[s.kind]}"><title>{_clock(s.start)}–{_clock(s.end)}</title></rect></a>'
        )
    if tl.heat:
        pts = " ".join(
            f"{1000 * (h.start + h.duration / 2) / dur:.1f},{20 - 18 * h.intensity:.1f}" for h in tl.heat
        )
        parts.append(f'<polyline points="{pts}" fill="none" stroke="var(--heat)" stroke-width="1.5"/>')
    for c in tl.chapters:
        x = 1000 * c.start / dur
        parts.append(
            f'<rect x="{x:.1f}" y="46" width="1" height="8" fill="var(--muted)"><title>{_e(c.title)}</title></rect>'
        )
    return f'<svg viewBox="0 0 1000 56" preserveAspectRatio="none" role="img" aria-label="scene timeline">{"".join(parts)}</svg>'


def _captions_note(tl: Timeline) -> str:
    if tl.video.id is None:
        return ""
    if not tl.captions:
        return " · no captions on this video"
    langs = sorted({f"{c.lang}{' (auto)' if c.kind == 'asr' else ''}" for c in tl.captions})
    return " · captions: " + ", ".join(langs)


def _spacing(frames: list[Frame]) -> float:
    if len(frames) < 2:
        return 0.0
    return (frames[-1].t - frames[0].t) / (len(frames) - 1)


def _clock(t: float) -> str:
    t = int(t)
    h, m, s = t // 3600, t // 60 % 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _duration(t: float) -> str:
    t = int(round(t))
    return f"{t // 60} min {t % 60:02d} s" if t >= 60 else f"{t} s"


def _e(s: str) -> str:
    return html.escape(s, quote=True)
