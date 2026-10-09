"""Every sentence of the read view checked against the passages it cites.

Jev judges meaning with one Choice per sentence (TypeSafe's citation-check recipe): do
the cited passages support the claim, contradict it, or say nothing about it? All
checks run at once. Numbers are checked in code, because Jev is weak at them (it let
"3.21" become "5.21"): every number in a sentence must appear in its cited passages or
their immediate neighbours (speech recognition cuts passages mid-sentence). A neighbour
that holds the number joins the sentence's citations, so its link points at the right
second, and Jev then judges the sentence against the corrected passages.

A sentence the words don't confirm gets a second look with what was on screen while it was said
(OpenAI's Decisions API, which can see frames; Jev can't): speech recognition garbles names and
numbers that a slide or code on screen shows plainly. The frame can only confirm. It costs OpenAI
credit, so it runs only with BOSON_SCREEN_CHECK=1 and OPENAI_API_KEY set.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path

from .timeline import Sentence, Timeline

VERDICTS = {"supports": "supported", "contradicts": "contradicted", "says_nothing": "unsupported"}
RELATION = {
    "type": "choice",
    "instructions": "How do the transcript `passages` relate to the `claim`?",
    "criteria": {
        "supports": "The passages state the claim or directly imply that it is true",
        "contradicts": "The passages state the opposite of the claim or imply it is false",
        "says_nothing": "The passages do not address what the claim asserts, either way",
    },
}
# jev-1.13 leans toward the option listed first (TypeSafe's list of its weaknesses), and
# "supports" comes first above. The same question goes out a second time, in the same request,
# with the options reversed, and the two answers are averaged.
RELATION_REVERSED = {**RELATION, "criteria": dict(reversed(list(RELATION["criteria"].items())))}


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_SCALED = re.compile(
    r"(\d+(?:[.,]\d+)*)(?:\s*(thousand|million|billion|trillion|bn|mn|[kmbt])\b|\s*(万|亿|千))?", re.I
)
_SCALES = {"thousand": 1e3, "k": 1e3, "千": 1e3, "万": 1e4, "million": 1e6, "mn": 1e6, "m": 1e6,
           "亿": 1e8, "billion": 1e9, "bn": 1e9, "b": 1e9, "trillion": 1e12, "t": 1e12}
_CN_DIGITS = {"零": 0, "〇": 0, "幺": 1, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
              "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10**4, "亿": 10**8}
# SenseVoice writes spoken numbers in characters: 十八点三 (18.3), 二零二六 (2026, read digit by digit),
# 幺 for a spoken "one", and a scale after a decimal: 十三点七亿.
_CN_NUMBER = re.compile(r"([零〇幺一二两三四五六七八九十百千万亿]+)(?:点([零〇幺一二三四五六七八九]+)([万亿])?)?")
_EN_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty".split())}
_EN_WORDS.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90})
# "eight B" is how speech recognition writes a model's "8B" (Llama 3 8B, 2026-10-04)
_EN_NUMBER = re.compile(r"\b(" + "|".join(_EN_WORDS) + r")\b(?:\s+(hundred|thousand|million|billion|trillion|b|m|k)\b)?", re.I)


def _cn_value(text: str) -> int | None:
    """Value of a Chinese numeral such as 一亿, 三千五百, 两万, 十二, or 二零二六 read digit by digit;
    None if it isn't one."""
    if len(text) >= 2 and all(ch in _CN_DIGITS for ch in text):
        return int("".join(str(_CN_DIGITS[ch]) for ch in text))
    total, section, digit = 0, 0, None
    for ch in text:
        if ch in _CN_DIGITS:
            digit = _CN_DIGITS[ch]
        elif ch in ("万", "亿"):
            section = (section + (digit or 0)) or 1
            total += section * _CN_UNITS[ch]
            section, digit = 0, None
        else:
            section += (digit if digit is not None else 1) * _CN_UNITS[ch]
            digit = None
    value = total + section + (digit or 0)
    return value if value > 0 else None


