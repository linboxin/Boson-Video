"""Which writer gives the best summary? Four writers on the same videos, scored and judged blind.

    uv run python scripts/summary_bakeoff.py <video key> … [--out out/bakeoff]

For each video, every contender writes a summary from the same transcript; Jev and code check each
sentence. Scores computed here: length and sentences per minute, sentences that failed the check,
coverage (the share of 5-minute stretches, and of chapters, that the summary cites), concrete
details (numbers), and narration ("the video says…", "本期视频…"). The owner judges quality
on blind.html, where the versions are shuffled and unlabelled; key.json says which is which.
Costs real money: Mercury and Luna well under a cent a video, Sol a few cents.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from boson_video import checker, library, speech, writer
from boson_video.env import load_env

# The instructions as they were before 2026-10-09: the baseline.
SYSTEM_V1 = """You turn a video's machine-made transcript into a short read view.

Rules:
- `transcript` has one passage per line: its id, its start time, then what was said.
- Use only what the transcript says. Every sentence cites the ids of all the transcript passages it rests on (usually 1-6); never use facts from passages you don't cite.
- Be concrete: keep the numbers, prices, dates, names, tickers, decisions and reasons. "He shorted Meta at 740" beats "He talked about Meta".
- The transcript was made by speech recognition, so names and English words inside other languages are often misheard (for example "Monelife" for "Money or Life"). When a word clearly sounds like an entry in `names`, write it the way `names` spells it. Never invent a name.
- `on_screen`, when given, is text shown in the video, read by OCR. The screen spells names right where speech recognition mishears them (a slide says 英矽智能 where the transcript heard 因系智能): when a transcript word sounds like an on-screen word, spell it the on-screen way. Use `on_screen` only for spelling, never as a source of facts.
- `text` and `title` are in {language}. {english_rule}
- `tldr`: 2-3 sentences saying what the video is and its main conclusion.
- `sections`: in time order. If `chapters` are given, make one section per chapter, titled like the chapter. Otherwise split by topic into about one section per 4-8 minutes (at least 2). Each section has 2-4 sentences. `start_id` is the id of the section's first transcript passage.
"""

CONTENDERS = [  # (label, model, effort, instructions)
    ("mercury-today", "mercury-2.5", "low", SYSTEM_V1),
    ("mercury-new", "mercury-2.5", "high", None),
    ("luna-new", "gpt-6-luna", "medium", None),
    ("sol-new", "gpt-6.1-sol", "medium", None),
]
NARRATION = re.compile(r"视频|本期|这期|作者|博主|主播|[Uu][Pp]主|\b(the|this) video\b|\bthe (author|creator|host)\b|\bin this (episode|talk)\b", re.I)
LABEL_TITLE = re.compile(r"^(开场|引子|引言|简介|介绍|结尾|总结|结语|封面.*|intro(duction)?|outro|conclusion|summary|part \d+)$", re.I)
NUMBER = re.compile(r"\d|[零一二三四五六七八九十百千万亿两]+(?:个|年|月|天|倍|次|分钟|小时|美元|元|%|成)")


def write_one(tl, names, label, model, effort, instructions):
    tl = copy.deepcopy(tl)
    started = time.perf_counter()
    tl.summary, stats = writer.write(tl, names, effort, model=model, instructions=instructions)
    stats["seconds"] = round(time.perf_counter() - started, 1)
    checker.check(tl)
    return label, tl, stats


def scores(tl, stats) -> dict:
    s = tl.summary
    every = s.sentences()
    minutes = tl.video.duration / 60
    cited = [tl.transcript[i].start for x in every for i in x.evidence]
    bins = max(1, round(minutes / 5))
    covered = len({min(bins - 1, int(t / 60 / 5)) for t in cited})
    chapters = sorted(tl.chapters, key=lambda c: c.start)
    hit = sum(1 for i, c in enumerate(chapters)
              if any(c.start <= t < (chapters[i + 1].start if i + 1 < len(chapters) else tl.video.duration) for t in cited))
    checked = [x for x in every if x.check]
    return {
        "sentences": len(every),
        "per_minute": round(len(every) / minutes, 2),
        "sections": len(s.sections),
        "failed_check": sum(1 for x in checked if x.check != "supported"),
        "checked": len(checked),
        "coverage_5min": round(covered / bins, 2),
        "chapters_covered": f"{hit}/{len(chapters)}" if chapters else "-",
        "with_numbers": sum(1 for x in every if NUMBER.search(x.text)),
        "narration": sum(1 for x in every if NARRATION.search(x.text)),
        "label_titles": sum(1 for sec in s.sections if LABEL_TITLE.match(sec.title.strip())),
        "seconds": stats.get("seconds"),
        "cost_usd": stats.get("cost_usd"),
    }


def section_html(tl) -> str:
    s, out = tl.summary, []
    def line(x):
        mark = "" if x.check == "supported" else ' <span class="flag" title="failed the check">?</span>'
        en = f'<div class="en">{html.escape(x.text_en)}</div>' if x.text_en else ""
        return f"<li>{html.escape(x.text)}{mark}{en}</li>"
    out.append('<div class="tldr"><ul>' + "".join(line(x) for x in s.tldr) + "</ul></div>")
    for sec in s.sections:
        en = f' <span class="en">{html.escape(sec.title_en)}</span>' if sec.title_en else ""
        out.append(f"<h4>{html.escape(sec.title)}{en}</h4><ul>" + "".join(line(x) for x in sec.sentences) + "</ul>")
    return "".join(out)


def blind_page(rows: list[dict]) -> str:
    cards = []
    for r in rows:
        versions = "".join(
            f'<section class="v"><h3>Version {letter}</h3>{body}</section>' for letter, body in r["versions"])
        picks = "".join(f'<label><input type="radio" name="{r["key"]}" value="{letter}"> {letter}</label>'
                        for letter, _ in r["versions"])
        cards.append(f'''<article><h2>{html.escape(r["title"])}</h2><p class="meta">{r["minutes"]} min · {html.escape(r["language"])}
· <a href="https://www.youtube.com/watch?v={r["key"]}" target="_blank">watch</a></p>
<div class="grid">{versions}</div><p class="pick">Best version: {picks}</p></article>''')
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>Summary bake-off (blind)</title><style>
:root{{color-scheme:light dark}} body{{font:15px/1.6 -apple-system,"PingFang SC",sans-serif;margin:0;padding:24px;background:#f6f5f2;color:#1c1c1f}}
@media (prefers-color-scheme:dark){{body{{background:#121214;color:#ececef}} .v{{background:#19191c!important;border-color:#2a2a2f!important}} .en{{color:#9c9ca5!important}}}}
article{{margin:0 0 48px}} h2{{margin:0}} .meta{{color:#6b6b73;margin:4px 0 12px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px}}
.v{{background:#fff;border:1px solid #e7e5e0;border-radius:12px;padding:12px 16px;max-height:80vh;overflow:auto}}
.v h3{{margin:0 0 8px;font-size:15px}} .tldr{{font-weight:500}} h4{{margin:14px 0 4px;font-size:14px}} ul{{margin:0;padding-left:18px}}
li{{margin:0 0 6px}} .en{{color:#6b6b73;font-size:13px}} .flag{{color:#b26a00;font-weight:700}}
.pick{{font-size:16px}} .pick label{{margin-right:14px}} button{{font:inherit;padding:8px 16px;border-radius:999px;border:0;background:#1c1c1f;color:#fff;cursor:pointer}}
</style></head><body><h1>Which summary is best?</h1><p>Each video has four versions from different writers, shuffled. Pick the one you'd rather read.
<b>?</b> marks a sentence that failed the check. Then copy your picks and paste them to Claude.</p>
{"".join(cards)}<p><button onclick="const p=[...document.querySelectorAll('article')].map(a=>{{const c=a.querySelector('input:checked');return a.querySelector('input').name+': '+(c?c.value:'-')}}).join('\\n');navigator.clipboard.writeText(p);this.textContent='Copied'">Copy my picks</button></p>
</body></html>'''


def main(keys: list[str], out: Path) -> None:
    load_env()
    out.mkdir(parents=True, exist_ok=True)
    results, rows, key_map = {}, [], {}
    for key in keys:
        tl = library.load(key)
        names = speech.names(tl.video.title, tl.video.channel, tl.video.description) + speech.title_terms(tl.video.title)
        print(f"\n{key} · {tl.video.title[:50]} · {round(tl.video.duration / 60)} min", flush=True)
        with ThreadPoolExecutor(len(CONTENDERS)) as pool:
            done = list(pool.map(lambda c: _safe(tl, names, *c), CONTENDERS))
        results[key] = {}
        versions = []
        for label, written, stats in done:
            if written is None:
                print(f"  {label:14s} FAILED: {stats}")
                results[key][label] = {"error": stats}
                continue
            sc = scores(written, stats)
            results[key][label] = sc
            (out / f"{key}.{label}.json").write_text(json.dumps(written.to_json()["summary"], ensure_ascii=False, indent=1))
            print(f"  {label:14s} {sc['sentences']:3d} sentences ({sc['per_minute']}/min) · failed check {sc['failed_check']}/{sc['checked']} · "
                  f"coverage {sc['coverage_5min']} · chapters {sc['chapters_covered']} · numbers {sc['with_numbers']} · "
                  f"narration {sc['narration']} · label titles {sc['label_titles']} · {sc['seconds']} s · ${sc['cost_usd']}", flush=True)
            versions.append((label, section_html(written)))
        random.shuffle(versions)
        letters = "ABCD"
        key_map[key] = {letters[i]: label for i, (label, _) in enumerate(versions)}
        rows.append({"key": key, "title": tl.video.title, "minutes": round(tl.video.duration / 60),
                     "language": writer.language_name(tl.language),
                     "versions": [(letters[i], body) for i, (_, body) in enumerate(versions)]})
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    (out / "key.json").write_text(json.dumps(key_map, indent=1))
    (out / "blind.html").write_text(blind_page(rows), encoding="utf-8")
    print(f"\nblind page: {out / 'blind.html'}  (answer key: {out / 'key.json'})")


def _safe(tl, names, label, model, effort, instructions):
    try:
        return write_one(tl, names, label, model, effort, instructions)
    except Exception as e:  # one writer failing shouldn't stop the others
        return label, None, f"{type(e).__name__}: {str(e)[:200]}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="+")
    ap.add_argument("--out", default="out/bakeoff")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    main(a.keys, Path(a.out))
