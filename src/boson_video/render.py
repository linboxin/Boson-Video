"""One self-contained HTML page: read a video like a document, and learn from it.

Left, kept in view: the video (when the page is served, `boson-video serve`), the ribbon
(drag along the whole video to see the frame and the words at any second) and what is being
said right now, in the original and in English. Right, in tabs: the summary (every sentence
linked to its second and checked against the transcript), the transcript read line by line
with its English beneath and technical terms glossed above the characters, the terms
explained, the ask box, and every scene. Frames come straight from the sprite sheets through
CSS background offsets, so nothing is re-encoded and the page works offline (without the
player and the ask box, which need the server).
"""

from __future__ import annotations

import base64
import html
import json
import re

from . import __version__
from .scenes import profile
from .timeline import Frame, Scene, Section, Sentence, Term, Timeline

LANGUAGE_LABELS = {"zh": "中文", "yue": "粵語", "en": "English"}
LANGUAGE_NAMES = {"zh": "Chinese", "en": "English", "yue": "Cantonese"}
GLOSSED_MENTIONS = 2  # a term carries its English gloss on its first mentions; later ones are just marked

FONTS = ("https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600"
         "&family=JetBrains+Mono:wght@400;500&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600"
         "&family=Noto+Serif+SC:wght@400;600&display=swap")

