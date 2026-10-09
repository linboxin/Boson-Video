"""The read view's words: a writing model turns the transcript into the summary and its sections.

Every sentence cites the transcript passages it rests on, so the page can link it to its second
and Jev can check it. Text is written in the video's language, with an English version for the
toggle. Mercury writes by default; `BOSON_WRITER=gpt-6-luna` (or another OpenAI model) swaps it,
and `BOSON_WRITER_EFFORT` sets how hard it thinks.

The instructions were rewritten on 2026-10-09 after the owner found the summaries weak: they
narrated the video ("the video introduces…") instead of stating its points, capped every section
at 4 sentences whatever the length (15 sentences for 28 minutes), and listed facts without the
reasons that connect them.
"""

from __future__ import annotations

import json
import os
import time

from . import mercury, openai_api
from .mercury import MODEL
from .timeline import Section, Sentence, Summary, Timeline

LANGUAGES = {
    "zh_CN": "Simplified Chinese",
    "zh_TW": "Traditional Chinese",
    "zh_HK": "Traditional Chinese",
    "yue_CN": "Cantonese, in Traditional Chinese characters",
}

SYSTEM = """You write the read view of a video for someone who wants its substance without watching it: often a learner following a long talk in a language they only half know. They read your summary first and open the video only for what they need to see.

The input:
- `transcript`: one passage per line: its id, its start time, then what was said. It is machine-made, so words are sometimes misheard.
- `chapters` (when the video has them), `names` (how the video spells its own names), `on_screen` (text shown in the video, read by OCR), `minutes` (its length) and `target_sentences` (about how many sentences the whole summary should have).

What to write:
- `tldr`: 2-4 sentences. The main point or conclusion first; then the one or two things that support it; then what it means for the viewer (a decision, a warning, a recommendation) when the video says so.
- `sections`: the substance in order. When `chapters` are given, follow them, but fold a chapter with little content into its neighbour and leave out the intro, the outro and self-promotion. Without chapters, start a new section where the topic changes, about every 3-6 minutes. Title each section with its point ("AI shortens the discovery stage to 18 months, not the trials"), never with a label ("Introduction", "Part 2", "开场"). Give each section 2-8 sentences, as many as its content deserves. `start_id` is the id of its first passage.
- About `target_sentences` sentences in all: more for dense stretches, fewer for chatter.

How to write each sentence:
- State the content itself. Never narrate the video or its maker: no "the video introduces", "the author previously made", "本期视频", "视频介绍了", "作者", "博主". Write "Drug discovery traditionally takes 3-5 years", not "The video says drug discovery takes 3-5 years".
- Attribute opinions, advice and predictions to the speaker ("he expects", "她建议", "the speaker warns"); state facts and explanations plainly.
- Keep what makes it useful: numbers with their units, names, tickers, dates, examples, comparisons, and the reasons and caveats the speaker gives. One concrete fact beats a general statement.
- Connect, don't just list: when the speaker gives a reason or a consequence, say how it follows.
- Use only what the transcript says. Every sentence cites the ids of all the passages it rests on (usually 1-6). Never use facts from passages you don't cite or from outside the video. `on_screen` is for spelling names and terms only.
- Speech recognition mishears: when a word clearly sounds like an entry in `names` or `on_screen`, or the context makes the intended word certain (工单 for 公单), write the intended word. Never invent a name or a number.
- `text` and `title` are in {language}. {english_rule}
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


class WriterError(RuntimeError):
    pass


last_bad_reply: dict = {}  # the most recent unusable reply, for diagnosis


def language_name(locale: str | None) -> str:
    return LANGUAGES.get(locale or "", "English")


def target_sentences(minutes: float) -> int:
    """About how long the whole summary should be: 14 sentences for 11 minutes, 27 for 28, 48 for an hour."""
    return max(10, min(48, round(6 + 0.75 * minutes)))


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
        # one line per passage, "<id> <time> <text>": far fewer tokens than an object per passage
        "transcript": "\n".join(f"{i} {_clock(s.start)} {s.text}" for i, s in enumerate(tl.transcript)),
    }
    if lines := tl.screen_lines():
        out["on_screen"] = lines
    return out


def system(tl: Timeline, instructions: str | None = None) -> str:
    language = language_name(tl.language)
    rule = ("The video is in English: leave `text_en` and `title_en` empty." if language == "English" else
            f"The video is in {language}, so `text_en` and `title_en` are required: the English version of every `text` and `title`.")
    return (instructions or SYSTEM).format(language=language, english_rule=rule)


def request_body(tl: Timeline, names: list[str], effort: str = "low", instructions: str | None = None) -> dict:
    return mercury.body(system(tl, instructions), payload(tl, names), SCHEMA, "read_view", effort)


def write(tl: Timeline, names: list[str], effort: str | None = None, transport=None, attempt: int = 1,
          model: str | None = None, instructions: str | None = None) -> tuple[Summary, dict]:
    """Returns the summary and the call's stats (seconds, tokens, cost, attempts). `instructions`
    replaces SYSTEM (with its {language} and {english_rule} slots), for comparing versions."""
    if not tl.transcript:
        raise WriterError("no transcript to summarize")
    model = model or os.environ.get("BOSON_WRITER") or MODEL
    # the settings the 2026-10-09 bake-off measured: Mercury at high, OpenAI's models at medium
    effort = effort or os.environ.get("BOSON_WRITER_EFFORT") or ("medium" if model.startswith("gpt-") else "high")
    if model.startswith("gpt-"):
        return _write_openai(tl, names, model, effort, transport, instructions)
    started = time.perf_counter()
    try:
        res = mercury.post(request_body(tl, names, effort, instructions), transport)
    except mercury.MercuryError as e:
        raise WriterError(str(e)) from None
    out = _read_output(res)
    summary = to_summary(out, tl) if out is not None else None
    if summary is None or not summary.sentences():
        last_bad_reply.update(res)  # kept for diagnosis
        if attempt == 1:  # the schema is usually honoured; one more try when it isn't
            summary, stats = write(tl, names, effort, transport, attempt=2, model=model, instructions=instructions)
            stats["seconds"] = round(time.perf_counter() - started, 2)
            return summary, stats
        raise WriterError("Mercury returned no usable summary twice")
    stats = mercury.stats(res, started, attempt)
    return summary, stats


def _write_openai(tl: Timeline, names: list[str], model: str, effort: str, transport,
                  instructions: str | None = None) -> tuple[Summary, dict]:
    try:
        out, stats = openai_api.ask_json(system(tl, instructions), payload(tl, names), SCHEMA, "read_view", model,
                                         effort, transport)
    except openai_api.OpenAIError as e:
        raise WriterError(str(e)) from None
    summary = to_summary(out, tl, model) if isinstance(out, dict) and isinstance(out.get("sections"), list) else None
    if summary is None or not summary.sentences():
        raise WriterError(f"{model} returned no usable summary")
    return summary, stats


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


def to_summary(out: dict, tl: Timeline, writer: str = MODEL) -> Summary:
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
    return Summary(tldr=sentences(out.get("tldr", [])), sections=sections, writer=writer)


def _clock(t: float) -> str:
    t = int(t)
    h, m, s = t // 3600, t // 60 % 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
