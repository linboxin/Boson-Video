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
    short = {"p0": {"starts": "先通过", "en": "first"}}
    full = {f"p{i}": {"starts": s.text[:5], "en": f"line {i}"} for i, s in enumerate(tl.transcript)}
    english, stats = study.translate(tl, [], transport=_mercury(short, full))
    assert english == ["line 0", "line 1", "line 2", "line 3"]
    assert stats["missing"] == 0 and stats["cost_usd"] > 0



def _by_chunk(reply):
    """Mercury answering each chunk by the ids it was given (chunks run at once, in any order)."""
    def handle(request):
        payload = json.loads(json.loads(request.content)["messages"][1]["content"])
        ids = [int(line.split(" ", 1)[0][1:]) for line in payload["transcript"].splitlines()]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply(ids))}}],
                                         "usage": {"prompt_tokens": 100, "completion_tokens": 50}})

    return httpx.MockTransport(handle)


def test_translate_keeps_only_english_that_quotes_its_own_passage(monkeypatch):
    monkeypatch.setattr(study, "CHUNK", 10)
    tl = _tl()
    tl.transcript = [Segment(i, i + 1, f"第{i}段，" + "说了一些话" * 3) for i in range(20)]
    # the first chunk: passage 7's English drifted onto passage 8's words; the second chunk is never usable
    reply = lambda ids: {f"p{i}": {"starts": f"p{i} " * (i == 3) + f"第{i + (i == 7)}段，说", "en": f"passage {i}"}
                         for i in ids} if ids[0] == 0 else {}  # passage 3 quotes its key too: still its own
    english, stats = study.translate(tl, [], transport=_by_chunk(reply))
    assert english[:10] == [f"passage {i}" for i in range(7)] + ["", "passage 8", "passage 9"]  # left out, not misplaced
    assert english[10:] == [""] * 10 and stats["missing"] == 11
    with pytest.raises(study.llm.LLMError, match="no usable translation"):
        study.translate(tl, [], transport=_by_chunk(lambda ids: {}))


def test_failed_english_keeps_the_terms_and_says_why(monkeypatch):
    from boson_video import checker, pipeline, writer
    from boson_video.timeline import Sentence, Summary, Term

    tl = _tl()
    term = Term("残差流", "残差流", "residual stream", "cánchā liú", "The model's running state.", Sentence("", "", [1]))
    monkeypatch.setattr(writer, "write", lambda tl, names, effort=None: (Summary(tldr=[], sections=[], writer="test"), {}))
    monkeypatch.setattr(writer, "repair", lambda tl, effort=None, check=None: {})
    monkeypatch.setattr(checker, "check", lambda tl, where=None: {})
    monkeypatch.setattr(study, "fill_summary_english", lambda tl, names: 0)
    monkeypatch.setattr(study, "translate", lambda tl, names: (_ for _ in ()).throw(study.llm.LLMError("no usable translation")))
    monkeypatch.setattr(study, "glossary", lambda tl, names, language: ([term], ["Why?"], {}))
    made = pipeline.add_summary(tl)
    assert tl.terms == [term] and tl.translation == []
    assert made["lacking"] == {"english": "No English transcript: no usable translation."}

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


def test_quiet_cuts_land_in_the_pauses():
    import numpy as np

    rate = sensevoice.RATE
    loud = np.ones(rate * 20, dtype=np.float32)
    loud[int(rate * 9.5):int(rate * 10.5)] = 0  # a pause near the middle
    edges = sensevoice.quiet_cuts(loud, 2)
    assert edges[0] == 0 and edges[-1] == len(loud)
    assert rate * 9.5 <= edges[1] <= rate * 10.5
