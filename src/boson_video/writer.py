"""The read view's words: a writing model turns the transcript into the summary and its sections.

Every sentence cites the transcript passages it rests on, so the page can link it to its second
and Jev can check it. Text is written in the video's language, with an English version for the
toggle. The model is whatever llm.py points at (Mercury by default); the harness here is what
makes a cheap model write well, and lets a better one write better:

- A short video is written in one call.
- A longer one (15 minutes and up) is written part by part: its chapters, or the parts an outline
  call finds where the topic changes. Each part is written in parallel from only its own passages,
  with a sentence budget and the passages that hold numbers; the tldr is then written from the
  finished sections. A small, focused input is where a fast model does its best work.
- After the check, `repair` gives every sentence that failed it, or narrates the video, one rewrite
  against its passages (an empty rewrite drops it), and retitles sections titled with a label.

Why (2026-10-09): the owner found the summaries weak. They narrated the video ("视频介绍了…")
instead of stating its points, capped every section at 4 sentences (15 sentences for 28 minutes),
and listed facts without their reasons; rewriting the instructions fixed the style, but on the
hour-long talk one call to Mercury lost depth and 8 of 46 sentences failed the check.
"""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import llm
from .timeline import Section, Sentence, Summary, Timeline

LANGUAGES = {
    "zh_CN": "Simplified Chinese",
    "zh_TW": "Traditional Chinese",
    "zh_HK": "Traditional Chinese",
    "yue_CN": "Cantonese, in Traditional Chinese characters",
}
PARTS_FROM_MINUTES = 15  # videos at least this long are written part by part
PARALLEL_PARTS = 4  # more at once ran into Mercury's rate limit (2026-10-09, eight parts of an hour-long talk)
NARRATION = re.compile(r"视频|本期|这期|作者|博主|主播|[Uu][Pp]主|\b(the|this) video\b|\bthe (author|creator|host)\b|\bin this (episode|talk)\b", re.I)
LABEL_TITLE = re.compile(r"^(开场|开头|引子|引言|简介|介绍|结尾|总结|结语|封面.*|intro(duction)?|outro|conclusion|summary|part \d+|section \d+)$", re.I)

READER = """You write the read view of a video for someone who wants its substance without watching it: often a learner following a long talk in a language they only half know. They read your summary first and open the video only for what they need to see."""

RULES = """How to write each sentence:
- State the content itself. Never narrate the video or its maker: no "the video introduces", "the author previously made", "本期视频", "视频介绍了", "作者", "博主". Write "Drug discovery traditionally takes 3-5 years", not "The video says drug discovery takes 3-5 years".
- Attribute opinions, advice and predictions to the speaker ("he expects", "她建议", "the speaker warns"); state facts and explanations plainly.
- Keep what makes it useful: numbers with their units, names, tickers, dates, examples, comparisons, and the reasons and caveats the speaker gives. One concrete fact beats a general statement.
- Connect, don't just list: when the speaker gives a reason or a consequence, say how it follows.
- Use only what the transcript says. Every sentence cites the ids of all the passages it rests on (usually 1-6). Never use facts from passages you don't cite or from outside the video. `on_screen` is for spelling names and terms only.
- Speech recognition mishears: when a word clearly sounds like an entry in `names` or `on_screen`, or the context makes the intended word certain (工单 for 公单), write the intended word. Never invent a name or a number.
- `text` and `title` are in {language}. {english_rule}"""