CSS = """
:root{--bg:#f4f5f7;--fg:#14171c;--muted:#5b626e;--line:#dde1e7;--card:#fff;--new:#2f6fed;--repeat:#9aa3b5;--base:#c3c6cc;--heat:#c9761a;--accent:#2450c2;--ok:#2e7a35;--warn:#a86400;--bad:#c0362c;--gloss:#6d3fb0;--gloss-bg:#f1ebfa;--now:#fff6dc;
--ui:"Instrument Sans",system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
--read:"Source Serif 4","Noto Serif SC",Georgia,"Songti SC","SimSun",serif;
--mono:"JetBrains Mono",ui-monospace,"SF Mono",Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f1115;--fg:#e7e9ee;--muted:#9ba2ae;--line:#2a2f38;--card:#171a20;--new:#6c9cff;--repeat:#5f6675;--base:#44474f;--heat:#f0a640;--accent:#86a6ff;--ok:#72c477;--warn:#e0a240;--bad:#ff7a6e;--gloss:#c4a5f5;--gloss-bg:#2a2140;--now:#2c2717;color-scheme:dark}}
:root[data-theme=dark]{--bg:#0f1115;--fg:#e7e9ee;--muted:#9ba2ae;--line:#2a2f38;--card:#171a20;--new:#6c9cff;--repeat:#5f6675;--base:#44474f;--heat:#f0a640;--accent:#86a6ff;--ok:#72c477;--warn:#e0a240;--bad:#ff7a6e;--gloss:#c4a5f5;--gloss-bg:#2a2140;--now:#2c2717;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 var(--ui)}
a{color:inherit}
button{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.app{max-width:1360px;margin:0 auto;padding-inline:20px;padding-block:24px 64px}
.top{margin-bottom:20px;max-width:86ch}
.eyebrow{font-size:12px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
h1{font-size:clamp(22px,3vw,30px);line-height:1.2;margin:6px 0 0;font-weight:600;text-wrap:balance}
h1 a{text-decoration:none}
h2{font-size:17px;margin:0;font-weight:600}
h3{font-size:16px;margin:0;font-weight:600}
.headline{font-size:15px;margin:10px 0 2px}
.stats,.note{color:var(--muted);font-size:13px}
.ts{font:12px var(--mono);font-variant-numeric:tabular-nums;color:var(--accent);text-decoration:none;white-space:nowrap}
a.ts:hover,a.ts:focus-visible{text-decoration:underline}
.lbl{font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-family:var(--ui)}
/* the two columns: the video stays in view, the reading scrolls */
.study{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.08fr);gap:28px;align-items:start}
.stage{position:sticky;top:12px;display:grid;gap:14px}
.player-box{display:none;aspect-ratio:16/9;border-radius:10px;overflow:hidden;background:#000}
.has-player .player-box{display:block}
.player-box iframe,#player{width:100%;height:100%;border:0;display:block}
#rib{display:block;width:100%;height:64px;cursor:crosshair;touch-action:none;border-radius:4px}
.lane-heat{fill:var(--heat);fill-opacity:.2}
.lane-heat-line{fill:none;stroke:var(--heat);stroke-width:1.5}
.sc-new{fill:var(--new)}.sc-repeat{fill:var(--repeat)}.sc-base{fill:var(--base)}
.ch{fill:var(--muted);fill-opacity:.18}.ch-b{fill-opacity:.36}
#rib-cursor{stroke:var(--fg);stroke-width:1.5}
.legend{display:flex;gap:4px 14px;flex-wrap:wrap;color:var(--muted);font-size:12px;margin-top:6px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
.readout{display:flex;gap:14px;align-items:flex-start;padding:12px 14px;background:var(--card);border:1px solid var(--line);border-radius:10px}
.has-player .readout #ro-frame{display:none}
.ro-text{flex:1;min-width:0;display:grid;gap:4px}
.ro-said{margin:0;font:17px/1.7 var(--read)}
.ro-en{margin:0;color:var(--muted);font-size:14px}
/* tabs */
.bar{display:flex;justify-content:space-between;align-items:center;gap:8px 12px;flex-wrap:wrap;position:sticky;top:0;z-index:2;background:var(--bg);padding:6px 0 10px;border-bottom:1px solid var(--line)}
.tabs{display:flex;gap:2px;flex-wrap:wrap}
.tabs button{border:0;background:transparent;padding:6px 12px;border-radius:8px;cursor:pointer;color:var(--muted);font-weight:500}
.tabs button[aria-selected=true]{background:var(--card);color:var(--fg);box-shadow:0 0 0 1px var(--line)}
.tabs .count{font:11px var(--mono);margin-left:5px;color:var(--muted)}
.toggle{display:inline-flex;border:1px solid var(--line);border-radius:999px;overflow:hidden}
.toggle button{font-size:13px;padding:3px 12px;border:0;background:transparent;color:var(--muted);cursor:pointer}
.toggle button[aria-pressed=true]{background:var(--fg);color:var(--bg)}
.tab{padding-top:16px}
/* languages: original, both, English */
.t-en{display:none}
.lang-en .t-orig{display:none}
.lang-en .t-en{display:inline}
.lang-en .sent:not(:has(.t-en)) .t-orig,.lang-en .title:not(:has(.t-en)) .t-orig,.lang-en .ln:not(:has(.t-en)) .t-orig,.lang-en .tc-said:not(:has(.t-en)) .t-orig{display:inline}
.lang-both .t-en{display:block;color:var(--muted);font:14px/1.5 var(--ui);margin-top:2px}
.lang-both .title .t-en{display:inline;margin-left:8px}
.lang-en p.t-en,.lang-en .ln .t-en{display:block;font:16px/1.65 var(--read)}
/* summary */
.tldr{font:17px/1.75 var(--read);margin:0;max-width:70ch}
.tldr .sent{display:block;margin-bottom:6px}
.sec{padding-top:16px;margin-top:16px;border-top:1px solid var(--line)}
.sec-head{display:flex;gap:4px 12px;align-items:baseline;flex-wrap:wrap}
.lines{margin:10px 0 0;padding:0;list-style:none;display:grid;gap:10px;max-width:70ch}
.lines li{font:16px/1.7 var(--read)}
.sent .ts{margin-right:8px}
.mark{font:12px var(--ui);margin-left:6px;white-space:nowrap}
.mark.ok{color:var(--ok)}.mark.warn{color:var(--warn)}.mark.bad{color:var(--bad)}
/* transcript, read like a language reader */
.search{display:flex;align-items:center;gap:8px;padding:7px 12px;background:var(--card);border:1px solid var(--line);border-radius:10px}
.search:focus-within{border-color:var(--accent)}
.search input{flex:1;min-width:0;border:0;background:transparent;color:var(--fg);font:inherit;font-size:15px;outline:none}
.tools{display:flex;gap:10px 16px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.tools .search{flex:1;min-width:200px}
.tools label.follow{font-size:13px;color:var(--muted);display:flex;gap:6px;align-items:center;cursor:pointer}
.transcript{list-style:none;margin:0;padding:0}
.ln{display:grid;grid-template-columns:52px minmax(0,1fr);gap:2px 10px;padding:8px 8px;border-radius:8px}
.ln .ts{padding-top:6px}
.ln p{margin:0}
.ln .t-orig{font:17px/2.1 var(--read)}
.ln.now{background:var(--now)}
.ln[hidden]{display:none}
.ln mark.hit{background:color-mix(in srgb,var(--heat) 32%,transparent);color:inherit;border-radius:2px}
.chapter-row{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);padding:16px 8px 4px;border-top:1px solid var(--line);margin-top:8px;list-style:none}
.chapter-row:first-child{border-top:0;margin-top:0}
/* the signature: technical terms glossed above the characters */
.term{color:var(--gloss);text-decoration:underline dotted color-mix(in srgb,var(--gloss) 55%,transparent);text-underline-offset:4px;cursor:pointer;border-radius:3px;ruby-position:over}
.term:hover,.term:focus-visible{background:var(--gloss-bg)}
.term rt{font:500 10.5px/1 var(--ui);color:var(--gloss);letter-spacing:.01em;padding-bottom:1px}
.lang-en .ln .t-orig .term rt{display:none}
#card{position:absolute;z-index:5;width:min(360px,calc(100vw - 32px));background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:0 12px 32px rgb(0 0 0 / .14);padding:14px 16px;display:grid;gap:8px}
#card .c-head{display:flex;gap:4px 10px;align-items:baseline;flex-wrap:wrap}
#card .c-term{font:600 19px var(--read);color:var(--gloss)}
#card .c-read{font-size:13px;color:var(--muted)}
#card .c-en{font-weight:600}
#card p{margin:0;font-size:14px;line-height:1.55}
/* terms */
.terms{display:grid;gap:12px}
.term-card{padding:14px 16px;background:var(--card);border:1px solid var(--line);border-radius:10px;display:grid;gap:8px}
.term-card:target{box-shadow:0 0 0 2px var(--gloss)}
.tc-head{display:flex;gap:4px 12px;align-items:baseline;flex-wrap:wrap}
.tc-term{font:600 20px var(--read);color:var(--gloss)}
.tc-read{color:var(--muted);font-size:13px}
.tc-en{font-weight:600}
.tc-head .note{margin-left:auto}
.term-card p{margin:0}
.tc-said{font:15px/1.65 var(--read)}
/* ask */
.ask{display:flex;align-items:center;gap:8px;padding:6px 6px 6px 14px;background:var(--card);border:1px solid var(--line);border-radius:12px}
.ask:focus-within{border-color:var(--accent)}
.ask input{flex:1;min-width:0;border:0;background:transparent;color:var(--fg);font:inherit;font-size:16px;outline:none;padding:6px 0}
.ask button,.btn{border:0;background:var(--fg);color:var(--bg);border-radius:8px;padding:7px 16px;cursor:pointer;font-weight:500}
.ask button:disabled{opacity:.5;cursor:default}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.chips button{border:1px solid var(--line);background:var(--card);border-radius:999px;padding:4px 12px;font-size:13px;cursor:pointer;text-align:left}
.chips button:hover{border-color:var(--accent)}
.answers{list-style:none;margin:16px 0 0;padding:0;display:grid;gap:14px}
.qa{padding:14px 16px;background:var(--card);border:1px solid var(--line);border-radius:10px;display:grid;gap:10px}
.qa-q{margin:0;font-weight:600;font-size:16px}
.qa-q .note{font-weight:400;margin-left:8px}
.qa-a{display:grid;gap:6px;font:16px/1.65 var(--read)}
.qa-bg{padding:8px 12px;border-left:3px solid var(--line);font-size:14px;display:grid;gap:4px}
.qa details summary{cursor:pointer;font-size:13px;color:var(--muted)}
.qa details ul{list-style:none;margin:8px 0 0;padding:0;display:grid;gap:8px}
.qa details li{display:grid;grid-template-columns:52px minmax(0,1fr);gap:2px 10px;font-size:14px}
.qa details li span{display:block;color:var(--muted)}
.pending{color:var(--muted);font-size:14px}
/* scenes */
h2.chapter{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:20px 0 6px;padding-top:12px;border-top:1px solid var(--line);font-weight:600}
.scene{display:grid;grid-template-columns:72px minmax(0,1fr);gap:4px 14px;padding:12px 0;border-bottom:1px solid var(--line)}
.when{font:12px var(--mono);font-variant-numeric:tabular-nums;color:var(--muted)}
.when a{font-weight:500;color:var(--fg);text-decoration:none}
.when a:hover{text-decoration:underline}
.body{display:flex;gap:12px;align-items:flex-start;flex-wrap:wrap;min-width:0}
.f{display:block;background-repeat:no-repeat;border-radius:6px;flex:none;box-shadow:0 0 0 1px var(--line);max-width:100%}
.strip{display:flex;flex-wrap:wrap;gap:6px;max-width:100%}
.sec .strip{margin-top:10px}
.strip .f{border-radius:3px;opacity:.92}
.strip .f:hover{opacity:1;box-shadow:0 0 0 2px var(--new)}
.scene.base,.scene.repeat{padding:8px 0}
.scene.base .body,.scene.repeat .body{align-items:center}
.said{grid-column:2;max-width:70ch;display:grid;gap:6px;margin-top:6px;font:15px/1.75 var(--read)}
.said p{margin:0}
.said a{font:12px var(--mono);color:var(--muted);text-decoration:none;margin-right:8px}
.scenes.dense{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px 12px}
.dense .scene{display:block;border:0;padding:0}
.dense .when{margin-bottom:4px}
.dense .when br{display:none}
.dense .when a{margin-right:6px}
.dense h2.chapter,.dense .said-all,.dense > .said{grid-column:1/-1}
footer{color:var(--muted);font-size:12px;line-height:1.6;margin-top:40px;max-width:100ch}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
@media (max-width:900px){.study{grid-template-columns:1fr}.stage{position:static}.bar{top:0}}
@media (max-width:560px){.scene{grid-template-columns:1fr}.said{grid-column:1}.ln{grid-template-columns:44px minmax(0,1fr)}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
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
  const mode = () => document.body.dataset.lang || "orig";
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const served = /^https?:$/.test(location.protocol);

  // ---- the ribbon and what is said now
  const rib = $("rib"), cursor = $("rib-cursor"), frame = $("ro-frame");
  let pos = 0, hovering = false;
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
    $("ro-where").textContent = si >= 0 ? (mode() !== "orig" && D.sections[si][2] ? D.sections[si][2] : D.sections[si][1])
      : ci >= 0 ? D.chapters[ci][1] : "";
    const gi = last(D.segs, pos), near = gi >= 0 && pos <= D.segs[gi][1] + 3;
    $("ro-said").textContent = near && mode() !== "en" ? D.segs[gi][2] : (near && !D.en[gi] ? D.segs[gi][2] : "");
    $("ro-en").textContent = near && mode() !== "orig" ? (D.en[gi] || "") : "";
    if (mode() === "en" && near && D.en[gi]) $("ro-said").textContent = D.en[gi], $("ro-en").textContent = "";
    rib.setAttribute("aria-valuenow", Math.floor(pos));
    rib.setAttribute("aria-valuetext", clock(pos));
  }
  const at = e => { const r = rib.getBoundingClientRect(); return (e.clientX - r.left) / r.width * D.d; };
  let downX = null;
  rib.addEventListener("pointermove", e => { hovering = true; show(at(e)); });
  rib.addEventListener("pointerleave", () => { hovering = false; });
  rib.addEventListener("pointerdown", e => { rib.setPointerCapture(e.pointerId); downX = e.clientX; show(at(e)); });
  rib.addEventListener("pointerup", e => { if (player && downX !== null && Math.abs(e.clientX - downX) < 4) seek(at(e)); downX = null; });
  rib.addEventListener("keydown", e => {
    const step = e.shiftKey ? 60 : 10;
    const to = { ArrowRight: pos + step, ArrowLeft: pos - step, Home: 0, End: D.d }[e.key];
    if (to !== undefined) { show(to); e.preventDefault(); }
    if (e.key === "Enter" && player) seek(pos);
  });
  show(D.start);

  // ---- tabs
  const tabs = [...document.querySelectorAll("[role=tab]")];
  function open(name, focus) {
    tabs.forEach(b => {
      const on = b.dataset.tab === name;
      b.setAttribute("aria-selected", String(on)); b.tabIndex = on ? 0 : -1;
      $("tab-" + b.dataset.tab).hidden = !on;
      if (on && focus) b.focus();
    });
  }
  tabs.forEach((b, i) => {
    b.addEventListener("click", () => open(b.dataset.tab));
    b.addEventListener("keydown", e => {
      const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
      if (d) open(tabs[(i + d + tabs.length) % tabs.length].dataset.tab, true);
    });
  });
  const current = () => tabs.find(b => b.getAttribute("aria-selected") === "true")?.dataset.tab;
  const wanted = location.hash.slice(1);  // #words, #terms, #ask: a link straight to a tab
  if (tabs.some(b => b.dataset.tab === wanted)) open(wanted);

  // ---- languages
  document.querySelectorAll("[data-lang]").forEach(b => b.addEventListener("click", () => {
    document.body.dataset.lang = b.dataset.lang;
    document.body.classList.remove("lang-orig", "lang-both", "lang-en");
    document.body.classList.add("lang-" + b.dataset.lang);
    document.querySelectorAll("[data-lang]").forEach(o => o.setAttribute("aria-pressed", String(o.dataset.lang === b.dataset.lang)));
    show(pos);
  }));

  // ---- the player (only when served: a page opened as a file can't embed YouTube)
  let player = null, playing = false;
  if (D.yt && served) {
    document.body.classList.add("has-player");
    window.onYouTubeIframeAPIReady = () => {
      player = new YT.Player("player", {
        videoId: D.yt,
        playerVars: { playsinline: 1, rel: 0, start: Math.floor(D.start) },
        events: { onStateChange: e => { playing = e.data === 1; } },
      });
    };
    const s = document.createElement("script");
    s.src = "https://www.youtube.com/iframe_api";
    document.head.append(s);
    setInterval(() => {
      if (!player || !player.getCurrentTime || hovering) return;
      const t = player.getCurrentTime();
      if (playing) { show(t); follow(t); }
    }, 250);
  }
  function seek(t) {
    if (!player || !player.seekTo) return false;
    player.seekTo(t, true); player.playVideo();
    show(t); follow(t, true);
    return true;
  }
  document.addEventListener("click", e => {
    const a = e.target.closest("a[href]");
    if (!a || !player || !D.yt || !a.href.includes(D.yt)) return;
    const m = a.href.match(/[?&#]t=(\\d+)/);
    if (!m) return;
    const line = a.closest(".ln");
    if (seek(line ? +line.dataset.t : +m[1])) e.preventDefault();
  });

  // ---- the transcript follows the video
  const lines = [...document.querySelectorAll(".ln")];
  const followBox = $("follow");
  let lit = null;
  function follow(t, force) {
    const gi = last(D.segs, t);
    const li = gi >= 0 ? $("p" + gi) : null;
    if (li === lit) return;
    lit?.classList.remove("now");
    lit = li;
    if (!li) return;
    li.classList.add("now");
    if (current() === "words" && (force || followBox?.checked) && !li.hidden) {
      const r = li.getBoundingClientRect();
      if (r.top < 80 || r.bottom > innerHeight - 40) li.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  // ---- search the transcript, in both languages
  const q = $("q");
  if (q) q.addEventListener("input", () => {
    const needle = q.value.trim().toLowerCase();
    let shown = 0;
    lines.forEach(li => {
      li.querySelectorAll("mark.hit").forEach(m => m.replaceWith(...m.childNodes));
      li.normalize();
      const hit = !needle || li.textContent.toLowerCase().includes(needle);
      li.hidden = !hit;
      if (hit && needle) { shown++; markText(li, needle); }
    });
    document.querySelectorAll(".chapter-row").forEach(r => r.hidden = !!needle);
    $("q-count").textContent = needle ? (shown ? shown + " line" + (shown > 1 ? "s" : "") : "Not said in this video.") : "";
  });
  function markText(root, needle) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const hits = [];
    while (walker.nextNode()) {
      const n = walker.currentNode;
      if (n.parentElement.closest("rt,.ts")) continue;
      const i = n.data.toLowerCase().indexOf(needle);
      if (i >= 0) hits.push([n, i]);
    }
    for (const [n, i] of hits) {
      const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + needle.length);
      const m = el("mark", "hit"); r.surroundContents(m);
    }
  }

  // ---- a term's card
  const card = $("card");
  function hideCard() { card.hidden = true; }
  function showCard(target) {
    const t = D.terms[+target.dataset.k];
    if (!t) return;
    card.replaceChildren();
    const head = el("div", "c-head");
    head.append(el("span", "c-term", t.term));
    if (t.reading) head.append(el("span", "c-read", t.reading));
    if (t.en && t.en.toLowerCase() !== t.term.toLowerCase()) head.append(el("span", "c-en", t.en));
    card.append(head);
    if (t.explain) { const p = el("p"); p.append(el("span", "lbl", "Background "), " " + t.explain); card.append(p); }
    if (t.said) {
      const p = el("p");
      p.append(el("span", "lbl", "In this video "), " ");
      if (t.t != null) { const a = el("a", "ts", clock(t.t)); a.href = link(t.t); p.append(a, " "); }
      p.append(mode() === "orig" || !t.said_en ? t.said : t.said_en);
      card.append(p);
    }
    const more = el("a", "note", "All terms →"); more.href = "#term-" + target.dataset.k;
    more.addEventListener("click", e => { e.preventDefault(); hideCard(); open("terms"); $("term-" + target.dataset.k)?.scrollIntoView({ block: "center" }); });
    card.append(more);
    card.hidden = false;
    const r = target.getBoundingClientRect();
    const left = Math.min(scrollX + r.left, scrollX + innerWidth - card.offsetWidth - 16);
    card.style.left = Math.max(16, left) + "px";
    card.style.top = (scrollY + r.bottom + 8) + "px";
  }
  document.addEventListener("click", e => {
    const t = e.target.closest(".term");
    if (t) { e.preventDefault(); showCard(t); return; }
    if (!e.target.closest("#card")) hideCard();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") hideCard();
    if ((e.key === "Enter" || e.key === " ") && e.target.classList?.contains("term")) { e.preventDefault(); showCard(e.target); }
  });

  // ---- ask
  const form = $("ask-form"), input = $("ask-q"), status = $("ask-status"), answers = $("answers");
  if (form) {
    if (!served) {
      $("ask-offline").hidden = false;
      form.querySelector("button").disabled = true;
    } else {
      fetch("/api/notes?v=" + encodeURIComponent(D.key)).then(r => r.ok ? r.json() : []).then(list => list.forEach(a => answers.append(renderAnswer(a)))).catch(() => {});
    }
    form.addEventListener("submit", e => { e.preventDefault(); askIt(input.value); });
    document.querySelectorAll("#ask-starters button").forEach(b => b.addEventListener("click", () => { input.value = b.textContent; if (served) askIt(b.textContent); }));
  }
  async function askIt(question) {
    question = question.trim();
    if (!question || !served) return;
    const btn = form.querySelector("button");
    btn.disabled = true;
    const waiting = el("li", "qa");
    waiting.append(el("p", "qa-q", question), el("p", "pending", "Finding the moments and writing the answer…"));
    answers.prepend(waiting);
    status.textContent = "";
    try {
      const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ v: D.key, q: question }) });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "the server said " + r.status);
      waiting.replaceWith(renderAnswer(data));
      input.value = "";
    } catch (err) {
      waiting.remove();
      status.textContent = "Couldn't answer: " + err.message;
    } finally { btn.disabled = false; }
  }
  const MARK = { supported: ["ok", "✓", "Checked: the transcript says this"], contradicted: ["bad", "✗", "The transcript says otherwise"], unsupported: ["warn", "?", "The cited passages don't say this"], uncited: ["warn", "?", "No passage cited"] };
  function renderAnswer(a) {
    const li = el("li", "qa");
    const q = el("p", "qa-q", a.question);
    q.append(el("span", "note", a.verdict === "not in this video" ? "not in this video" : a.asked || ""));
    li.append(q);
    if (a.answer && a.answer.length) {
      const body = el("div", "qa-a");
      for (const s of a.answer) {
        const p = el("span", "sent");
        if (s.t != null) { const t = el("a", "ts", clock(s.t)); t.href = link(s.t); p.append(t); }
        p.append(s.text);
        const m = MARK[s.check];
        if (m) { const x = el("span", "mark " + m[0], m[1]); x.title = s.note ? m[2] + ": " + s.note : m[2]; p.append(x); }
        body.append(p);
      }
      li.append(body);
    }
    if (a.background && a.background.length) {
      const bg = el("div", "qa-bg");
      bg.append(el("span", "lbl", "Background, not from the video"));
      a.background.forEach(b => bg.append(el("span", null, b)));
      li.append(bg);
    }
    if (a.moments && a.moments.length && a.verdict !== "not in this video") {
      const d = el("details"), s = el("summary", null, "Where it's said");
      const ul = el("ul");
      for (const m of a.moments) {
        const row = el("li"), t = el("a", "ts", clock(m.t)); t.href = link(m.t);
        const words = el("div", null, m.text); if (m.en) words.append(el("span", null, m.en));
        row.append(t, words); ul.append(row);
      }
      d.append(s, ul); li.append(d);
    }
    return li;
  }
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
    bilingual = bool(tl.translation) or bool(tl.summary and any(x.text_en for x in tl.summary.sentences()))
    lang = "both" if bilingual else "orig"
    eyebrow = " · ".join(x for x in (_e(v.channel), _clock(v.duration), _language(tl)) if x)
    panels = [p for p in (
        ("read", "Summary", _read_view(tl), None),
        ("words", "Transcript", _transcript(tl), len(tl.transcript) or None),
        ("terms", "Terms", _terms(tl), len(tl.terms) or None),
        ("ask", "Ask", _ask(tl), None),
        ("scenes", "Scenes", _scenes(tl, dense), len(tl.scenes) or None),
    ) if p[2]]
    first = panels[0][0]
    tab_buttons = "".join(
        f'<button type="button" role="tab" id="t-{k}" data-tab="{k}" aria-controls="tab-{k}" '
        f'aria-selected="{str(k == first).lower()}" tabindex="{0 if k == first else -1}">{label}'
        f'{f"<span class=count>{n}</span>" if n else ""}</button>'
        for k, label, _, n in panels
    )
    tab_panels = "".join(
        f'<section class="tab" id="tab-{k}" role="tabpanel" aria-labelledby="t-{k}"{"" if k == first else " hidden"}>{body}</section>'
        for k, _, body, _ in panels
    )
    return f"""<!doctype html>