# Speech recognition writes no punctuation, so a year read digit by digit runs into the number
# before it: 百分之二十五点二二零二四年 is 25.2 then 2024, not 25.22024. Split the year off.
_RUN_ON_YEAR = re.compile(r"(?<=[点零〇幺一二两三四五六七八九十])([一二][零〇九][零〇一二三四五六七八九]{2}年)")


def _values(text: str) -> list[tuple[str, float]]:
    """(as written, value) for every number in the text, scale words applied."""
    text = _RUN_ON_YEAR.sub(r" \1", text)
    out = []
    for m in _SCALED.finditer(text):
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        out.append((m.group(0).strip(), value * _SCALES.get((m.group(2) or m.group(3) or "").lower(), 1)))
    for m in _CN_NUMBER.finditer(text):
        whole, fraction, scale = m.group(1), m.group(2), m.group(3)
        if not any(ch in _CN_DIGITS or ch == "十" for ch in whole) or (whole in ("一", "幺") and not fraction):
            continue  # 亿 alone (数亿) is not a number, and a lone 一 is usually "a"
        v = _cn_value(whole)
        if v is None:
            continue
        value = float(v)
        if fraction:
            value += float("0." + "".join(str(_CN_DIGITS[ch]) for ch in fraction))
            value *= _CN_UNITS.get(scale or "", 1)
        out.append((m.group(0), value))
    for m in _EN_NUMBER.finditer(text):  # "system one", "six thousand"
        scale = {"hundred": 1e2, "thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12,
                 "k": 1e3, "m": 1e6, "b": 1e9}
        out.append((m.group(0), _EN_WORDS[m.group(1).lower()] * scale.get((m.group(2) or "").lower(), 1)))
    return out


def tolerance(written: str, value: float) -> float:
    """How far a said number may be from the claim's and still match, by how precisely the claim
    writes it: "468,532" must match exactly (a planted 468,532 passed for 486,532 under a flat 1%,
    2026-10-04), "25.2" within 0.05, "2 million" within half a million, and a rounded "6,000"
    within a thousand. Chinese numerals in a claim get half a percent."""
    m = re.match(r"(\d[\d,]*)(?:\.(\d+))?", written)
    if not m:
        return 0.005 * abs(value) + 1e-9
    whole, fraction = m.group(1).replace(",", ""), m.group(2)
    mantissa = float(whole + ("." + fraction if fraction else ""))
    scale = value / mantissa if mantissa else 1.0  # "2 million" -> 1e6
    if fraction:
        return 0.5 * 10 ** -len(fraction) * scale + 1e-9
    zeros = len(whole) - len(whole.rstrip("0")) if whole.strip("0") else 0
    if zeros >= 3:  # "6,000": a rounded figure, so a whole unit either way ("100" stays exact)
        return 10 ** zeros * scale + 1e-9
    return 0.5 * scale + 1e-9


def missing_numbers(sentence: str, passages: list[str], strict: bool = False) -> list[str]:
    """Numbers in the sentence that its passages never say, compared by value ("2 million" = 2000000).

    When the passages state no numbers at all, nothing is compared and nothing is missing, unless
    `strict`: then every number is missing. Strict is for checks where nothing else judges the
    sentence (no Jev key), so "the passages hold no numbers" can't read as "the numbers are there".
    """
    said = " ".join(passages)
    said_values = [v for _, v in _values(said)]
    if not said_values:
        return [w for w, _ in _values(sentence) if re.search(r"\d", w)] if strict else []
    digit_runs = re.sub(r"[^\d]+", " ", said.replace(",", ""))
    numbers = [(w, v) for w, v in _values(sentence) if re.search(r"\d", w)]
    bares = [(_NUMBER.match(w).group(0).replace(",", "") if _NUMBER.match(w) else "") for w, _ in numbers]
    glued = set()  # speech recognition glues neighbours: "llama 270 B" for "llama 2 70B"
    for i in range(len(bares) - 1):
        if bares[i] and bares[i + 1] and bares[i] + bares[i + 1] in digit_runs:
            glued |= {i, i + 1}
    missing = []
    for i, (written, value) in enumerate(numbers):
        if i in glued or any(abs(value - v) <= tolerance(written, value) for v in said_values):
            continue
        if len(bares[i]) >= 2 and bares[i] in digit_runs:
            continue  # part of a longer glued number
        missing.append(written)
    return missing


