"""The read view's words: Mercury turns the transcript into a short summary and sections.

Every sentence cites the transcript passages it rests on, so the page can link it to
its second and Jev can check it. Text is written in the video's language, with an
English version for the toggle.
"""

from __future__ import annotations

import json
import time

from . import mercury
from .mercury import MODEL
from .timeline import Section, Sentence, Summary, Timeline

LANGUAGES = {
    "zh_CN": "Simplified Chinese",
    "zh_TW": "Traditional Chinese",
    "zh_HK": "Traditional Chinese",
    "yue_CN": "Cantonese, in Traditional Chinese characters",
}

SYSTEM = """You turn a video's machine-made transcript into a short read view.

Rules:
- `transcript` has one passage per line: its id, its start time, then what was said.
- Use only what the transcript says. Every sentence cites the ids of all the transcript passages it rests on (usually 1-6); never use facts from passages you don't cite.
- Be concrete: keep the numbers, prices, dates, names, tickers, decisions and reasons. "He shorted Meta at 740" beats "He talked about Meta".
- The transcript was made by speech recognition, so names and English words inside other languages are often misheard (for example "Monelife" for "Money or Life"). When a word clearly sounds like an entry in `names`, write it the way `names` spells it. Never invent a name.
- `text` and `title` are in {language}. {english_rule}
- `tldr`: 2-3 sentences saying what the video is and its main conclusion.
- `sections`: in time order. If `chapters` are given, make one section per chapter, titled like the chapter. Otherwise split by topic into about one section per 4-8 minutes (at least 2). Each section has 2-4 sentences. `start_id` is the id of the section's first transcript passage.
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


def request_body(tl: Timeline, names: list[str], effort: str = "low") -> dict:
    language = language_name(tl.language)
    payload = {
        "title": tl.video.title,
        "channel": tl.video.channel,
        "duration": _clock(tl.video.duration),
        "names": names,
        "chapters": [{"title": c.title, "start": _clock(c.start)} for c in tl.chapters],
        # one line per passage, "<id> <time> <text>": far fewer tokens than an object per passage
        "transcript": "\n".join(f"{i} {_clock(s.start)} {s.text}" for i, s in enumerate(tl.transcript)),
    }
    rule = ("The video is in English: leave `text_en` and `title_en` empty." if language == "English" else
            f"The video is in {language}, so `text_en` and `title_en` are required: the English version of every `text` and `title`.")
    return mercury.body(SYSTEM.format(language=language, english_rule=rule), payload, SCHEMA, "read_view", effort)


def write(tl: Timeline, names: list[str], effort: str = "low", transport=None, attempt: int = 1) -> tuple[Summary, dict]:
    """Returns the summary and the call's stats (seconds, tokens, cost, attempts)."""
    if not tl.transcript:
        raise WriterError("no transcript to summarize")
    started = time.perf_counter()
    try:
        res = mercury.post(request_body(tl, names, effort), transport)
    except mercury.MercuryError as e:
        raise WriterError(str(e)) from None
    out = _read_output(res)
    summary = to_summary(out, tl) if out is not None else None
    if summary is None or not summary.sentences():
        last_bad_reply.update(res)  # kept for diagnosis
        if attempt == 1:  # the schema is usually honoured; one more try when it isn't
            summary, stats = write(tl, names, effort, transport, attempt=2)
            stats["seconds"] = round(time.perf_counter() - started, 2)
            return summary, stats
        raise WriterError("Mercury returned no usable summary twice")
    stats = mercury.stats(res, started, attempt)
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


def to_summary(out: dict, tl: Timeline) -> Summary:
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
    return Summary(tldr=sentences(out.get("tldr", [])), sections=sections, writer=MODEL)


def _clock(t: float) -> str:
    t = int(t)
    h, m, s = t // 3600, t // 60 % 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