SYSTEM = READER + """

The input:
- `transcript`: one passage per line: its id, its start time, then what was said. It is machine-made, so words are sometimes misheard.
- `chapters` (when the video has them), `names` (how the video spells its own names), `on_screen` (text shown in the video, read by OCR), `minutes` (its length) and `target_sentences` (about how many sentences the whole summary should have).

What to write:
- `tldr`: 2-4 sentences. The main point or conclusion first; then the one or two things that support it; then what it means for the viewer (a decision, a warning, a recommendation) when the video says so.
- `sections`: the substance in order. When `chapters` are given, follow them, but fold a chapter with little content into its neighbour and leave out the intro, the outro and self-promotion. Without chapters, start a new section where the topic changes, about every 3-6 minutes. Title each section with its point ("AI shortens the discovery stage to 18 months, not the trials"), never with a label ("Introduction", "Part 2", "开场"). Give each section 2-8 sentences, as many as its content deserves. `start_id` is the id of its first passage.
- About `target_sentences` sentences in all: more for dense stretches, fewer for chatter.

""" + RULES + "\n"

PART_SYSTEM = READER + """

You write one section of that summary: the part of the video in `transcript` (one passage per line: its id, its start time, what was said; machine-made, so words are sometimes misheard). `video` is the whole video's title, `chapter` the chapter this part belongs to (if any), `before` and `after` what the neighbouring parts are about, so you don't repeat them.

What to write:
- `title`: the point of this part, stated ("Next-word prediction compresses the internet into the weights"), never a label ("Introduction", "Part 2", "开场").
- `sentences`: about `target_sentences` of them, in the order the points come. Use the passages listed in `with_numbers`: those numbers are usually what makes the part useful. If the part is only an intro, an outro or self-promotion, return no sentences.

""" + RULES + "\n"

TLDR_SYSTEM = READER + """

The sections of the summary are written (`sections`: each sentence with the passage ids it cites). Write the `tldr` that opens it: 2-4 sentences. The main point or conclusion first; then the one or two things that support it; then what it means for the viewer (a decision, a warning, a recommendation) when the video says so. Each sentence cites the passage ids its claims rest on, taken from the sentences it draws on. State the content directly; never narrate the video ("本期视频", "the video introduces"). Attribute opinions and predictions to the speaker. `text` is in {language}. {english_rule}
"""

OUTLINE_SYSTEM = """Split a video's transcript (one passage per line: its id, its start time, what was said) into the sections a reader would want: start a new one where the topic changes, about every 3-6 minutes, and keep the intro, the outro and self-promotion short. Return each section's first passage id, in order, starting with 0, and a few words saying what it covers."""

REPAIR_SYSTEM = READER + """

Some sentences of the summary need another try (`items`): each comes with the passages it should rest on (`passages`: id, start time, what was said) and its `problem`. Rewrite each so it says only what those passages say, stated directly, keeping the numbers, names and reasons the passages give. Never narrate the video ("本期视频", "the video says", "作者"). Cite the ids of the passages it rests on, from those given. If the passages don't support any version of the sentence, return an empty `text`.

Some section titles are labels (`titles`: the title and the section's first sentences): give each a title that states the section's point.

`text` and `title` are in {language}. {english_rule}
"""

SENTENCE = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "text_en": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["text", "text_en", "evidence"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {
        "tldr": {"type": "array", "items": SENTENCE},
        "sections": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "title_en": {"type": "string"},
                "start_id": {"type": "integer"},
                "sentences": {"type": "array", "items": SENTENCE},
            },
            "required": ["title", "title_en", "start_id", "sentences"],
            "additionalProperties": False,
        }},
    },
    "required": ["tldr", "sections"],
    "additionalProperties": False,
}


PART_SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}, "title_en": {"type": "string"},
                   "sentences": {"type": "array", "items": SENTENCE}},
    "required": ["title", "title_en", "sentences"],
    "additionalProperties": False,
}
TLDR_SCHEMA = {
    "type": "object", "properties": {"tldr": {"type": "array", "items": SENTENCE}},
    "required": ["tldr"], "additionalProperties": False,
}
OUTLINE_SCHEMA = {
    "type": "object",
    "properties": {"sections": {"type": "array", "items": {
        "type": "object", "properties": {"start_id": {"type": "integer"}, "covers": {"type": "string"}},
        "required": ["start_id", "covers"], "additionalProperties": False}}},
    "required": ["sections"], "additionalProperties": False,
}
REPAIR_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "integer"}, "text": {"type": "string"}, "text_en": {"type": "string"},
                           "evidence": {"type": "array", "items": {"type": "integer"}}},
            "required": ["id", "text", "text_en", "evidence"], "additionalProperties": False}},
        "titles": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "integer"}, "title": {"type": "string"}, "title_en": {"type": "string"}},
            "required": ["id", "title", "title_en"], "additionalProperties": False}},
    },
    "required": ["items", "titles"], "additionalProperties": False,
}


