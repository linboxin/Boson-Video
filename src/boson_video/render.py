"""One self-contained HTML page: read a video like a document.

Top to bottom: the ribbon (drag along the video to see the frame and the words at any
second), the summary (every sentence linked to its second and checked against the
transcript, switchable to English), a search over what was said, then every scene with
the words spoken during it. Frames come straight from the sprite sheets through CSS
background offsets, so nothing is re-encoded and the page works offline.
"""

from __future__ import annotations

import base64
import html
import json

from . import __version__
from .scenes import profile
from .timeline import Frame, Scene, Section, Sentence, Timeline

LANGUAGE_LABELS = {"zh": "中文", "yue": "粵語", "en": "English"}

CSS = """
:root{--bg:#f7f7f5;--fg:#1c1c1e;--muted:#6e6e73;--line:#e3e3df;--card:#fff;--new:#2f6fed;--repeat:#9aa3b5;--base:#c3c6cc;--heat:#e8590c;--accent:#2450c2;--ok:#2e7a35;--warn:#a86400;--bad:#c0362c}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141416;--fg:#ececef;--muted:#9a9aa3;--line:#2b2b30;--card:#1c1c20;--new:#6c9cff;--repeat:#5f6675;--base:#44474f;--heat:#ff8a3d;--accent:#86a6ff;--ok:#72c477;--warn:#e0a240;--bad:#ff7a6e;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
main{max-width:1000px;margin:0 auto;padding:28px 16px 64px;display:grid;gap:30px}
a{color:inherit}
h1{font-size:22px;line-height:1.3;margin:0 0 4px;text-wrap:balance}
h1 a{text-decoration:none}
h2{font-size:17px;margin:0}
h3{font-size:16px;margin:0;font-weight:600}
.meta{color:var(--muted);font-size:14px}
.headline{font-size:17px;margin:14px 0 4px}
.stats,.note{color:var(--muted);font-size:13px}
.ts{font-size:12px;font-variant-numeric:tabular-nums;color:var(--accent);text-decoration:none;white-space:nowrap}
a.ts:hover,a.ts:focus-visible{text-decoration:underline}
#rib{display:block;width:100%;height:64px;cursor:crosshair;touch-action:none;border-radius:4px}
#rib:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.lane-heat{fill:var(--heat);fill-opacity:.18}
.lane-heat-line{fill:none;stroke:var(--heat);stroke-width:1.5}
.sc-new{fill:var(--new)}.sc-repeat{fill:var(--repeat)}.sc-base{fill:var(--base)}
.ch{fill:var(--muted);fill-opacity:.18}.ch-b{fill-opacity:.36}
#rib-cursor{stroke:var(--fg);stroke-width:1.5}
.legend{display:flex;gap:6px 16px;flex-wrap:wrap;color:var(--muted);font-size:12px;margin-top:6px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.readout{display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap;margin-top:12px;padding:12px;background:var(--card);border:1px solid var(--line);border-radius:10px}
.ro-text{flex:1;min-width:0;display:grid;gap:4px}
.ro-said{margin:0;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
.read-bar{display:flex;justify-content:space-between;align-items:center;gap:8px 16px;flex-wrap:wrap}
.toggle{display:inline-flex;border:1px solid var(--line);border-radius:999px;overflow:hidden}
.toggle button{font:inherit;font-size:13px;padding:3px 12px;border:0;background:transparent;color:var(--muted);cursor:pointer}
.toggle button[aria-pressed=true]{background:var(--fg);color:var(--bg)}
.tldr{font-size:17px;line-height:1.75;margin:12px 0 0;max-width:74ch}
.sec{padding-top:16px;margin-top:16px;border-top:1px solid var(--line)}
.sec-head{display:flex;gap:4px 12px;align-items:baseline;flex-wrap:wrap}
.sec .strip{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.lines{margin:10px 0 0;padding:0;list-style:none;display:grid;gap:8px;max-width:74ch}
.lines li{line-height:1.7}
.sent .ts{margin-right:6px}
.mark{font-size:12px;margin-left:6px;white-space:nowrap}
.mark.ok{color:var(--ok)}.mark.warn{color:var(--warn)}.mark.bad{color:var(--bad)}
.t-en{display:none}
.lang-en .t-orig{display:none}
.lang-en .t-en{display:inline}
.lang-en .sent:not(:has(.t-en)) .t-orig,.lang-en .title:not(:has(.t-en)) .t-orig{display:inline}
.search{display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--card);border:1px solid var(--line);border-radius:10px;margin-top:10px}
.search:focus-within{border-color:var(--accent)}
.search input{flex:1;min-width:0;border:0;background:transparent;color:var(--fg);font:inherit;font-size:16px;outline:none}
.hits{list-style:none;margin:10px 0 0;padding:0;display:grid;gap:6px;max-width:80ch}
.hits li{display:flex;gap:10px;align-items:baseline}
.hits mark{background:color-mix(in srgb,var(--heat) 30%,transparent);color:inherit;border-radius:2px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
h2.chapter{font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);margin:24px 0 8px;padding-top:12px;border-top:1px solid var(--line)}
.scene{display:grid;grid-template-columns:88px minmax(0,1fr);gap:4px 16px;padding:14px 0;border-bottom:1px solid var(--line)}
.when{font-variant-numeric:tabular-nums;font-size:13px;color:var(--muted)}
.when a{font-weight:600;color:var(--fg);text-decoration:none}
.when a:hover{text-decoration:underline}
.body{display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap;min-width:0}
.f{display:block;background-repeat:no-repeat;border-radius:6px;flex:none;box-shadow:0 0 0 1px var(--line)}
.strip{display:flex;flex-wrap:wrap;gap:6px;max-width:100%}
.strip .f{border-radius:3px;opacity:.92}
.strip .f:hover{opacity:1;box-shadow:0 0 0 2px var(--new)}
.scene.base,.scene.repeat{padding:8px 0}
.scene.base .body,.scene.repeat .body{align-items:center}
.said{grid-column:2;max-width:74ch;display:grid;gap:8px;margin-top:6px;font-size:15px;line-height:1.75}
.said p{margin:0}
.said a{font-size:12px;color:var(--muted);text-decoration:none;font-variant-numeric:tabular-nums;margin-right:8px}
.said a:hover{text-decoration:underline}
.scenes.dense{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:18px 14px}
.dense .scene{display:block;border:0;padding:0}
.dense .when{margin-bottom:4px}
.dense .when br{display:none}
.dense .when a{margin-right:6px}
.dense h2.chapter,.dense .said-all,.dense > .said{grid-column:1/-1}
footer{color:var(--muted);font-size:12px;line-height:1.6}
@media (max-width:560px){.scene{grid-template-columns:1fr}.said{grid-column:1}}
"""