<html lang="{_e(_html_lang(tl))}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Boson-Video</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{_e(FONTS)}">
<style>{CSS}{sheets_css}</style>
</head>
<body class="lang-{lang}" data-lang="{lang}">
<div class="app">
<header class="top">
<div class="eyebrow">{eyebrow}</div>
<h1><a href="{_e(v.link(0))}">{title}</a></h1>
<p class="headline">{_e(headline)}</p>
<div class="stats">{len(tl.frames)} frames (one per {_spacing(tl.frames):.0f} s) → {len(tl.scenes)} scenes, {sum(1 for s in tl.scenes if s.kind == "new")} new visuals{_captions_note(tl)}{_words_note(tl)}</div>
</header>
<div class="study">
<div class="stage">
<div class="player-box"><div id="player"></div></div>
{_ribbon(tl)}
</div>
<div class="panel">
<div class="bar"><div class="tabs" role="tablist" aria-label="Ways to read this video">{tab_buttons}</div>{_toggle(tl, lang)}</div>
{tab_panels}
</div>
</div>
<footer>{_footer(tl)}</footer>
</div>
<div id="card" role="dialog" aria-label="Term" hidden></div>
<script>const DATA = {_page_data(tl)};</script>
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
    english = tl.translation if len(tl.translation) == len(tl.transcript) else [""] * len(tl.transcript)
    data = {
        "d": max(v.duration, 1.0),
        "start": 0,
        "link": link,
        "yt": v.id,
        "key": v.id or _stem(v.url),
        "frames": [[round(f.t, 2), f.sheet, f.x, f.y, f.w, f.h] for f in tl.frames],
        "sheets": [[s.width, s.height] for s in tl.sheets],
        "scenes": [[round(s.start, 2), round(s.end, 2), s.index] for s in tl.scenes],
        "chapters": [[round(c.start, 2), c.title] for c in sorted(tl.chapters, key=lambda c: c.start)],
        "sections": [[round(s.start, 2), s.title, s.title_en] for s in sections],
        "segs": [[round(s.start, 2), round(s.end, 2), s.text] for s in tl.transcript],
        "en": english,
        "terms": [{"term": t.term, "en": t.en, "reading": t.reading, "explain": t.explain,
                   "said": t.said.text, "said_en": t.said.text_en, "t": _first_time(tl, t)} for t in tl.terms],
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
        parts.append(f'<rect class="ch{" ch-b" if i % 2 else ""}" x="{x:.1f}" y="48" width="{w:.1f}" height="12"><title>{_e(c.title)}</title></rect>')
    parts.append('<line id="rib-cursor" x1="0" x2="0" y1="0" y2="64" vector-effect="non-scaling-stroke"/>')
    legend = (
        '<span><i style="background:var(--new)"></i>new visual</span>'
        '<span><i style="background:var(--repeat)"></i>seen before</span>'
        '<span><i style="background:var(--base)"></i>base shot</span>'
        + ('<span><i style="background:var(--heat)"></i>most replayed</span>' if tl.heat else "")
        + ('<span><i style="background:var(--muted);opacity:.4"></i>chapters</span>' if chapters else "")
    )
    return f"""<section aria-label="The whole video on one strip">
<svg id="rib" viewBox="0 0 1000 64" preserveAspectRatio="none" tabindex="0" role="slider" aria-label="Position in the video" aria-valuemin="0" aria-valuemax="{int(dur)}" aria-valuenow="0">{"".join(parts)}</svg>
<div class="legend">{legend}<span>drag to look · click to play from there</span></div>
</section>
<div class="readout" aria-live="polite"><div id="ro-frame" class="f"></div><div class="ro-text"><div><a id="ro-time" class="ts" href="{_e(tl.video.link(0))}">0:00</a> <strong id="ro-where"></strong></div><p id="ro-said" class="ro-said" lang="{_e(_lang_attr(tl))}"></p><p id="ro-en" class="ro-en" lang="en"></p></div></div>"""


def _toggle(tl: Timeline, lang: str) -> str:
    if lang == "orig":
        return ""
    label = LANGUAGE_LABELS.get((tl.language or "en").split("_")[0], "Original")
    buttons = [("orig", label), ("both", "Both"), ("en", "English")]
    inner = "".join(f'<button type="button" data-lang="{k}" aria-pressed="{str(k == lang).lower()}">{_e(t)}</button>'
                    for k, t in buttons)
    return f'<div class="toggle" role="group" aria-label="Language">{inner}</div>'


def _read_view(tl: Timeline) -> str:
    s = tl.summary
    if s is None:
        return ""
    tldr = "".join(_sentence(tl, x) for x in s.tldr)
    sections = "".join(_section(tl, sec) for sec in s.sections)
    return f"""<h2 class="sr" id="read-h">Summary</h2>
<p class="tldr">{tldr}</p>
{sections}
<p class="note" style="margin-top:16px">{_check_note(s.sentences(), s.checker)}</p>"""


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


def _mark(x: Sentence) -> str:
    if x.check not in MARKS:
        return ""
    cls, sign, tip = MARKS[x.check]
    tip = f"{tip}: {x.check_note}" if x.check_note else f"{tip} (Jev {x.check_p:.2f})"
    return f'<span class="mark {cls}" title="{_e(tip)}">{sign}</span>'


def _sentence(tl: Timeline, x: Sentence) -> str:
    when = ""
    if x.evidence:
        t = min(tl.transcript[i].start for i in x.evidence)
        when = f'<a class="ts" href="{_e(tl.video.link(t))}">{_clock(t)}</a>'
    text = f'<span class="t-orig">{_e(x.text)}</span>{_mark(x)}'  # the mark follows the sentence it checks
    if x.text_en:
        text += f'<span class="t-en" lang="en">{_e(x.text_en)}</span>'
    return f'<span class="sent">{when}{text}</span>'


def _check_note(sentences: list[Sentence], checker: str = "jev+code") -> str:
    if checker == "code":
        flagged = sum(1 for s in sentences if s.check == "unsupported")
        return (f"Numbers checked by code against the passages each sentence cites ({flagged} flagged ?); "
                "the meaning wasn't checked (no TypeSafe key for Jev).")
    checked = [s for s in sentences if s.check]
    if not checked:
        return "Sentences were not checked."
    ok = sum(1 for s in checked if s.check == "supported")
    return (f"{ok} of {len(checked)} sentences checked against the transcript passages they cite (✓). "
            "? means the cited passages don't say it; ✗ means they say otherwise. Hover a mark for Jev's confidence.")


def _transcript(tl: Timeline) -> str:
    """Every passage, the original over its English, technical terms glossed above the characters."""
    if not tl.transcript:
        return ""
    english = tl.translation if len(tl.translation) == len(tl.transcript) else []
    find = _term_finder(tl.terms)
    seen: dict[int, int] = {}
    chapters = sorted(tl.chapters, key=lambda c: c.start)
    rows, ci = [], 0
    lang = _e(_lang_attr(tl))
    for i, seg in enumerate(tl.transcript):
        while ci < len(chapters) and chapters[ci].start <= seg.start + 0.5:
            rows.append(f'<li class="chapter-row">{_e(chapters[ci].title)}</li>')
            ci += 1
        en = f'<p class="t-en" lang="en">{_e(english[i])}</p>' if english and english[i] else ""
        rows.append(
            f'<li class="ln" id="p{i}" data-t="{seg.start:.2f}"><a class="ts" href="{_e(tl.video.link(seg.start))}">{_clock(seg.start)}</a>'
            f'<div><p class="t-orig" lang="{lang}">{_gloss(seg.text, find, tl.terms, seen)}</p>{en}</div></li>'
        )
    follow = '<label class="follow"><input type="checkbox" id="follow" checked> Follow the video</label>' if tl.video.id else ""
    terms_hint = ' <span class="term" style="cursor:default">Underlined terms</span> open an explanation.' if tl.terms else ""
    return f"""<h2 class="sr">Transcript</h2>
<div class="tools"><label class="search" for="q"><span class="sr">Search what was said</span><input id="q" type="search" placeholder="Search what was said, in either language" autocomplete="off"></label>{follow}<span id="q-count" class="note" aria-live="polite"></span></div>
<p class="note" style="margin:0 0 8px">Machine transcript{f" ({_e(tl.transcriber)})" if tl.transcriber else ""}{", English by Mercury" if english else ""}.{terms_hint}</p>
<ol class="transcript">{"".join(rows)}</ol>"""


def _term_finder(terms: list[Term]):
    """One regex for every term as heard, longest first; spaces are optional ("L L M" = "LLM")."""
    keys = sorted({t.heard or t.term for t in terms if (t.heard or t.term)}, key=len, reverse=True)
    if not keys:
        return None
    pattern = "|".join(r"\s*".join(re.escape(c) for c in re.sub(r"\s+", "", k)) for k in keys)
    return re.compile(f"({pattern})", re.I)


def _gloss(text: str, find, terms: list[Term], seen: dict[int, int]) -> str:
    if find is None:
        return _e(text)
    index = {re.sub(r"\s+", "", (t.heard or t.term)).lower(): k for k, t in enumerate(terms)}
    out, last = [], 0
    for m in find.finditer(text):
        k = index.get(re.sub(r"\s+", "", m.group(0)).lower())
        if k is None:
            continue
        out.append(_e(text[last:m.start()]))
        t = terms[k]
        seen[k] = seen.get(k, 0) + 1
        gloss = t.en if t.en and t.en.lower() != m.group(0).strip().lower() else ""
        rt = f"<rt>{_e(gloss)}</rt>" if gloss and seen[k] <= GLOSSED_MENTIONS else ""
        out.append(f'<ruby class="term" data-k="{k}" tabindex="0" role="button" aria-label="{_e(t.term)}: {_e(t.en)}">'
                   f'{_e(m.group(0))}{rt}</ruby>')
        last = m.end()
    out.append(_e(text[last:]))
    return "".join(out)


def _terms(tl: Timeline) -> str:
    if not tl.terms:
        return ""
    cards = []
    for k, t in enumerate(tl.terms):
        first = _first_time(tl, t)
        when = f'<a class="ts" href="{_e(tl.video.link(first))}">first said {_clock(first)}</a>' if first is not None else ""
        count = f'<span class="note">said {len(t.mentions)}×</span>' if len(t.mentions) > 1 else ""
        reading = f'<span class="tc-read">{_e(t.reading)}</span>' if t.reading else ""
        en = f'<span class="tc-en">{_e(t.en)}</span>' if t.en and t.en.lower() != t.term.lower() else ""
        said = ""
        if t.said.text:
            st = min(tl.transcript[i].start for i in t.said.evidence) if t.said.evidence else None
            stamp = f'<a class="ts" href="{_e(tl.video.link(st))}">{_clock(st)}</a> ' if st is not None else ""
            en_said = f'<span class="t-en" lang="en">{_e(t.said.text_en)}</span>' if t.said.text_en else ""
            said = (f'<p class="tc-said"><span class="lbl">In this video</span> {stamp}'
                    f'<span class="t-orig">{_e(t.said.text)}</span>{_mark(t.said)}{en_said}</p>')
        explain = f'<p><span class="lbl">Background</span> {_e(t.explain)}</p>' if t.explain else ""
        cards.append(f"""<article class="term-card" id="term-{k}">
<div class="tc-head"><span class="tc-term" lang="{_e(_lang_attr(tl))}">{_e(t.term)}</span>{reading}{en}{when}{count}</div>
{explain}{said}
</article>""")
    return f"""<h2 class="sr">Terms</h2>
<p class="note" style="margin:0 0 12px">Technical terms in this video, in the order they come up. "Background" is general knowledge to help you follow; "In this video" is what the speaker says, checked against the transcript.</p>
<div class="terms">{"".join(cards)}</div>"""


def _ask(tl: Timeline) -> str:
    if not tl.transcript:
        return ""
    key = tl.video.id or _stem(tl.video.url)
    starters = "".join(f'<button type="button">{_e(q)}</button>' for q in tl.questions)
    return f"""<h2 class="sr">Ask</h2>
<form id="ask-form" class="ask" autocomplete="off"><label for="ask-q" class="sr">Your question</label><input id="ask-q" placeholder="Ask about this video, in any language"><button type="submit">Ask</button></form>
{f'<div class="chips" id="ask-starters">{starters}</div>' if starters else ""}
<p class="note" id="ask-offline" hidden>Asking needs the page served from this computer: run <code>boson-video serve --open {_e(key)}</code>. From a terminal: <code>boson-video ask {_e(key)} "your question"</code>.</p>
<p id="ask-status" class="note" aria-live="polite"></p>
<ol id="answers" class="answers"></ol>
<p class="note" style="margin-top:16px">Jev finds the moments that answer you, Mercury explains them in plain English, and Jev checks each sentence against what was said. Anything the video doesn't say is kept apart as background. Your questions are saved with the video.</p>"""


def _scenes(tl: Timeline, dense: bool) -> str:
    chapters = sorted(tl.chapters, key=lambda c: c.start)
    rows, ci = [], 0
    for s in tl.scenes:
        while ci < len(chapters) and chapters[ci].start <= s.start + 0.5:
            rows.append(f'<h2 class="chapter">{_e(chapters[ci].title)}</h2>')
            ci += 1
        rows.append(_scene_row(tl, s, dense))
    heading = "Scenes and everything said" if tl.transcript and not dense else "Scenes"
    return f"""<h2 class="sr" id="scenes-h">{heading}</h2>
<div class="scenes{" dense" if dense else ""}">
{"".join(rows)}
</div>"""


def _footer(tl: Timeline) -> str:
    t = tl.timings
    parts = [f"scenes ready in {t.get('total', 0) / 1000:.2f} s"]
    if "words total" in t:
        parts.append(f"words in {t['words total'] / 1000:.1f} s more")
    if "write" in t:
        parts.append(f"summary written in {t['write'] / 1000:.1f} s and checked in {t.get('check', 0) / 1000:.1f} s")
    source = "the video's storyboard thumbnails" + (f", its audio transcribed on this {_machine(tl)}" if tl.transcript else "")
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
    paras = "".join(
        f'<p><a href="{_e(tl.video.link(g.start))}">{_clock(g.start)}</a>{_e(g.text)}</p>' for g in segments
    )
    return f'<div class="said" lang="{_e(_lang_attr(tl))}">{paras}</div>'


def _first_time(tl: Timeline, t: Term) -> float | None:
    if t.mentions:
        return tl.transcript[t.mentions[0]].start
    if t.said.evidence:
        return tl.transcript[t.said.evidence[0]].start
    return None


def _machine(tl: Timeline) -> str:
    return "Mac" if tl.transcriber in ("", "Apple SpeechAnalyzer") else f"computer by {tl.transcriber}"


def _words_note(tl: Timeline) -> str:
    if not tl.transcript:
        return ""
    language = LANGUAGE_NAMES.get((tl.language or "").split("_")[0], tl.language)
    return f" · words: {len(tl.transcript)} passages in {language}, transcribed on this {_machine(tl)}"


def _language(tl: Timeline) -> str:
    if not tl.language:
        return ""
    return LANGUAGE_NAMES.get(tl.language.split("_")[0], tl.language)


def _lang_attr(tl: Timeline) -> str:
    return (tl.language or "").replace("_", "-")


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


def _stem(url: str) -> str:
    return re.split(r"[\\/]", url)[-1].rsplit(".", 1)[0]


def _clock(t: float) -> str:
    t = int(t)
    h, m, s = t // 3600, t // 60 % 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _duration(t: float) -> str:
    t = int(round(t))
    return f"{t // 60} min {t % 60:02d} s" if t >= 60 else f"{t} s"


def _e(s: str) -> str:
    return html.escape(s, quote=True)
