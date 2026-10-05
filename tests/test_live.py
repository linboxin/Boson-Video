"""Hits YouTube. Run with `uv run pytest -m live`."""

import json

import pytest

from boson_video.pipeline import build

pytestmark = pytest.mark.live


def test_slide_talk_end_to_end():
    tl = build("https://www.youtube.com/watch?v=zjkBMFhNj_g")  # Karpathy, 1-hour LLM talk
    assert tl.video.duration > 3000
    assert len(tl.frames) > 300 and len(tl.chapters) > 10 and tl.heat
    assert len(tl.scenes) > 30
    assert tl.timings["total"] < 5000


def test_talking_head_end_to_end():
    tl = build("9JKT5rBbrwM")  # a 25-min talking head with no captions
    assert tl.captions == []
    assert any(s.kind == "base" and s.duration > 1200 for s in tl.scenes)


def test_words_on_the_mac(tmp_path):
    from boson_video.pipeline import add_words

    tl = build("snZ811wvjjw")  # TEDxTaipei, Mandarin, 14:29, human zh-TW captions
    add_words(tl, tmp_path, "zh_TW")
    assert tl.language == "zh_TW"
    assert sum(len(s.text) for s in tl.transcript) > 2500
    assert tl.timings["speech"] < 30_000


@pytest.mark.live
def test_planted_errors_with_jev():
    """Jev on the planted-error fixture: 14 of 14 true accepted and 13 of 14 planted caught on
    2026-10-04 (it missed an entity swap). This guards against getting worse."""
    import importlib.util
    import os
    from pathlib import Path

    from boson_video.env import load_env

    load_env()
    if not os.environ.get("TYPESAFE_API_KEY"):
        pytest.skip("no TYPESAFE_API_KEY")
    path = Path(__file__).resolve().parents[1] / "scripts" / "planted_errors.py"
    spec = importlib.util.spec_from_file_location("planted_errors", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from typesafe_sdk import AsyncTypeSafeClient

    cases = json.loads(mod.FIXTURE.read_text(encoding="utf-8"))
    accepted, true, caught, planted, misses = mod.score(cases, mod.run_mode(cases, AsyncTypeSafeClient))
    assert accepted == true and caught >= planted - 1, misses
