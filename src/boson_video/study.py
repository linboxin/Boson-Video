"""Learning from a video in a language you only half know.

Three jobs, each one Mercury request (run at once, alongside the summary):

- `translate`: every transcript passage in English, so the transcript can be read side by side.
- `glossary`: the technical terms a non-expert would trip on, each with its English name, a
  plain explanation, and what the video itself says about it (cited, then checked by Jev).
- `answer`: a question in your own words. Jev finds the moments (ask.py); Mercury explains
  them in plain English, citing the passages; Jev checks each cited sentence. Background the
  video doesn't give is allowed, but kept apart and labelled, so evidence and explanation never mix.
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import ask as ask_mod
from . import checker, llm
from .timeline import Segment, Sentence, Term, Timeline

CHUNK = 40  # passages per translation request; chunks run at once (asked for 120, Mercury stopped near 90: 2026-10-14)

TRANSLATE_SYSTEM = """You translate a video's machine-made transcript into natural English, passage by passage.

- `transcript` has one passage per line: its key (p0, p1, …), then what was said. Return an object with exactly those keys. For each: `starts`, the first five characters of what was said (after the key), copied exactly, and `en`, the English for that passage alone.
- Each passage may start or end mid-sentence. Never move words from one passage into another: if a passage ends mid-sentence, its English ends there too ("…").
- Speech recognition garbles English words inside other languages ("ibedding" for "embedding", "toan" for "token"). Translate what the speaker meant; spell names as `names` does.
- `on_screen`, when given, is text shown in the video: it spells names right where speech recognition misheard them (英矽智能 on a slide, 因系智能 in the transcript). Follow its spelling, and give a company or product its usual English name (英矽智能 → Insilico Medicine).
- Keep technical terms precise and keep every number. Don't summarise, don't merge or skip passages.
"""


def _translate_schema(keys: list[str]) -> dict:
    """One required key per passage: asked for a list, Mercury split passages into sentences and
    numbered those, so the English drifted lines away from its Chinese (2026-10-14)."""
    line = {"type": "object", "properties": {"starts": {"type": "string"}, "en": {"type": "string"}},
            "required": ["starts", "en"], "additionalProperties": False}
    return {"type": "object", "properties": {k: line for k in keys}, "required": keys, "additionalProperties": False}

GLOSSARY_SYSTEM = """You help a learner who is fluent in everyday {language} but not in this video's technical field.

From the transcript, pick the 8-20 technical terms such a learner would most need explained to follow the video, in order of first use. Skip everyday words.

For each term:
- `heard`: the term exactly as it is written in the transcript, copied character for character, even if misheard (it is used to find the term in the text).
- `term`: the term written correctly, as the speaker meant it (`on_screen`, when given, shows how the video itself spells it).
- `en`: its usual English name. `reading`: pinyin with tone marks if the term is Chinese, else "".
- `explain`: 1-2 plain English sentences for a smart non-expert: what it is and why it matters here. This is general background.
- `said`: one sentence in {language} saying what the video itself says about it; `said_en`: the same in English; `evidence`: the ids of the passages that say it. Use only what those passages say.

Also give `questions`: 3 short questions, in English, that this learner would want to ask about the video.
"""

SENTENCE_FIELDS = {"said": {"type": "string"}, "said_en": {"type": "string"},
                   "evidence": {"type": "array", "items": {"type": "integer"}}}
GLOSSARY_SCHEMA = {
    "type": "object",
    "properties": {
        "terms": {"type": "array", "items": {
            "type": "object",
            "properties": {"heard": {"type": "string"}, "term": {"type": "string"}, "en": {"type": "string"},
                           "reading": {"type": "string"}, "explain": {"type": "string"}, **SENTENCE_FIELDS},
            "required": ["heard", "term", "en", "reading", "explain", "said", "said_en", "evidence"],
            "additionalProperties": False,
        }},
        "questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["terms", "questions"], "additionalProperties": False,
}

ANSWER_SYSTEM = """You answer a learner's question about a video, in plain words and in the language the question is asked in, using the transcript passages given.