class WriterError(RuntimeError):
    pass


last_bad_reply: dict = {}  # the most recent unusable reply, for diagnosis


def language_name(locale: str | None) -> str:
    return LANGUAGES.get(locale or "", "English")


def target_sentences(minutes: float) -> int:
    """About how long the whole summary should be: 14 sentences for 11 minutes, 27 for 28, 48 for an hour."""
    return max(10, min(48, round(6 + 0.75 * minutes)))


def _lines(tl: Timeline, ids) -> str:
    """Passages as compact lines, "<id> <time> <text>": far fewer tokens than an object each."""
    return "\n".join(f"{i} {_clock(tl.transcript[i].start)} {tl.transcript[i].text}" for i in ids)


def payload(tl: Timeline, names: list[str]) -> dict:
    minutes = tl.video.duration / 60
    out = {
        "title": tl.video.title,
        "channel": tl.video.channel,
        "duration": _clock(tl.video.duration),
        "minutes": round(minutes),
        "target_sentences": target_sentences(minutes),
        "names": names,
        "chapters": [{"title": c.title, "start": _clock(c.start)} for c in tl.chapters],
        "transcript": _lines(tl, range(len(tl.transcript))),
    }
    if lines := tl.screen_lines():
        out["on_screen"] = lines
    return out


def _slots(tl: Timeline) -> dict:
    language = language_name(tl.language)
    rule = ("The video is in English: leave `text_en` and `title_en` empty." if language == "English" else
            f"The video is in {language}, so `text_en` and `title_en` are required: the English version of every `text` and `title`.")
    return {"language": language, "english_rule": rule}


def system(tl: Timeline, instructions: str | None = None) -> str:
    return (instructions or SYSTEM).format(**_slots(tl))


def request_body(tl: Timeline, names: list[str], effort: str | None = "high", instructions: str | None = None) -> dict:
    return llm.body(system(tl, instructions), payload(tl, names), SCHEMA, "read_view", effort)


def _effort(effort: str | None) -> str:
    # what the 2026-10-09 bake-off measured for Mercury
    return effort or os.environ.get("BOSON_WRITER_EFFORT") or "high"


def write(tl: Timeline, names: list[str], effort: str | None = None, transport=None, attempt: int = 1,
          instructions: str | None = None, parts: bool | None = None) -> tuple[Summary, dict]:
    """The summary and the calls' stats (seconds, tokens, cost, attempts). Written part by part for a
    video of 15 minutes or more (`parts` forces it either way); `instructions` replaces SYSTEM for a
    one-call write (with its {language} and {english_rule} slots), for comparing versions."""
    if not tl.transcript:
        raise WriterError("no transcript to summarize")
    effort = _effort(effort)
    if parts is None:
        parts = instructions is None and tl.video.duration / 60 >= PARTS_FROM_MINUTES
    if parts:
        try:
            return write_in_parts(tl, names, effort, transport)
        except WriterError:
            pass  # a whole-video write is the fallback
    return _write_whole(tl, names, effort, transport, attempt, instructions)


def _write_whole(tl, names, effort, transport, attempt=1, instructions=None) -> tuple[Summary, dict]:
    started = time.perf_counter()
    try:
        res = llm.post(request_body(tl, names, effort, instructions), transport)
    except llm.LLMError as e:
        raise WriterError(str(e)) from None
    out = _read_output(res)
    summary = to_summary(out, tl) if out is not None else None
    if summary is None or not summary.sentences():
        last_bad_reply.update(res)  # kept for diagnosis
        if attempt == 1:  # the schema is usually honoured; one more try when it isn't
            summary, stats = _write_whole(tl, names, effort, transport, 2, instructions)
            stats["seconds"] = round(time.perf_counter() - started, 2)
            return summary, stats
        raise WriterError(f"{llm.model_name()} returned no usable summary twice")
    return summary, llm.stats(res, started, attempt)


