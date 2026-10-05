"""Every sentence of the read view checked against the passages it cites.

Jev judges meaning with one Choice per sentence (TypeSafe's citation-check recipe): do
the cited passages support the claim, contradict it, or say nothing about it? All
checks run at once. Numbers are checked in code, because Jev is weak at them (it let
"3.21" become "5.21"): every number in a sentence must appear in its cited passages or
their immediate neighbours (speech recognition cuts passages mid-sentence). A neighbour
that holds the number joins the sentence's citations, so its link points at the right
second, and Jev then judges the sentence against the corrected passages.
"""

from __future__ import annotations

import asyncio
import os
import re
import time

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
_EN_NUMBER = re.compile(r"\b(" + "|".join(_EN_WORDS) + r")\b(?:\s+(hundred|thousand|million|billion|trillion)\b)?", re.I)


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
        scale = {"hundred": 1e2, "thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
        out.append((m.group(0), _EN_WORDS[m.group(1).lower()] * scale.get((m.group(2) or "").lower(), 1)))
    return out


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
        if i in glued or any(abs(value - v) <= 0.01 * max(abs(v), 1e-9) for v in said_values):
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


def check(tl: Timeline, concurrency: int = 16, client=None) -> dict:
    """Fill in Sentence.check / check_p for the summary and the glossary; returns counts and timing."""
    if tl.summary is None:
        raise CheckError("nothing to check")
    stats = check_sentences(tl, tl.summary.sentences() + [t.said for t in tl.terms if t.said.text], concurrency, client)
    tl.summary.checker = stats["checked_by"]
    return stats


def jev_available(client=None) -> bool:
    return client is not None or bool(os.environ.get("TYPESAFE_API_KEY"))


def check_sentences(tl: Timeline, sentences: list[Sentence], concurrency: int = 16, client=None) -> dict:
    """Check any sentences that cite `tl.transcript` (summary lines, glossary lines, answers).

    With Jev: Jev judges the meaning and code checks the numbers ("jev+code"). Without a key:
    code checks the numbers only ("code"); a sentence whose numbers are all there is left
    unchecked rather than marked as supported, because nothing judged its meaning.
    """
    started = time.perf_counter()
    if jev_available(client):
        asyncio.run(_check_all(tl, sentences, concurrency, client))
        checked_by = "jev+code"
    else:
        texts = [seg.text for seg in tl.transcript]
        for s in sentences:
            if not s.evidence:
                s.check, s.check_p = "uncited", 1.0
                continue
            s.evidence, missing = repair_evidence(s.text, s.evidence, texts, strict=True)
            if missing:
                s.check, s.check_p, s.check_note = "unsupported", 1.0, f"{', '.join(missing)} isn't in the cited passages"
        checked_by = "code"
    counts: dict[str, int] = {}
    for s in sentences:
        counts[s.check] = counts.get(s.check, 0) + 1
    return {"seconds": round(time.perf_counter() - started, 2), "counts": counts, "checked_by": checked_by}


def both_orders(res, name: str) -> dict[str, float]:
    """Average a Choice's probabilities over its two orders (`name`, `name_r`); one if only one came back."""
    answers = [res.choices[k].probabilities for k in (name, name + "_r") if k in res.choices]
    labels = set().union(*answers)
    return {label: sum(float(a.get(label, 0.0)) for a in answers) / len(answers) for label in labels}


async def _check_all(tl: Timeline, sentences: list[Sentence], concurrency: int, client) -> None:
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
        choice = max(probs, key=probs.get)
        sentence.check = VERDICTS[choice]
        sentence.check_p = round(probs[choice], 3)
        if missing and sentence.check == "supported":
            sentence.check, sentence.check_note = "unsupported", f"{', '.join(missing)} isn't in the cited passages"

    try:
        await asyncio.gather(*(one(s) for s in sentences))
    except Exception as e:  # the SDK's errors carry the status and a hint
        raise CheckError(f"Jev could not check the summary: {str(e)[:200]}") from None


def _clock(t: float) -> str:
    t = int(t)
    return f"{t // 60}:{t % 60:02d}"