class CheckError(RuntimeError):
    pass


def repair_evidence(sentence: str, evidence: list[int], texts: list[str], strict: bool = False) -> tuple[list[int], list[str]]:
    """Add neighbouring passages that hold the sentence's numbers; return (evidence, still missing)."""
    window = sorted({j for i in evidence for j in (i - 1, i, i + 1) if 0 <= j < len(texts)})
    missing = missing_numbers(sentence, [texts[i] for i in window], strict)
    numbers = [w for w, _ in _values(sentence) if re.search(r"\d", w)]
    extra = {
        j for j in window
        if j not in evidence and _values(texts[j]) and len(missing_numbers(sentence, [texts[j]])) < len(numbers)
    }
    return sorted(set(evidence) | extra), missing


def check(tl: Timeline, concurrency: int = 16, client=None, where: Path | None = None) -> dict:
    """Fill in Sentence.check / check_p for the summary and the glossary; returns counts and timing.
    `where` is the video's folder, so a sentence the words can't confirm can be looked up on screen."""
    if tl.summary is None:
        raise CheckError("nothing to check")
    stats = check_sentences(tl, tl.summary.sentences() + [t.said for t in tl.terms if t.said.text], concurrency,
                            client, where)
    tl.summary.checker = stats["checked_by"]
    return stats


def jev_available(client=None) -> bool:
    return client is not None or bool(os.environ.get("TYPESAFE_API_KEY"))


def check_sentences(tl: Timeline, sentences: list[Sentence], concurrency: int = 16, client=None,
                    where: Path | None = None) -> dict:
    """Check any sentences that cite `tl.transcript` (summary lines, glossary lines, answers).

    With Jev: Jev judges the meaning and code checks the numbers ("jev+code"). Without a key:
    code checks the numbers only ("code"); a sentence whose numbers are all there is left
    unchecked rather than marked as supported, because nothing judged its meaning.

    Then the screen, when it is switched on (BOSON_SCREEN_CHECK=1 and an OpenAI key) and the
    video's folder is given (`where`): a sentence the
    words didn't confirm is asked again with the frames on screen while it was said ("+frames").
    The frame can confirm a sentence, never overrule one the words confirmed (see `look`).
    """
    started = time.perf_counter()
    frames: dict = {}
    if jev_available(client):
        frames = asyncio.run(_check_all(tl, sentences, concurrency, client, where))
        checked_by = f"{getattr(client, 'label', 'jev')}+code"  # Jev, or OpenAI's judge (decisions.py)
        if frames.get("looked"):
            checked_by += "+frames"
    else:
        texts = [seg.text for seg in tl.transcript]
        for s in sentences:
            if not s.evidence:
                s.check, s.check_p = "uncited", 1.0
                continue
            s.evidence, missing = repair_evidence(s.text, s.evidence, texts, strict=True)
            missing = [m for m in missing if not in_title(m, tl)]
            if missing:
                s.check, s.check_p, s.check_note = "unsupported", 1.0, f"{', '.join(missing)} isn't in the cited passages"
        checked_by = "code"
    counts: dict[str, int] = {}
    for s in sentences:
        counts[s.check] = counts.get(s.check, 0) + 1
    out = {"seconds": round(time.perf_counter() - started, 2), "counts": counts, "checked_by": checked_by}
    if frames.get("looked"):
        out["frames"] = frames
    return out