# ---- part by part ---------------------------------------------------------------------------------


def plan_parts(tl: Timeline, effort: str, transport=None) -> tuple[list[tuple[int, int, str]], dict]:
    """[(first passage id, last + 1, chapter title or "")]: the chapters (a chapter under a minute or
    two passages joins the one before), or the parts an outline call finds; evenly by time if it fails."""
    n, starts = len(tl.transcript), [s.start for s in tl.transcript]
    cuts: list[tuple[int, str]] = []
    stats: dict = {"cost_usd": 0.0}
    if len(tl.chapters) >= 2:
        for c in sorted(tl.chapters, key=lambda c: c.start):
            first = next((i for i, t in enumerate(starts) if t >= c.start - 1), n)
            if first < n and (not cuts or first > cuts[-1][0]):
                cuts.append((first, c.title))
        if cuts:
            cuts[0] = (0, cuts[0][1])
    else:
        try:
            out, stats = llm.ask_json(OUTLINE_SYSTEM, {"transcript": _lines(tl, range(n))}, OUTLINE_SCHEMA, "outline",
                                      usable=lambda o: len(o.get("sections", [])) >= 2, effort="low", transport=transport)
            ids = sorted({int(x["start_id"]) for x in out["sections"] if 0 <= int(x["start_id"]) < n} | {0})
            cuts = [(i, "") for i in ids]
        except (llm.LLMError, KeyError, TypeError, ValueError):
            step = max(1, round(n / max(2, round(tl.video.duration / 300))))
            cuts = [(i, "") for i in range(0, n, step)]
    raw = [(first, cuts[k + 1][0] if k + 1 < len(cuts) else n, title) for k, (first, title) in enumerate(cuts)]

    def short(part) -> bool:
        first, last, _ = part
        end = tl.transcript[last].start if last < n else tl.video.duration
        return last - first < 2 or end - starts[first] < 60

    parts: list[tuple[int, int, str]] = []
    for part in raw:
        if parts and short(part):  # its passages stay with the part before
            parts[-1] = (parts[-1][0], part[1], parts[-1][2])
        elif len(parts) == 1 and short(parts[0]):  # a short opening joins the next part, and takes its title
            parts[0] = (parts[0][0], part[1], part[2])
        else:
            parts.append(part)
    return parts, stats