JS = """
(() => {
  const D = DATA;
  const $ = id => document.getElementById(id);
  const clock = t => {
    t = Math.floor(t);
    const h = Math.floor(t / 3600), m = Math.floor(t / 60) % 60, s = String(t % 60).padStart(2, "0");
    return h ? h + ":" + String(m).padStart(2, "0") + ":" + s : m + ":" + s;
  };
  const link = t => D.link[0] + Math.floor(t) + D.link[1];
  const last = (list, t) => {  // index of the last item starting at or before t
    let lo = 0, hi = list.length - 1, at = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (list[mid][0] <= t) { at = mid; lo = mid + 1; } else hi = mid - 1; }
    return at;
  };
  const english = () => document.body.classList.contains("lang-en");

  const rib = $("rib"), cursor = $("rib-cursor"), frame = $("ro-frame");
  let pos = 0;
  function show(t) {
    pos = Math.max(0, Math.min(D.d - 0.01, t));
    const x = pos / D.d * 1000;
    cursor.setAttribute("x1", x); cursor.setAttribute("x2", x);
    const fi = last(D.frames, pos);
    if (fi >= 0) {
      const [, sheet, fx, fy, fw, fh] = D.frames[fi], [sw, shh] = D.sheets[sheet], k = 0.6;
      frame.className = "f s" + sheet;
      frame.style.cssText = `width:${fw * k}px;height:${fh * k}px;background-size:${sw * k}px ${shh * k}px;background-position:-${fx * k}px -${fy * k}px`;
    }
    $("ro-time").textContent = clock(pos);
    $("ro-time").href = link(pos);
    const si = last(D.sections, pos), ci = last(D.chapters, pos);
    $("ro-where").textContent = si >= 0 ? (english() && D.sections[si][2] ? D.sections[si][2] : D.sections[si][1])
      : ci >= 0 ? D.chapters[ci][1] : "";
    const gi = last(D.segs, pos);
    $("ro-said").textContent = gi >= 0 && pos <= D.segs[gi][1] + 3 ? D.segs[gi][2] : "";
    rib.setAttribute("aria-valuenow", Math.floor(pos));
    rib.setAttribute("aria-valuetext", clock(pos));
  }
  const fromPointer = e => { const r = rib.getBoundingClientRect(); show((e.clientX - r.left) / r.width * D.d); };
  rib.addEventListener("pointermove", fromPointer);
  rib.addEventListener("pointerdown", e => { rib.setPointerCapture(e.pointerId); fromPointer(e); });
  rib.addEventListener("dblclick", () => {
    const i = last(D.scenes, pos);
    if (i >= 0) document.getElementById("s" + D.scenes[i][2])?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  rib.addEventListener("keydown", e => {
    const step = e.shiftKey ? 60 : 10;
    const to = { ArrowRight: pos + step, ArrowLeft: pos - step, Home: 0, End: D.d }[e.key];
    if (to !== undefined) { show(to); e.preventDefault(); }
  });
  show(D.start);

  document.querySelectorAll("[data-lang]").forEach(b => b.addEventListener("click", () => {
    document.body.classList.toggle("lang-en", b.dataset.lang === "en");
    document.querySelectorAll("[data-lang]").forEach(o => o.setAttribute("aria-pressed", String(o === b)));
    show(pos);
  }));

  const q = $("q"), hits = $("hits");
  if (q && hits) q.addEventListener("input", () => {
    const needle = q.value.trim().toLowerCase();
    hits.replaceChildren();
    if (!needle) return;
    let shown = 0;
    for (const [start, , text] of D.segs) {
      const at = text.toLowerCase().indexOf(needle);
      if (at < 0) continue;
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.className = "ts"; a.href = link(start); a.textContent = clock(start);
      const snippet = document.createElement("span");
      const from = Math.max(0, at - 40), to = Math.min(text.length, at + needle.length + 60);
      const mark = document.createElement("mark");
      mark.textContent = text.slice(at, at + needle.length);
      snippet.append((from ? "…" : "") + text.slice(from, at), mark, text.slice(at + needle.length, to) + (to < text.length ? "…" : ""));
      li.append(a, snippet);
      li.addEventListener("mouseenter", () => show(start));
      hits.append(li);
      if (++shown >= 40) break;
    }
    if (!shown) { const li = document.createElement("li"); li.className = "note"; li.textContent = "Not said in this video."; hits.append(li); }
  });
})();
"""


