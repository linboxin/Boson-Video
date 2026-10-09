"""The planted-error test for what was shown: claims about slides, checked against the slide.

    uv run python scripts/planted_frames.py            # run it (needs the frames in the library)
    uv run python scripts/planted_frames.py --build    # rebuild the fixture's screen text from the library

Each case is a claim about one full-resolution frame of f4zGqjYWS_Q (charts, prices, timelines and
diagrams in Chinese, with English and Chinese claims). The truth of every claim was read off the
frame by eye (2026-10-09), not taken from OCR. Planted errors change a number, a direction, an
entity, a date or a detail; "not shown" claims are true in the world but absent from the slide,
so a checker that accepts them is bringing in what it knows rather than what was shown.

Ways of checking:
- openai, frame: OpenAI's Decisions API looks at the frame, both option orders (decisions.py)
- openai, frame, one order: the same, "supports" listed first
- openai, screen text: the same model given only the OCR text of the frame
- jev, screen text: Jev given the OCR text (the best Jev can do today: it can't see)
- code only, screen text: the claim's numbers looked up in the OCR text
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boson_video import checker, decisions, library  # noqa: E402
from boson_video.env import load_env  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "planted_frames.json"
VIDEO = "f4zGqjYWS_Q"

# (frame, claim, true?, what was planted)
CASES = [
    ("1350000.jpg", "Recursion's revenue fell 60.1% year on year in Q2'26.", True, ""),
    ("1350000.jpg", "Recursion's revenue fell 16.0% year on year in Q2'26.", False, "number"),
    ("1350000.jpg", "Recursion's revenue grew 60.1% year on year in Q2'26.", False, "direction"),
    ("1350000.jpg", "Insilico Medicine (3696.HK) grew revenue 287% year on year in the first half of 2026.", True, ""),
    ("1350000.jpg", "Recursion grew revenue 287% year on year in the first half of 2026.", False, "entity"),
    ("1350000.jpg", "The highest quarterly revenue in Recursion's chart is 35.54 million dollars.", True, ""),
    ("1350000.jpg", "The highest quarterly revenue in Recursion's chart is 53.54 million dollars.", False, "number"),
    ("1350000.jpg", "Insilico turned a profit for the first time in 1H26, thanks to upfront payments from new BD deals.", True, ""),
    ("1350000.jpg", "Insilico posted a loss in 1H26 despite new BD deals.", False, "negation"),
    ("1350000.jpg", "Recursion is headquartered in Salt Lake City.", False, "not shown"),
    ("1430000.jpg", "Year to date in 2026, TWST is up 546%.", True, ""),
    ("1430000.jpg", "Year to date in 2026, TWST is up 564%.", False, "number"),
    ("1430000.jpg", "TXG is up 743% over the past 12 months.", True, ""),
    ("1430000.jpg", "ILMN is up 743% over the past 12 months.", False, "entity"),
    ("1430000.jpg", "RXRX is down 13.6% over the past 12 months.", True, ""),
    ("1430000.jpg", "RXRX is up 13.6% over the past 12 months.", False, "direction"),
    ("1430000.jpg", "英矽智能今年以来上涨53.5%。", True, ""),
    ("1430000.jpg", "英矽智能今年以来上涨35.5%。", False, "number"),
    ("1430000.jpg", "TWST's share price is $205.00.", True, ""),
    ("1430000.jpg", "TXG's share price is $205.00.", False, "entity"),
    ("1270000.jpg", "Illumina's revenue grew 9.4% year on year in Q2'26.", True, ""),
    ("1270000.jpg", "TXG's revenue grew 12.6% year on year in Q2'26.", False, "direction"),
    ("1270000.jpg", "Twist's revenue rose in every one of the eight quarters shown.", True, ""),
    ("1270000.jpg", "TXG's revenue rose in every one of the eight quarters shown.", False, "detail"),
    ("1270000.jpg", "金斯瑞只披露半年度数据。", True, ""),
    ("1270000.jpg", "Illumina is the world's largest DNA sequencing company.", False, "not shown"),
    ("320000.jpg", "Drug discovery traditionally takes 3 to 5 years.", True, ""),
    ("320000.jpg", "Drug discovery traditionally takes 5 to 8 years.", False, "number"),
    ("320000.jpg", "From preclinical development to FDA approval takes 7 to 10 years.", True, ""),
    ("320000.jpg", "The whole process takes 10 to 15 years in total.", True, ""),
    ("320000.jpg", "The whole process takes 15 to 20 years in total.", False, "number"),
    ("320000.jpg", "Phase III trials involve hundreds to thousands of people.", True, ""),
    ("320000.jpg", "Phase I trials involve hundreds to thousands of people.", False, "detail"),
    ("340000.jpg", "The slide places INS018_055 at the candidate-drug step, from 2021.", True, ""),
    ("340000.jpg", "The slide places INS018_055 at the candidate-drug step, from 2019.", False, "date"),
    ("340000.jpg", "Insilico's Rentosertib is given as an example from before LLMs.", True, ""),
    ("420000.jpg", "PandaOmics, from Insilico, ranks targets from omics data and the literature.", True, ""),
    ("420000.jpg", "PandaOmics comes from Google DeepMind.", False, "entity"),
    ("420000.jpg", "AlphaFold turns an amino acid sequence into a 3D structure.", True, ""),
    ("420000.jpg", "Chemistry42 turns an amino acid sequence into a 3D structure.", False, "detail"),
    ("420000.jpg", "AlphaFold won its creators the 2024 Nobel Prize in Chemistry.", False, "not shown"),
    ("610000.jpg", "Insilico, an AI-native drug company, has taken a new target as far as Phase III.", True, ""),
    ("610000.jpg", "Relay (RLAY) works from known targets.", True, ""),
    ("610000.jpg", "Relay (RLAY) works from new targets.", False, "detail"),
    ("610000.jpg", "Eli Lilly covers the whole chain, end to end, and also sells the drug after launch.", True, ""),
    ("1190000.jpg", "In a BD deal the money comes in three parts: an upfront payment, milestones and a share of sales.", True, ""),
    ("1190000.jpg", "In a BD deal the money comes in two parts: an upfront payment and a share of sales.", False, "number"),
    ("1190000.jpg", "The small biotech gives drug rights to the big pharma company, which pays money in return.", True, ""),
    ("1190000.jpg", "The big pharma company gives drug rights to the small biotech, which pays money in return.", False, "direction"),
    ("1190000.jpg", "Only the upfront payment is real money; milestones and sales shares may only come later.", True, ""),
]

CRITERIA = {
    "supports": "The {what} states the claim, with the same numbers, names and direction",
    "contradicts": "The {what} states something different: another number, name, date or direction",
    "says_nothing": "The {what} does not show what the claim is about",
}


def relation(what: str, field: str = "") -> dict:
    """The same Choice for a picture and for its OCR text, so only what the judge is given differs."""
    return {"type": "choice",
            "instructions": f"How does the {what}{f' (`{field}`)' if field else ''} relate to the `claim`? "
                            f"Judge only what the {what} shows, not what you know from elsewhere.",
            "criteria": {k: v.format(what=what) for k, v in CRITERIA.items()}}


FRAME = relation("picture")  # the frame goes as an image, not in the text
SCREEN = relation("text read off the screen by OCR, which can be garbled", "screen_text")
BOTH = relation("picture, with the text read off it by OCR, which can be garbled", "screen_text")
QUESTIONS = {"frame": FRAME, "screen": SCREEN, "frame+screen": BOTH}


def build() -> None:
    data = json.loads((library.home() / VIDEO / "timeline.json").read_text(encoding="utf-8"))
    text = {Path(s["image"]).name: s["text"].splitlines() for s in data.get("screens", []) if s.get("image")}
    cases = [{"video": VIDEO, "frame": f, "claim": c, "true": t, "planted": p, "screen_text": text.get(f, [])}
             for f, c, t, p in CASES]
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(cases)} cases to {FIXTURE}")


async def judge_all(cases: list[dict], make_client, given: str, both: bool) -> tuple[list[str], dict]:
    """`given`: what the judge sees besides the claim: "frame", "screen" (OCR text) or "frame+screen"."""
    client = make_client()
    gate = asyncio.Semaphore(8)
    spec = QUESTIONS[given]
    reversed_spec = {**spec, "criteria": dict(reversed(list(spec["criteria"].items())))}
    questions = {"relation": spec, **({"relation_r": reversed_spec} if both else {})}
    started = time.perf_counter()

    async def one(c: dict) -> str:
        state = {"claim": c["claim"]}
        if "frame" in given:
            state["frames"] = [str(library.home() / c["video"] / "frames" / c["frame"])]
        if "screen" in given:
            state["screen_text"] = c["screen_text"]
        async with gate:
            res = await client.system_one(state, questions)
        probs = checker.both_orders(res, "relation")
        return checker.VERDICTS[max(probs, key=probs.get)] if probs else "no answer"

    verdicts = await asyncio.gather(*(one(c) for c in cases))
    if hasattr(client, "aclose"):
        await client.aclose()
    usage = dict(getattr(client, "usage", {}))
    usage["wall_seconds"] = round(time.perf_counter() - started, 1)
    return list(verdicts), usage


def code_only(cases: list[dict]) -> list[str]:
    return ["unsupported" if checker.missing_numbers(c["claim"], c["screen_text"], strict=True) else "unchecked"
            for c in cases]


def score(cases: list[dict], verdicts: list[str]) -> tuple[int, int, int, int, list[str]]:
    true = [(c, v) for c, v in zip(cases, verdicts) if c["true"]]
    false = [(c, v) for c, v in zip(cases, verdicts) if not c["true"]]
    accepted = sum(v == "supported" for _, v in true)
    caught = sum(v not in ("supported", "unchecked", "no answer") for _, v in false)
    misses = [f"  true claim not accepted ({v}): {c['claim']}" for c, v in true if v != "supported"]
    misses += [f"  planted {c['planted']} missed ({v}): {c['claim']}" for c, v in false
               if v in ("supported", "unchecked", "no answer")]
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
    missing = {c["frame"] for c in cases if not (library.home() / c["video"] / "frames" / c["frame"]).exists()}
    if missing:
        print(f"frames not in the library: {', '.join(sorted(missing))} (build {VIDEO} first)")
        return 1
    modes = []
    if decisions.available():
        lines = lambda: decisions.AsyncDecisionsClient(render="lines")  # noqa: E731
        modes += [("openai, frame", decisions.AsyncDecisionsClient, "frame", True),
                  ("openai, frame, one order", decisions.AsyncDecisionsClient, "frame", False),
                  ("openai, frame, as lines", lines, "frame", True),
                  ("openai, frame + text", decisions.AsyncDecisionsClient, "frame+screen", True),
                  ("openai, frame + text, lines", lines, "frame+screen", True),
                  ("openai, screen text", decisions.AsyncDecisionsClient, "screen", True)]
    if checker.jev_available():
        from typesafe_sdk import AsyncTypeSafeClient

        modes.append(("jev, screen text", AsyncTypeSafeClient, "screen", True))
    print(f"{len(cases)} cases on {len({c['frame'] for c in cases})} frames: "
          f"{sum(c['true'] for c in cases)} true, {sum(not c['true'] for c in cases)} planted\n")
    print(f"{'checker':26} {'true accepted':>14} {'planted caught':>15}   cost")
    for name, make_client, given, both in modes:
        verdicts, usage = asyncio.run(judge_all(cases, make_client, given, both))
        a, t, c, f, misses = score(cases, verdicts)
        cost = ""
        if usage.get("calls"):
            cost = (f"{usage['input_tokens'] / usage['calls']:.0f} tokens and {usage['seconds'] / usage['calls']:.2f} s "
                    f"a call, ${decisions.cost_usd(usage['input_tokens']):.4f} for all")
        print(f"{name:26} {a:>8} of {t:<3} {c:>9} of {f:<3}   {cost}")
        for m in misses:
            print(m)
    verdicts = code_only(cases)
    a, t, c, f, misses = score(cases, verdicts)
    false_alarms = [x for x, v in zip(cases, verdicts) if x["true"] and v == "unsupported"]
    print(f"{'code only, screen text':26} {'not judged':>14} {c:>9} of {f:<3}   "
          f"{len(false_alarms)} true claims flagged (OCR misread their numbers)")
    for x in false_alarms:
        print(f"  flagged although true: {x['claim']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
