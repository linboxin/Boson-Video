"""Hits YouTube. Run with `uv run pytest -m live`."""

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