def render(tl: Timeline) -> str:
    v = tl.video
    headline, stats = profile(tl.scenes, v.duration)
    dense = len(tl.scenes) >= 30 and stats["median_scene_s"] <= 4  # fast cutting: a grid reads better
    sheets_css = "\n".join(
        f".s{i}{{background-image:url(data:image/jpeg;base64,{base64.b64encode(s.jpeg).decode()})}}"
        for i, s in enumerate(tl.sheets)
    )
    title = _e(v.title or "Untitled video")
    data = _page_data(tl)
    return f"""<!doctype html>
<html lang="{_e(_html_lang(tl))}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Boson-Video</title>
<style>{CSS}{sheets_css}</style>
</head>
<body>
<main>
<header>
<h1><a href="{_e(v.link(0))}">{title}</a></h1>
<div class="meta">{_e(v.channel)}{" · " if v.channel else ""}{_clock(v.duration)}</div>
<p class="headline">{_e(headline)}</p>
<div class="stats">{len(tl.frames)} frames (one per {_spacing(tl.frames):.0f} s) → {len(tl.scenes)} scenes, {sum(1 for s in tl.scenes if s.kind == "new")} new visuals{_captions_note(tl)}{_words_note(tl)}</div>
</header>
{_ribbon(tl)}
{_read_view(tl)}
{_find(tl)}
{_scenes(tl, dense)}
<footer>{_footer(tl)}</footer>
</main>
<script>const DATA = {data};</script>
<script>{JS}</script>
</body>
</html>
"""