def in_title(written: str, tl: Timeline) -> bool:
    """A number that is part of a name in the video's title ("CS329A", "GPT-4"): the speaker needn't say it."""
    digits = "".join(ch for ch in written if ch.isdigit())
    return bool(digits) and digits in "".join(ch if ch.isdigit() else " " for ch in tl.video.title).split()


def both_orders(res, name: str) -> dict[str, float]:
    """Average a Choice's probabilities over its two orders (`name`, `name_r`); one if only one came back."""
    answers = [res.choices[k].probabilities for k in (name, name + "_r") if k in res.choices]
    labels = set().union(*answers)
    return {label: sum(float(a.get(label, 0.0)) for a in answers) / len(answers) for label in labels}


# The second look, for a sentence the words didn't confirm: the passages and what was on screen
# while they were said, together. On 2026-10-09 the frame alone overruled true sentences (a slide
# caught mid-build, a frame from the next topic), so it is only ever asked to confirm.
SAID_OR_SHOWN = {
    "type": "choice",
    "instructions": "How do the transcript `passages`, together with what was on screen while they were said (the "
                    "pictures, and `screen_text` read off them by OCR, which can be garbled), relate to the `claim`?",
    "criteria": {
        "supports": "What was said and shown, together, states the claim or directly implies it",
        "contradicts": "What was said or shown states the opposite of the claim or something different",
        "says_nothing": "Neither what was said nor what was shown addresses the claim",
    },
}
SAID_OR_SHOWN_REVERSED = {**SAID_OR_SHOWN, "criteria": dict(reversed(list(SAID_OR_SHOWN["criteria"].items())))}
FRAMES_PER_LOOK = 3
# The screen confirms only when it is sure. On the planted slide claims (scripts/planted_frames.py,
# 2026-10-09), lifting on any "supports" let 4 of 24 planted errors through (a figure moved to the
# next company's card, an arrow reversed); at 0.9 none got through and 9 true claims were rescued.
# The nearest planted error scored 0.89, so this is a thin margin, chosen on one video.
LOOK_SURE = 0.9


def on_screen(tl: Timeline, where: Path, t0: float, t1: float) -> list[tuple[Path, list[str], float]]:
    """The full-resolution frames on screen while [t0, t1] was said: (frame, all the text on screen by
    then, its time) for each scene the span overlaps. A slide that builds gives its last step before
    t1, the most complete; a repeated picture gives its first appearance, whose frames were fetched."""
    found = []
    for scene in tl.scenes:
        if scene.end <= t0 or scene.start >= t1:
            continue
        source, until = scene, t1
        if scene.kind == "repeat":
            first = next((s for s in tl.scenes if s.look == scene.look and s.kind == "new"), None)
            source, until = (first, first.end) if first else (scene, t1)
        shown = sorted((sc for sc in tl.screens if sc.scene == source.index and sc.image and sc.t <= until
                        and (where / sc.image).exists()), key=lambda sc: sc.t)
        if shown:
            lines = [line for sc in shown for line in sc.text.splitlines() if line.strip()]
            found.append((where / shown[-1].image, lines, shown[-1].t))
    return found


