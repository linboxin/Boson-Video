"""The planted-error test: does the checker accept true claims and catch false ones?

    uv run python scripts/planted_errors.py            # run it (TYPESAFE_API_KEY for the Jev rows, OPENAI_API_KEY for OpenAI's)
    uv run python scripts/planted_errors.py --build    # rebuild the fixture from the videos in the library

Each case is a claim about a real passage from two Chinese videos (SenseVoice transcripts),
with the passage before and after it, the way the checker sees a cited passage. True claims
should pass; planted errors (a changed number, a flipped direction, a negation, a wrong entity
or date) should not. Most claims are in English, because that is how a plugin user's AI writes.

Ways of checking:
- jev, both orders: Jev asked twice in one request with the options reversed (what ships)
- jev, one order: the question once, "supports" listed first (before 2026-10-04)
- openai, both orders / one order: the same questions to OpenAI's Decisions API (decisions.py)
- code only: numbers compared by value, nothing judges meaning (what a user without a key gets)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boson_video import checker, decisions, library  # noqa: E402
from boson_video.env import load_env  # noqa: E402
from boson_video.timeline import Segment, Sentence, Timeline, Video  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "planted_errors.json"

# (video, passage index, claim, true?, what was planted)
CASES = [
    ("slFa9Vx3crw", 27, "Tesla delivered 486,532 electric vehicles.", True, ""),
    ("slFa9Vx3crw", 27, "Tesla delivered 468,532 electric vehicles.", False, "number"),
    ("slFa9Vx3crw", 27, "Tesla delivered more vehicles than the number before it.", True, ""),
    ("slFa9Vx3crw", 27, "Tesla delivered fewer vehicles than the number before it.", False, "direction"),
    ("slFa9Vx3crw", 28, "Energy storage deployment was 13.7 GWh, and the earnings report is on October 21.", True, ""),
    ("slFa9Vx3crw", 28, "Energy storage deployment was 13.7 GWh, and the earnings report is on October 12.", False, "date"),
    ("slFa9Vx3crw", 252, "Customer A's share fell from 25.2% in 2023 to 20.9% in 2025.", True, ""),
    ("slFa9Vx3crw", 252, "Customer A's share rose from 20.9% in 2023 to 25.2% in 2025.", False, "direction"),
    ("slFa9Vx3crw", 252, "Customer B's share fell from 25.2% in 2023 to 20.9% in 2025.", False, "entity"),
    ("slFa9Vx3crw", 258, "In Q2 2026 the share was 18.3%.", True, ""),
    ("slFa9Vx3crw", 278, "US government revenue is forecast to fall to about 5% in Q4 2026.", True, ""),
    ("slFa9Vx3crw", 278, "US government revenue is forecast to fall to about 15% in Q4 2026.", False, "number"),
    ("slFa9Vx3crw", 151, "The previous chip peak was between $148 and $151.8.", True, ""),
    ("slFa9Vx3crw", 151, "The previous chip peak was between $158 and $161.8.", False, "number"),
    ("slFa9Vx3crw", 27, "特斯拉交付了四十八万六千五百三十二辆电动车。", True, ""),
    ("slFa9Vx3crw", 252, "客户A的占比逐年上升。", False, "direction"),
    ("qbReD1cGykQ", 38, "Each group has 128 questions.", True, ""),
    ("qbReD1cGykQ", 38, "Each group has 256 questions.", False, "number"),
    ("qbReD1cGykQ", 39, "By default, all models refuse the harmful questions, such as how to make a bomb.", True, ""),
    ("qbReD1cGykQ", 39, "By default, all models answer the harmful questions, such as how to make a bomb.", False, "negation"),
    ("qbReD1cGykQ", 42, "They record the residual stream at every layer when the last token of the prompt enters the model.", True, ""),
    ("qbReD1cGykQ", 42, "They record the residual stream at every layer when the first token of the prompt enters the model.", False, "detail"),
    ("qbReD1cGykQ", 74, "KL divergence quantifies the gap between the two models' outputs; a bigger gap gives a bigger result.", True, ""),
    ("qbReD1cGykQ", 74, "KL divergence quantifies the gap between the two models' outputs; a bigger gap gives a smaller result.", False, "direction"),
    ("qbReD1cGykQ", 47, "With 32 layers they record 32 residuals, each an array of 4096 numbers.", True, ""),
    ("qbReD1cGykQ", 47, "With 32 layers they record 16 residuals, each an array of 4096 numbers.", False, "number"),
    ("qbReD1cGykQ", 72, "Removing a direction can stop refusals but make the model talk nonsense.", True, ""),
    ("qbReD1cGykQ", 72, "Removing a direction always keeps the model's answers sensible.", False, "contradiction"),
]


def build() -> None:
    cases = []
    for video, i, claim, true, planted in CASES:
        tl = library.load(video)
        window = [tl.transcript[j].text for j in (i - 1, i, i + 1)]
        cases.append({"video": video, "cited": i, "claim": claim, "true": true, "planted": planted,
                      "passages": window, "at": round(tl.transcript[i].start, 1)})
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(cases)} cases to {FIXTURE}")


class OneOrder:
    """Jev as it was asked before 2026-10-04: each Choice once, in the written order."""

    def __init__(self, client):
        self.client = client

    async def system_one(self, state, questions):
        return await self.client.system_one(state, {k: v for k, v in questions.items() if not k.endswith("_r")})


def run_mode(cases: list[dict], make_client) -> list[str]:
    """The checker's verdict for every case, in order (a fresh client per case: each check runs its own event loop)."""
    out = []
    for c in cases:
        client = make_client() if make_client else None
        tl = Timeline(video=Video("planted", "", 60, "u"), frames=[], sheets=[])
        tl.transcript = [Segment(k * 5.0, k * 5.0 + 4, t) for k, t in enumerate(c["passages"])]
        s = Sentence(c["claim"], "", [1])
        checker.check_sentences(tl, [s], client=client)
        out.append(s.check or "unchecked")
    return out