def _page_data(tl: Timeline) -> str:
    v = tl.video
    if v.id:
        link = [f"https://www.youtube.com/watch?v={v.id}&t=", "s"]
    else:
        link = [v.link(0).rsplit("#t=", 1)[0] + "#t=", ""]
    sections = tl.summary.sections if tl.summary else []
    data = {
        "d": max(v.duration, 1.0),
        "start": 0,
        "link": link,
        "frames": [[round(f.t, 2), f.sheet, f.x, f.y, f.w, f.h] for f in tl.frames],
        "sheets": [[s.width, s.height] for s in tl.sheets],
        "scenes": [[round(s.start, 2), round(s.end, 2), s.index] for s in tl.scenes],
        "chapters": [[round(c.start, 2), c.title] for c in sorted(tl.chapters, key=lambda c: c.start)],
        "sections": [[round(s.start, 2), s.title, s.title_en] for s in sections],
        "segs": [[round(s.start, 2), round(s.end, 2), s.text] for s in tl.transcript],
    }
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _ribbon(tl: Timeline) -> str:
    """The whole video on one strip: replay curve, scenes, chapters, and a cursor to drag."""
    dur = max(tl.video.duration, 1e-6)
    parts = []
    if tl.heat:
        pts = " ".join(f"{1000 * (h.start + h.duration / 2) / dur:.1f},{22 - 20 * h.intensity:.1f}" for h in tl.heat)
        parts.append(f'<polygon class="lane-heat" points="0,22 {pts} 1000,22"/>')
        parts.append(f'<polyline class="lane-heat-line" vector-effect="non-scaling-stroke" points="{pts}"/>')
    for s in tl.scenes:
        x, w = 1000 * s.start / dur, max(1000 * s.duration / dur - 0.6, 0.6)
        parts.append(f'<rect class="sc-{s.kind}" x="{x:.1f}" y="26" width="{w:.1f}" height="18"/>')
    chapters = sorted(tl.chapters, key=lambda c: c.start)
    for i, c in enumerate(chapters):
        end = chapters[i + 1].start if i + 1 < len(chapters) else dur
        x, w = 1000 * c.start / dur, max(1000 * (end - c.start) / dur - 1, 1)
        parts.append(f'<rect class="ch{" ch-b" if i % 2 else ""}" x="{x:.1f}" y="48" width="{w:.1f}" height="12"/>')
    parts.append('<line id="rib-cursor" x1="0" x2="0" y1="0" y2="64" vector-effect="non-scaling-stroke"/>')
    legend = (
        '<span><i style="background:var(--new)"></i>new visual</span>'
        '<span><i style="background:var(--repeat)"></i>seen before</span>'
        '<span><i style="background:var(--base)"></i>base shot (host / camera)</span>'
        + ('<span><i style="background:var(--heat)"></i>most replayed</span>' if tl.heat else "")
        + ('<span><i style="background:var(--muted);opacity:.4"></i>chapters</span>' if chapters else "")
    )
    return f"""<section aria-label="The whole video on one strip">
<svg id="rib" viewBox="0 0 1000 64" preserveAspectRatio="none" tabindex="0" role="slider" aria-label="Position in the video" aria-valuemin="0" aria-valuemax="{int(dur)}" aria-valuenow="0">{"".join(parts)}</svg>
<div class="legend">{legend}<span>drag, or use the arrow keys · double-click jumps to the scene</span></div>
<div class="readout" aria-live="polite"><div id="ro-frame" class="f"></div><div class="ro-text"><div><a id="ro-time" class="ts" href="{_e(tl.video.link(0))}">0:00</a> <strong id="ro-where"></strong></div><p id="ro-said" class="ro-said"></p></div></div>
</section>"""


def _read_view(tl: Timeline) -> str:
    s = tl.summary
    if s is None:
        return ""
    bilingual = any(x.text_en for x in s.sentences())
    toggle = ""
    if bilingual:
        label = LANGUAGE_LABELS.get((tl.language or "en").split("_")[0], "Original")
        toggle = (
            '<div class="toggle" role="group" aria-label="Language">'
            f'<button type="button" data-lang="orig" aria-pressed="true">{_e(label)}</button>'
            '<button type="button" data-lang="en" aria-pressed="false">English</button></div>'
        )
    tldr = " ".join(_sentence(tl, x) for x in s.tldr)
    sections = "".join(_section(tl, sec) for sec in s.sections)
    return f"""<section aria-labelledby="read-h">
<div class="read-bar"><h2 id="read-h">Summary</h2>{toggle}</div>
<p class="tldr">{tldr}</p>
{sections}
<p class="note" style="margin-top:16px">{_check_note(s.sentences())}</p>
</section>"""


def _section(tl: Timeline, sec: Section) -> str:
    title = f'<span class="t-orig">{_e(sec.title)}</span>' + (
        f'<span class="t-en" lang="en">{_e(sec.title_en)}</span>' if sec.title_en else ""
    )
    visuals = [x for x in tl.scenes if x.kind == "new" and sec.start <= x.start < sec.end][:4]
    strip = "".join(_frame(tl, tl.frames[x.key], 0.4, tl.video.link(x.start)) for x in visuals)
    lines = "".join(f"<li>{_sentence(tl, x)}</li>" for x in sec.sentences)
    return f"""<article class="sec">
<div class="sec-head"><h3 class="title">{title}</h3><a class="ts" href="{_e(tl.video.link(sec.start))}">{_clock(sec.start)} – {_clock(sec.end)}</a></div>
{f'<div class="strip">{strip}</div>' if strip else ""}
<ul class="lines">{lines}</ul>
</article>"""