def write_in_parts(tl: Timeline, names: list[str], effort: str, transport=None) -> tuple[Summary, dict]:
    started = time.perf_counter()
    parts, plan_stats = plan_parts(tl, effort, transport)
    if len(parts) < 2:
        raise WriterError("the video didn't split into parts")
    total = target_sentences(tl.video.duration / 60)
    ends = [tl.transcript[last].start if last < len(tl.transcript) else tl.video.duration for _, last, _ in parts]
    screen, slots = tl.screen_lines(), _slots(tl)

    def one(k: int):
        first, last, chapter = parts[k]
        share = (ends[k] - tl.transcript[first].start) / max(tl.video.duration, 1)
        body = {
            "video": tl.video.title, "chapter": chapter, "names": names,
            "before": parts[k - 1][2] if k else "", "after": parts[k + 1][2] if k + 1 < len(parts) else "",
            "target_sentences": max(2, min(10, round(total * share))),
            "with_numbers": [i for i in range(first, last) if re.search(r"\d|[零一二三四五六七八九十百千万亿两]", tl.transcript[i].text)],
            "transcript": _lines(tl, range(first, last)),
        }
        if screen:
            body["on_screen"] = screen
        out, st = llm.ask_json(PART_SYSTEM.format(**slots), body, PART_SCHEMA, "section",
                               usable=lambda o: isinstance(o.get("sentences"), list), effort=effort, transport=transport)
        return {"title": out.get("title", ""), "title_en": out.get("title_en", ""), "start_id": first,
                "sentences": [x for x in out["sentences"] if isinstance(x, dict)]}, st

    calls, written = [plan_stats], []
    with ThreadPoolExecutor(min(PARALLEL_PARTS, len(parts))) as pool:
        for k, result in enumerate(pool.map(lambda k: _try(one, k), range(len(parts)))):
            if result is not None:
                written.append(result[0])
                calls.append(result[1])
    if len([w for w in written if w["sentences"]]) < max(1, len(parts) // 2):
        raise WriterError("too many parts failed to write")
    sections_in = [{"title": w["title"], "sentences": [{"text": x.get("text", ""), "evidence": x.get("evidence", [])}
                                                        for x in w["sentences"]]} for w in written if w["sentences"]]
    try:
        top, st = llm.ask_json(TLDR_SYSTEM.format(**slots), {"video": tl.video.title, "sections": sections_in}, TLDR_SCHEMA,
                               "tldr", usable=lambda o: bool(o.get("tldr")), effort=effort, transport=transport)
        calls.append(st)
        tldr = top["tldr"]
    except llm.LLMError:
        tldr = []
    summary = to_summary({"tldr": tldr, "sections": written}, tl)
    if not summary.sentences():
        raise WriterError("the parts came back empty")
    return summary, _total(calls, started, len(parts))


def _try(fn, k):
    try:
        return fn(k)
    except llm.LLMError:
        return None


def _total(calls: list[dict], started: float, parts: int = 0) -> dict:
    out = {"seconds": round(time.perf_counter() - started, 2), "attempts": sum(c.get("attempts", 0) for c in calls),
           "input_tokens": sum(c.get("input_tokens", 0) for c in calls),
           "output_tokens": sum(c.get("output_tokens", 0) for c in calls),
           "cost_usd": round(sum(c.get("cost_usd", 0) for c in calls), 5)}
    if parts:
        out["parts"] = parts
    return out


# ---- repair ---------------------------------------------------------------------------------------


def repair(tl: Timeline, effort: str | None = None, transport=None, check=None) -> dict:
    """One more try for what the check and the style gate caught: sentences that failed the check or
    narrate the video are rewritten against their passages (an empty rewrite drops the sentence) and
    checked again; label titles are retitled. `check(tl, sentences)` re-checks (checker.check_sentences)."""
    s = tl.summary
    if s is None:
        return {}
    started = time.perf_counter()
    n = len(tl.transcript)
    every = s.sentences()
    bad = [x for x in every if x.check in ("unsupported", "contradicted") or NARRATION.search(x.text)]
    labels = [k for k, sec in enumerate(s.sections) if LABEL_TITLE.match(sec.title.strip())]
    if not bad and not labels:
        return {"repair_candidates": 0}
    items = []
    for k, x in enumerate(bad):
        near = sorted({j for i in x.evidence for j in (i - 1, i, i + 1) if 0 <= j < n}) or list(range(min(n, 3)))
        problem = ("narrates the video instead of stating the point" if NARRATION.search(x.text) and x.check == "supported"
                   else f"the passages don't support it{': ' + x.check_note if x.check_note else ''}")
        items.append({"id": k, "text": x.text, "problem": problem, "passages": _lines(tl, near)})
    titles = [{"id": k, "title": s.sections[k].title, "first_sentences": [x.text for x in s.sections[k].sentences[:2]]}
              for k in labels]
    try:
        out, st = llm.ask_json(REPAIR_SYSTEM.format(**_slots(tl)), {"video": tl.video.title, "items": items, "titles": titles},
                               REPAIR_SCHEMA, "repair", usable=lambda o: isinstance(o.get("items"), list),
                               effort=_effort(effort), transport=transport)
    except llm.LLMError as e:
        return {"repair_candidates": len(bad), "error": str(e)}
    fixed, dropped = [], []
    for item in out.get("items", []):
        k = item.get("id")
        if not isinstance(k, int) or not 0 <= k < len(bad):
            continue
        x, text = bad[k], (item.get("text") or "").strip()
        if not text:
            dropped.append(x)
            continue
        allowed = {j for i in x.evidence for j in (i - 1, i, i + 1) if 0 <= j < n} or set(range(n))
        x.text = text
        x.text_en = "" if (item.get("text_en") or "").strip() == text else (item.get("text_en") or "").strip()
        x.evidence = sorted({e for e in item.get("evidence", []) if isinstance(e, int) and e in allowed}) or x.evidence
        x.check, x.check_p, x.check_note = "", 0.0, ""
        fixed.append(x)
    for t in out.get("titles", []):
        k = t.get("id")
        if isinstance(k, int) and k in labels and (t.get("title") or "").strip():
            s.sections[k].title = t["title"].strip()
            s.sections[k].title_en = (t.get("title_en") or "").strip()
    if dropped:
        gone = {id(x) for x in dropped}
        s.tldr = [x for x in s.tldr if id(x) not in gone]
        for sec in s.sections:
            sec.sentences = [x for x in sec.sentences if id(x) not in gone]
        s.sections = [sec for sec in s.sections if sec.sentences]
    if fixed and check:
        check(tl, fixed)
    return {"repair_candidates": len(bad), "rewritten": len(fixed), "dropped": len(dropped),
            "still_failing": sum(1 for x in fixed if x.check and x.check != "supported"),
            "retitled": len(labels), "seconds": round(time.perf_counter() - started, 2), "cost_usd": st.get("cost_usd", 0)}


def _read_output(res: dict) -> dict | None:
    """The JSON object the schema asks for. Mercury has wrapped it in a list, and has returned the
    bare list of sections (no tldr, 2026-10-04, a 35-minute video, twice in a row)."""
    try:
        out = json.loads(res["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None
    if isinstance(out, list):
        whole = next((x for x in out if isinstance(x, dict) and ("sections" in x or "tldr" in x)), None)
        sections = [x for x in out if isinstance(x, dict) and "sentences" in x]
        out = whole or ({"tldr": [], "sections": sections} if sections else None)
    return out if isinstance(out, dict) and isinstance(out.get("sections"), list) else None


def to_summary(out: dict, tl: Timeline, writer: str | None = None) -> Summary:
    """Model output -> Summary: valid evidence only, sections ordered and given times."""
    n = len(tl.transcript)

    def sentences(items: list[dict]) -> list[Sentence]:
        result = []
        for it in items:
            text = (it.get("text") or "").strip()
            if not text:
                continue
            evidence = sorted({e for e in it.get("evidence", []) if isinstance(e, int) and 0 <= e < n})
            english = (it.get("text_en") or "").strip()
            result.append(Sentence(text, "" if english == text else english, evidence))
        return result

    raw = sorted(out.get("sections", []), key=lambda s: max(0, min(n - 1, int(s.get("start_id", 0)))))
    starts = [tl.transcript[max(0, min(n - 1, int(s.get("start_id", 0))))].start for s in raw]
    sections = []
    for i, s in enumerate(raw):
        end = starts[i + 1] if i + 1 < len(raw) else tl.video.duration
        body = sentences(s.get("sentences", []))
        body.sort(key=lambda x: tl.transcript[x.evidence[0]].start if x.evidence else starts[i])  # read in video order
        if body:
            title, title_en = s.get("title", "").strip(), s.get("title_en", "").strip()
            sections.append(Section(title, "" if title_en == title else title_en, starts[i], end, body))
    return Summary(tldr=sentences(out.get("tldr", [])), sections=sections, writer=writer or llm.model_name())


def _clock(t: float) -> str:
    t = int(t)
    h, m, s = t // 3600, t // 60 % 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