- `passages`: one per line: id, time, what was said, then " // " and an English translation.
- `answer`: 1-4 short sentences answering the question from the passages. Each cites the ids it rests on; use only what those passages say. Explain jargon in plain words.
- `background`: 0-2 sentences of general knowledge the learner needs that the passages don't give (leave it empty if not needed). Never put claims about the video here.
- `found` says whether a search judged that the video answers the question. If the passages don't answer it, leave `answer` empty and use `background` to say so and give a brief general answer.
"""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "array", "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "integer"}}},
            "required": ["text", "evidence"], "additionalProperties": False,
        }},
        "background": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "background"], "additionalProperties": False,
}


class StudyError(RuntimeError):
    pass


def translate(tl: Timeline, names: list[str], transport=None) -> tuple[list[str], dict]:
    """English for every passage (empty strings where a chunk failed twice; an error if all did)."""
    english, stats = translate_texts([s.text for s in tl.transcript], tl.video.title, names, transport, tl.screen_lines())
    if english and not any(english):
        raise llm.LLMError(f"{llm.endpoint().model} returned no usable translation")
    return english, stats


def translate_texts(texts: list[str], title: str, names: list[str], transport=None,
                    on_screen: list[str] | None = None) -> tuple[list[str], dict]:
    """English for each text, in chunks sent at once; a chunk that fails twice stays empty."""
    n = len(texts)
    if not n:
        return [], {"seconds": 0, "cost_usd": 0, "output_tokens": 0, "missing": 0}
    started = time.perf_counter()

    def chunk(lo: int):
        ids = range(lo, min(lo + CHUNK, n))
        payload = {"title": title, "names": names, "transcript": "\n".join(f"p{i} {texts[i]}" for i in ids)}
        if on_screen:
            payload["on_screen"] = on_screen
        try:
            out, st = llm.ask_json(TRANSLATE_SYSTEM, payload, _translate_schema([f"p{i}" for i in ids]), "translation",
                                   usable=lambda o: sum(_anchored(o, i, texts[i]) for i in ids) >= 0.9 * len(ids),
                                   effort="instant", max_tokens=16000, transport=transport)
        except llm.LLMError:  # this chunk goes without English; the others still count
            return {}, {"cost_usd": 0, "output_tokens": 0}
        return {i: out[f"p{i}"]["en"].strip() for i in ids if _anchored(out, i, texts[i])}, st

    english = [""] * n
    cost, tokens = 0.0, 0
    with ThreadPoolExecutor(8) as pool:
        for lines, st in pool.map(chunk, range(0, n, CHUNK)):
            cost += st["cost_usd"]
            tokens += st["output_tokens"]
            for i, en in lines.items():
                english[i] = en
    return english, {"seconds": round(time.perf_counter() - started, 2), "cost_usd": round(cost, 5),
                     "output_tokens": tokens, "missing": english.count("")}


def _anchored(reply: dict, i: int, text: str) -> bool:
    """The reply's English for passage `i`, quoting how that passage starts: a line that drifted
    onto a neighbouring passage quotes the wrong words, and is left out rather than shown."""
    line = reply.get(f"p{i}")
    if not isinstance(line, dict) or not isinstance(line.get("en"), str):
        return False
    said, quoted = _plain(text), _plain(re.sub(rf"^\s*p{i}(?!\d)", "", str(line.get("starts", ""))))  # some quote the key too
    return not said or bool(quoted) and said.startswith(quoted[:3])


def _plain(text: str) -> str:
    return re.sub(r"[\W_]+", "", text).lower()


def fill_summary_english(tl: Timeline, names: list[str], transport=None) -> int:
    """Translate any summary sentence or title the writer left without English; returns how many."""
    if tl.summary is None:
        return 0
    slots = [(x, "text_en", x.text) for x in tl.summary.sentences() if not x.text_en]
    slots += [(sec, "title_en", sec.title) for sec in tl.summary.sections if not sec.title_en and sec.title]
    if not slots:
        return 0
    english, _ = translate_texts([text for _, _, text in slots], tl.video.title, names, transport, tl.screen_lines())
    for (obj, attr, _), en in zip(slots, english):
        setattr(obj, attr, en)
    return len(slots)


def glossary(tl: Timeline, names: list[str], language: str, transport=None) -> tuple[list[Term], list[str], dict]:
    n = len(tl.transcript)
    payload = {"title": tl.video.title, "names": names,
               "transcript": "\n".join(f"{i} {s.text}" for i, s in enumerate(tl.transcript))}
    if lines := tl.screen_lines():
        payload["on_screen"] = lines
    out, st = llm.ask_json(GLOSSARY_SYSTEM.format(language=language), payload, GLOSSARY_SCHEMA, "glossary",
                               usable=lambda o: bool(o.get("terms")), transport=transport)
    terms = []
    for t in out["terms"]:
        heard = (t.get("heard") or "").strip()
        term = (t.get("term") or "").strip() or heard
        if not term:
            continue
        evidence = sorted({e for e in t.get("evidence", []) if isinstance(e, int) and 0 <= e < n})
        said, said_en = (t.get("said") or "").strip(), (t.get("said_en") or "").strip()
        terms.append(Term(heard=heard, term=term, en=(t.get("en") or "").strip(), reading=(t.get("reading") or "").strip(),
                          explain=(t.get("explain") or "").strip(),
                          said=Sentence(said, "" if said_en == said else said_en, evidence),
                          mentions=mentions(tl.transcript, heard or term)))
    terms.sort(key=lambda t: t.mentions[0] if t.mentions else (t.said.evidence[0] if t.said.evidence else n))
    questions = [q.strip() for q in out.get("questions", []) if isinstance(q, str) and q.strip()][:4]
    return terms, questions, st


def mentions(transcript: list[Segment], heard: str) -> list[int]:
    """Passages that contain the term (case-insensitive, ignoring spaces: "L L M" = "LLM")."""
    if not heard:
        return []
    needle = re.sub(r"\s+", "", heard).lower()
    return [i for i, s in enumerate(transcript) if needle in re.sub(r"\s+", "", s.text).lower()]


def answer(tl: Timeline, question: str, jev=None, transport=None, where: Path | None = None) -> dict:
    """Jev finds the moments, Mercury explains them, Jev checks the explanation."""
    if not tl.transcript:
        raise StudyError("no transcript to ask")
    started = time.perf_counter()
    english = tl.translation if len(tl.translation) == len(tl.transcript) else [""] * len(tl.transcript)
    # Jev reads both languages, so an English question matches a Chinese passage more surely.
    both = [Segment(s.start, s.end, f"{s.text} // {en}" if en else s.text) for s, en in zip(tl.transcript, english)]
    try:
        found = ask_mod.ask(both, question, client=jev)
    except ask_mod.AskError as e:
        raise StudyError(str(e)) from None
    around = sorted({j for i, _ in found["moments"] for j in range(i - 2, i + 3) if 0 <= j < len(both)})
    payload = {
        "video": tl.video.title,
        "question": question,
        "found": found["verdict"],
        "passages": "\n".join(f"{i} {_clock(both[i].start)} {both[i].text}" for i in around),
    }
    try:
        out, st = llm.ask_json(ANSWER_SYSTEM, payload, ANSWER_SCHEMA, "answer",
                                   usable=lambda o: bool(o.get("answer") or o.get("background")), transport=transport)
    except llm.LLMError as e:
        raise StudyError(str(e)) from None
    allowed = set(around)
    sentences = [Sentence(x["text"].strip(), "", sorted({e for e in x.get("evidence", []) if e in allowed}))
                 for x in out["answer"] if (x.get("text") or "").strip()]
    if sentences:
        try:
            checker.check_sentences(tl, sentences, client=jev, where=where)
        except checker.CheckError as e:
            raise StudyError(str(e)) from None
    background = [b.strip() for b in out["background"] if b.strip()]
    if found["verdict"] == "not in this video":
        # "The video doesn't say…" is a remark, not evidence: unchecked lines join the background
        background = [s.text for s in sentences if s.check != "supported"] + background
        sentences = [s for s in sentences if s.check == "supported"]
    return {
        "question": question,
        "verdict": found["verdict"],
        "moments": [{"i": i, "t": tl.transcript[i].start, "p": p, "text": tl.transcript[i].text, "en": english[i]}
                    for i, p in found["moments"]],
        "answer": [{"text": s.text, "t": min(tl.transcript[i].start for i in s.evidence) if s.evidence else None,
                    "check": s.check, "note": s.check_note} for s in sentences],
        "background": background,
        "seconds": round(time.perf_counter() - started, 2),
        "cost_usd": st["cost_usd"],
        "asked": time.strftime("%Y-%m-%d %H:%M"),
    }


def _clock(t: float) -> str:
    t = int(t)
    h, m, s = t // 3600, t // 60 % 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