MARKS = {
    "supported": ("ok", "✓", "Checked: the transcript says this"),
    "contradicted": ("bad", "✗", "The transcript says otherwise"),
    "unsupported": ("warn", "?", "The cited passages don't say this"),
    "uncited": ("warn", "?", "No transcript passage cited"),
}


def _sentence(tl: Timeline, x: Sentence) -> str:
    when = ""
    if x.evidence:
        t = min(tl.transcript[i].start for i in x.evidence)
        when = f'<a class="ts" href="{_e(tl.video.link(t))}">{_clock(t)}</a>'
    text = f'<span class="t-orig">{_e(x.text)}</span>'
    if x.text_en:
        text += f'<span class="t-en" lang="en">{_e(x.text_en)}</span>'
    mark = ""
    if x.check in MARKS:
        cls, sign, tip = MARKS[x.check]
        tip = f"{tip}: {x.check_note}" if x.check_note else f"{tip} (Jev {x.check_p:.2f})"
        mark = f'<span class="mark {cls}" title="{_e(tip)}">{sign}</span>'
    return f'<span class="sent">{when}{text}{mark}</span>'


def _check_note(sentences: list[Sentence]) -> str:
    checked = [s for s in sentences if s.check]
    if not checked:
        return "Sentences were not checked."
    ok = sum(1 for s in checked if s.check == "supported")
    return (f"{ok} of {len(checked)} sentences checked against the transcript passages they cite (✓). "
            "? means the cited passages don't say it; ✗ means they say otherwise. Hover a mark for Jev's confidence.")


def _find(tl: Timeline) -> str:
    if not tl.transcript:
        return ""
    target = tl.video.id or tl.video.url
    command = _e(f'boson-video ask {target} "your question"')
    return f"""<section aria-labelledby="find-h">
<h2 id="find-h">Find a moment</h2>
<label class="search" for="q"><span class="sr">Search what was said</span><input id="q" type="search" placeholder="Search what was said" autocomplete="off"></label>
<ol id="hits" class="hits"></ol>
<p class="note">To ask in your own words, run <code>{command}</code> and Jev points to the moment that answers it.</p>
</section>"""


def _scenes(tl: Timeline, dense: bool) -> str:
    chapters = sorted(tl.chapters, key=lambda c: c.start)
    rows, ci = [], 0
    for s in tl.scenes:
        while ci < len(chapters) and chapters[ci].start <= s.start + 0.5:
            rows.append(f'<h2 class="chapter">{_e(chapters[ci].title)}</h2>')
            ci += 1
        rows.append(_scene_row(tl, s, dense))
    if dense and tl.transcript:
        rows.append('<h2 class="chapter said-all">What\'s said</h2>' + _said(tl, tl.transcript))
    heading = "Scenes and everything said" if tl.transcript else "Scenes"
    return f"""<section aria-labelledby="scenes-h">
<h2 id="scenes-h">{heading}</h2>
<div class="scenes{" dense" if dense else ""}">
{"".join(rows)}
</div>
</section>"""


def _footer(tl: Timeline) -> str:
    t = tl.timings
    parts = [f"scenes ready in {t.get('total', 0) / 1000:.2f} s"]
    if "words total" in t:
        parts.append(f"words in {t['words total'] / 1000:.1f} s more")
    if "write" in t:
        parts.append(f"summary written in {t['write'] / 1000:.1f} s and checked in {t.get('check', 0) / 1000:.1f} s")
    source = "the video's storyboard thumbnails" + (", its audio transcribed on this Mac" if tl.transcript else "")
    models = ""
    if tl.summary:
        models = f" Summary by {tl.summary.writer}" + (f", checked by {tl.summary.checker}" if tl.summary.checker else "") + "."
    return f"Built from {source}: {'; '.join(parts)}.{models} boson-video {__version__}"


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


def _html_lang(tl: Timeline) -> str:
    return (tl.language or "en").replace("_", "-") if tl.summary or tl.transcript else "en"


def _frame(tl: Timeline, f: Frame, scale: float, href: str) -> str:
    sh = tl.sheets[f.sheet]
    style = (
        f"width:{f.w * scale:.0f}px;height:{f.h * scale:.0f}px;"
        f"background-size:{sh.width * scale:.0f}px {sh.height * scale:.0f}px;"
        f"background-position:-{f.x * scale:.0f}px -{f.y * scale:.0f}px"
    )
    return f'<a class="f s{f.sheet}" style="{style}" href="{_e(href)}" title="{_clock(f.t)}"></a>'


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
