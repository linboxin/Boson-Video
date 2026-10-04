"""The learning layer offline: translation, glossary and answers with fake Mercury and Jev replies."""

import json
from types import SimpleNamespace

import httpx
import pytest

from boson_video import sensevoice, study
from boson_video.timeline import Segment, Timeline, Video


def _tl() -> Timeline:
    tl = Timeline(video=Video("llm abliteration是什么？", "程序员老王", 60, "u", "qbReD1cGykQ"), frames=[], sheets=[])
    tl.language = "zh_CN"
    tl.transcript = [
        Segment(1, 5, "先通过 ibedding 转化"),
        Segment(6, 10, "每一层残差流的数值"),
        Segment(11, 15, "有害残差减去无害残差"),
        Segment(16, 20, "得到三十二个残差差值"),
    ]
    return tl


def _mercury(*replies):
    queue = list(replies)

    def handle(request):
        body = queue.pop(0) if len(queue) > 1 else queue[0]
        content = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                         "usage": {"prompt_tokens": 100, "completion_tokens": 50}})

    return httpx.MockTransport(handle)


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("INCEPTION_API_KEY", "test")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test")


def test_translate_fills_every_passage_and_retries_a_short_reply():
    tl = _tl()
    short = {"lines": [{"id": 0, "en": "first"}]}
    full = {"lines": [{"id": i, "en": f"line {i}"} for i in range(4)]}
    english, stats = study.translate(tl, [], transport=_mercury(short, full))
    assert english == ["line 0", "line 1", "line 2", "line 3"]
    assert stats["missing"] == 0 and stats["cost_usd"] > 0


def test_glossary_finds_mentions_and_orders_by_first_use():
    tl = _tl()
    reply = {"terms": [
        {"heard": "残差流", "term": "残差流", "en": "residual stream", "reading": "cánchā liú",
         "explain": "The model's running state.", "said": "每层都有残差流。", "said_en": "Every layer has one.", "evidence": [1, 99]},
        {"heard": "ibedding", "term": "embedding", "en": "embedding", "reading": "",
         "explain": "Tokens to vectors.", "said": "先通过 embedding。", "said_en": "First the embedding.", "evidence": [0]},
    ], "questions": ["What is a residual stream?", " "]}
    terms, questions, _ = study.glossary(tl, [], "Simplified Chinese", transport=_mercury(reply))
    assert [t.term for t in terms] == ["embedding", "残差流"]  # first said at 0, then at 1
    assert terms[1].said.evidence == [1]  # an id outside the transcript is dropped
    assert terms[1].mentions == [1]
    assert questions == ["What is a residual stream?"]


def test_mentions_ignore_case_and_spaces():
    segs = [Segment(0, 1, "一个新的技术 L L M abliteration"), Segment(1, 2, "llm 很强")]
    assert study.mentions(segs, "LLM") == [0, 1]


class FakeJev:
    """Answers TypeSafe's system_one: the ask recipe (where/exists) and the check (relation)."""

    def __init__(self, best: str, exists: float):
        self.best, self.exists = best, exists

    async def system_one(self, state, questions):
        if "relation" in questions:
            choice = SimpleNamespace(choice="supports", probabilities={"supports": 0.93})
            return SimpleNamespace(choices={"relation": choice}, nouls={})
        options = list(questions["where"]["criteria"])
        probs = {o: (0.8 if o == self.best else 0.2 / max(1, len(options) - 1)) for o in options}
        return SimpleNamespace(choices={"where": SimpleNamespace(choice=self.best, probabilities=probs)},
                               nouls={"exists": SimpleNamespace(noul=self.exists)})


def test_answer_cites_checks_and_keeps_background_apart():
    tl = _tl()
    tl.translation = ["First the embedding", "Each layer's residual stream", "Harmful minus harmless", "32 differences"]
    reply = {"answer": [{"text": "They subtract the harmless average from the harmful one.", "evidence": [2, 50]}],
             "background": ["A residual stream is the model's running internal state."]}
    out = study.answer(tl, "How do they find the direction?", jev=FakeJev("P0002", 0.9), transport=_mercury(reply))
    assert out["verdict"] == "answered"
    assert out["moments"][0]["i"] == 2 and out["moments"][0]["en"] == "Harmful minus harmless"
    assert out["answer"] == [{"text": "They subtract the harmless average from the harmful one.", "t": 11,
                              "check": "supported", "note": ""}]
    assert out["background"] == ["A residual stream is the model's running internal state."]


def test_answer_when_the_video_doesnt_say():
    tl = _tl()
    reply = {"answer": [], "background": ["The video doesn't cover this. In general, …"]}
    out = study.answer(tl, "What is the weather?", jev=FakeJev("P0000", 0.1), transport=_mercury(reply))
    assert out["verdict"] == "not in this video" and out["answer"] == [] and out["background"]


def test_shouted_english_goes_lower_case_but_acronyms_stay():
    assert sensevoice.tidy("先通过 IBEDDING 转化 TOKEN 和 MOE AI LLM") == "先通过 ibedding 转化 token 和 MOE AI LLM"