async def look(tl: Timeline, sentence: Sentence, where: Path, client, gate: asyncio.Semaphore) -> bool:
    """Ask again with the frames on screen; True when they confirm the sentence. Only a sentence the
    words didn't confirm is asked, and only "supported" changes it: a frame that seems to disagree
    leaves the words' verdict as it was. Numbers must still be said or read off the screen."""
    texts = [seg.text for seg in tl.transcript]
    seen: dict[Path, tuple[list[str], float]] = {}
    for i in sentence.evidence:
        for path, lines, t in on_screen(tl, where, tl.transcript[i].start, tl.transcript[i].end):
            seen.setdefault(path, (lines, t))
    if not seen:
        return False
    picked = sorted(seen.items(), key=lambda x: x[1][1])[:FRAMES_PER_LOOK]
    around = sorted({j for i in sentence.evidence for j in (i - 1, i, i + 1) if 0 <= j < len(texts)})
    screen_text = list(dict.fromkeys(line for _, (lines, _) in picked for line in lines))
    state = {"claim": sentence.text,
             "passages": [f"[{_clock(tl.transcript[i].start)}] {texts[i]}" for i in around],
             "screen_text": screen_text,
             "frames": [str(path) for path, _ in picked]}
    async with gate:
        res = await client.system_one(state, {"relation": SAID_OR_SHOWN, "relation_r": SAID_OR_SHOWN_REVERSED})
    probs = both_orders(res, "relation")
    if probs.get("supports", 0.0) < LOOK_SURE:
        return False
    if [m for m in missing_numbers(sentence.text, [texts[i] for i in around] + screen_text) if not in_title(m, tl)]:
        return False
    sentence.check, sentence.check_p = "supported", round(probs["supports"], 3)
    at = ", ".join(_clock(t) for _, (_, t) in picked)
    sentence.check_note = f"seen on screen ({at}; OpenAI looked at the frame{'s' if len(picked) > 1 else ''})"
    return True


async def _check_all(tl: Timeline, sentences: list[Sentence], concurrency: int, client,
                     where: Path | None = None) -> dict:
    """Jev (or the client given) judges every sentence; then the screen, for the ones it didn't confirm."""
    if client is None:
        from typesafe_sdk import AsyncTypeSafeClient

        client = AsyncTypeSafeClient()
    gate = asyncio.Semaphore(concurrency)
    texts = [seg.text for seg in tl.transcript]

    async def one(sentence: Sentence) -> None:
        if not sentence.evidence:
            sentence.check, sentence.check_p = "uncited", 1.0
            return
        sentence.evidence, missing = repair_evidence(sentence.text, sentence.evidence, texts)
        around = sorted({j for i in sentence.evidence for j in (i - 1, i, i + 1) if 0 <= j < len(texts)})
        state = {
            "claim": sentence.text,
            "passages": [f"[{_clock(tl.transcript[i].start)}] {tl.transcript[i].text}" for i in around],
        }
        async with gate:
            res = await client.system_one(state, {"relation": RELATION, "relation_r": RELATION_REVERSED})
        probs = both_orders(res, "relation")
        if not probs:  # OpenAI's judge may refuse a question; Jev always answers
            sentence.check_note = "the judge gave no answer"
            return
        choice = max(probs, key=probs.get)
        sentence.check = VERDICTS[choice]
        sentence.check_p = round(probs[choice], 3)
        missing = [m for m in missing if not in_title(m, tl)]
        if missing and sentence.check == "supported":
            sentence.check, sentence.check_note = "unsupported", f"{', '.join(missing)} isn't in the cited passages"

    try:
        await asyncio.gather(*(one(s) for s in sentences))
    except Exception as e:  # the SDK's errors carry the status and a hint
        judge = "OpenAI's judge" if getattr(client, "label", "jev") == "openai" else "Jev"
        raise CheckError(f"{judge} could not check the summary: {str(e)[:200]}") from None

    from . import decisions

    doubtful = [s for s in sentences if s.evidence and s.check in ("unsupported", "contradicted")]
    if where is None or not tl.screens or not doubtful or not decisions.screen_check_on():
        return {}
    eyes = client if getattr(client, "label", "") == "openai" else decisions.AsyncDecisionsClient()
    try:
        confirmed = await asyncio.gather(*(look(tl, s, where, eyes, gate) for s in doubtful))
    except Exception as e:  # the screen is an extra: the words' verdicts stand
        return {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    finally:
        if eyes is not client:
            await eyes.aclose()
    usage = eyes.usage
    return {"looked": usage["calls"], "confirmed": sum(confirmed), "input_tokens": usage["input_tokens"],
            "cost_usd": decisions.cost_usd(usage["input_tokens"])}


def _clock(t: float) -> str:
    t = int(t)
    return f"{t // 60}:{t % 60:02d}"