def score(cases: list[dict], verdicts: list[str]) -> tuple[int, int, int, int, list[str]]:
    true = [(c, v) for c, v in zip(cases, verdicts) if c["true"]]
    false = [(c, v) for c, v in zip(cases, verdicts) if not c["true"]]
    accepted = sum(v == "supported" for _, v in true)
    caught = sum(v not in ("supported", "unchecked") for _, v in false)
    misses = [f"  true claim not accepted ({v}): {c['claim']}" for c, v in true if v != "supported"]
    misses += [f"  planted {c['planted']} missed ({v}): {c['claim']}" for c, v in false if v in ("supported", "unchecked")]
    return accepted, len(true), caught, len(false), misses


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    load_env()
    if args.build:
        build()
        return 0
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
    modes = [("code only", None)]
    if checker.jev_available():
        from typesafe_sdk import AsyncTypeSafeClient

        modes = [("jev, both orders", "both"), ("jev, one order", "one")] + modes
    if decisions.available():
        modes = [("openai, both orders", "openai"), ("openai, one order", "openai one")] + modes
    print(f"{len(cases)} cases: {sum(c['true'] for c in cases)} true, {sum(not c['true'] for c in cases)} planted\n")
    print(f"{'checker':18} {'true accepted':>14} {'planted caught':>15}")
    for name, kind in modes:
        client = None
        if kind == "both":
            client = AsyncTypeSafeClient
        elif kind == "one":
            client = lambda: OneOrder(AsyncTypeSafeClient())  # noqa: E731
        elif kind == "openai":
            client = decisions.AsyncDecisionsClient
        elif kind == "openai one":
            client = lambda: OneOrder(decisions.AsyncDecisionsClient())  # noqa: E731
        if kind is None:
            import os

            saved = os.environ.pop("TYPESAFE_API_KEY", None)
        try:
            verdicts = run_mode(cases, client)
        finally:
            if kind is None and saved:
                os.environ["TYPESAFE_API_KEY"] = saved
        a, t, c, f, misses = score(cases, verdicts)
        if kind is None:  # code judges numbers only, so true claims stay unchecked by design
            print(f"{name:18} {'not judged':>14} {c:>9} of {f:<3}")
            misses = [m for m in misses if "true claim" not in m]
        else:
            print(f"{name:18} {a:>8} of {t:<3} {c:>9} of {f:<3}")
        for m in misses:
            print(m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
