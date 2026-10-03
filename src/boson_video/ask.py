"""Ask the video: which moment answers a question (Jev, TypeSafe's line-search recipe).

Every transcript passage gets an id. One Choice points at the passage that answers the
question, and a Noul in the same request says whether the video answers it at all
(a Choice always picks something). A Choice takes at most 255 options, so a long
transcript is searched in two passes: first a window of passages, then the passage.
"""

from __future__ import annotations

import asyncio
import os
import time

from .timeline import Segment

MAX_OPTIONS = 255
WINDOW = 30  # passages per window in the first pass of a long transcript
FOUND, ABSENT = 0.7, 0.35  # the recipe's thresholds for the Noul; tune on real questions


class AskError(RuntimeError):
    pass


def _pid(i: int) -> str:
    return f"P{i:04d}"


def _clock(t: float) -> str:
    t = int(t)
    h, m, s = t // 3600, t // 60 % 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _document(segments: list[Segment], ids: list[int], windows: bool = False) -> str:
    lines = []
    for n, i in enumerate(ids):
        if windows and n % WINDOW == 0:
            w = n // WINDOW
            last = ids[min(n + WINDOW, len(ids)) - 1]
            lines.append(f"## W{w:03d} ({_clock(segments[i].start)}–{_clock(segments[last].end)})")
        lines.append(f"{_pid(i)} | {_clock(segments[i].start)} | {segments[i].text}")
    return "\n".join(lines)


def _questions(question: str, options: list[str], unit: str) -> dict:
    return {
        "where": {
            "type": "choice",
            "instructions": f'Which {unit} of the transcript contains the answer to: "{question}"?',
            "criteria": {o: None for o in options},
        },
        "exists": {
            "type": "noul",
            "instructions": f'Does any part of the transcript address or answer: "{question}"?',
            "criteria": {
                "true": "At least one passage states or directly implies the answer",
                "false": "No passage addresses this",
            },
        },
    }


def ask(segments: list[Segment], question: str, top: int = 3, client=None) -> dict:
    """{"exists": p, "verdict": ..., "moments": [(index, probability), ...], "seconds": s}"""
    if not segments:
        raise AskError("no transcript to search")
    if client is None and not os.environ.get("TYPESAFE_API_KEY"):
        raise AskError("no TYPESAFE_API_KEY in .env (Jev answers questions)")
    started = time.perf_counter()
    result = asyncio.run(_ask(segments, question, top, client))
    p = result["exists"]
    result["verdict"] = "answered" if p >= FOUND else ("not in this video" if p < ABSENT else "partly addressed")
    result["seconds"] = round(time.perf_counter() - started, 2)
    return result


async def _ask(segments: list[Segment], question: str, top: int, client) -> dict:
    if client is None:
        from typesafe_sdk import AsyncTypeSafeClient

        client = AsyncTypeSafeClient()
    everything = list(range(len(segments)))
    candidates = everything
    exists = None
    if len(segments) > MAX_OPTIONS:  # pass 1: which window
        n_windows = -(-len(segments) // WINDOW)
        options = [f"W{w:03d}" for w in range(n_windows)]
        res = await client.system_one(_document(segments, everything, windows=True),
                                      _questions(question, options, "window (##)"))
        exists = res.nouls["exists"].noul
        probs = res.choices["where"].probabilities
        best = sorted(range(n_windows), key=lambda w: probs.get(f"W{w:03d}", 0.0), reverse=True)[:2]
        candidates = sorted(i for w in best for i in range(w * WINDOW, min((w + 1) * WINDOW, len(segments))))
    res = await client.system_one(_document(segments, candidates), _questions(question, [_pid(i) for i in candidates], "passage"))
    probs = res.choices["where"].probabilities
    ranked = sorted(candidates, key=lambda i: probs.get(_pid(i), 0.0), reverse=True)[:top]
    return {
        "exists": res.nouls["exists"].noul if exists is None else max(exists, res.nouls["exists"].noul),
        "moments": [(i, round(float(probs.get(_pid(i), 0.0)), 3)) for i in ranked],
    }
