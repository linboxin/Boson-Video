"""How close a transcript is to human-made captions: word error rate, or for Chinese,
an error rate over characters (English words inside Chinese count as one unit each).

error rate = (substitutions + deletions + insertions) / units in the human version
"""

from __future__ import annotations

import re

import numpy as np

_TAG = re.compile(r"<[^>]+>")
_BRACKETS = re.compile(r"\[[^\]]*\]|\([^)]*\)|（[^）]*）|♪")  # [Applause], (笑声), music marks
_TIMING = re.compile(r"^\d\d:\d\d[:.\d]* --> ")
_UNITS = re.compile(r"[\u3400-\u9fff]|[a-z0-9]+(?:'[a-z]+)?")


def vtt_text(vtt: str) -> str:
    """Plain text of a WebVTT caption file, without timings, tags or repeated lines."""
    lines, last = [], None
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or _TIMING.match(line) or line.startswith(("Kind:", "Language:", "NOTE")):
            continue
        if line.isdigit():
            continue
        line = _TAG.sub("", line)
        if line != last:
            lines.append(line)
            last = line
    return " ".join(lines)


def units(text: str, simplified: bool = False) -> list[str]:
    """Comparable units: each Chinese character, and each lowercased English word or number.

    `simplified` turns traditional characters into simplified first (OpenCC, a dev dependency), so
    a transcriber writing 里 isn't charged an error against captions writing 裡."""
    if simplified:
        from opencc import OpenCC

        text = OpenCC("t2s").convert(text)
    return _UNITS.findall(_BRACKETS.sub(" ", text).lower())


def error_rate(reference: list[str], hypothesis: list[str]) -> float:
    """Levenshtein distance over units, divided by the reference length."""
    if not reference:
        return 0.0 if not hypothesis else 1.0
    vocab = {u: i for i, u in enumerate(set(reference) | set(hypothesis))}
    ref = np.array([vocab[u] for u in reference])
    hyp = np.array([vocab[u] for u in hypothesis])
    cols = np.arange(len(hyp) + 1)
    prev = cols.astype(np.int64)
    for i in range(1, len(ref) + 1):
        sub = prev[:-1] + (hyp != ref[i - 1])  # substitute (or match)
        dele = prev[1:] + 1  # delete a reference unit
        cand = np.empty_like(prev)
        cand[0] = i
        cand[1:] = np.minimum(sub, dele)
        # insertions: row[j] = min over k <= j of cand[k] + (j - k)
        prev = np.minimum.accumulate(cand - cols) + cols
    return float(prev[-1]) / len(ref)
