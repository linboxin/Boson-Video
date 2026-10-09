"""OpenAI's Decisions API client offline: requests in the API's shape, answers in Jev's."""

import asyncio
import json

import httpx
import pytest

from boson_video import checker, decisions
from boson_video.timeline import Segment, Sentence, Timeline, Video


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")


def _transport(answers, seen=None, statuses=()):
    queue = list(statuses)

    def handle(request):
        body = json.loads(request.content)
        if seen is not None:
            seen.append(body)
        if queue:
            return httpx.Response(queue.pop(0), json={"error": "busy"}, headers={"retry-after": "0"})
        return httpx.Response(200, json={"model": "gpt-6-luna", "answers": answers(body),
                                         "usage": {"input_tokens": 1100, "output_tokens": 0}})

    return httpx.MockTransport(handle)


def _choice(name, probs):
    return {"type": "choice", "name": name, "choice": max(probs, key=probs.get),
            "probabilities": [{"value": k, "probability": v} for k, v in probs.items()], "confidence": 0.9}


def test_jev_question_becomes_choices_in_the_same_order():
    q = decisions.question("relation", checker.RELATION)
    assert q["type"] == "choice" and q["name"] == "relation"
    assert [c["value"] for c in q["choices"]] == ["supports", "contradicts", "says_nothing"]
    assert q["choices"][0]["description"] == checker.RELATION["criteria"]["supports"]


def test_frames_go_as_inline_images_and_answers_come_back_in_jevs_shape(tmp_path):
    frame = tmp_path / "1000.jpg"
    frame.write_bytes(b"\xff\xd8jpeg")
    seen = []
    client = decisions.AsyncDecisionsClient(
        transport=_transport(lambda b: [_choice(q["name"], {"supports": 0.8, "contradicts": 0.15, "says_nothing": 0.05})
                                        for q in b["questions"]], seen))

    async def run():
        res = await client.system_one({"claim": "KL = 2.71", "frames": [str(frame)]},
                                      {"relation": checker.RELATION, "relation_r": checker.RELATION_REVERSED})
        await client.aclose()
        return res

    res = asyncio.run(run())
    content = seen[0]["input"][0]["content"]
    assert json.loads(content[0]["text"]) == {"claim": "KL = 2.71"}  # the path itself isn't sent as text
    assert content[1]["image_url"].startswith("data:image/jpeg;base64,")
    assert checker.both_orders(res, "relation")["supports"] == pytest.approx(0.8)
    assert client.usage["calls"] == 1 and client.usage["input_tokens"] == 1100


def test_a_refused_question_is_left_out_and_the_sentence_stays_unchecked():
    tl = Timeline(video=Video("t", "", 60, "u"), frames=[], sheets=[])
    tl.transcript = [Segment(0, 4, "a"), Segment(5, 9, "the passage"), Segment(10, 14, "c")]
    s = Sentence("A claim.", "", [1])
    client = decisions.AsyncDecisionsClient(
        transport=_transport(lambda b: [{"type": "refusal", "name": q["name"]} for q in b["questions"]]))
    stats = checker.check_sentences(tl, [s], client=client)
    assert s.check == "" and s.check_note == "the judge gave no answer"
    assert stats["checked_by"] == "openai+code"


def test_busy_answers_are_retried(monkeypatch):
    seen = []
    client = decisions.AsyncDecisionsClient(
        transport=_transport(lambda b: [_choice("relation", {"supports": 1.0})], seen, statuses=(429, 503)))
    answers = asyncio.run(client.ask("text", [decisions.question("relation", checker.RELATION)]))
    assert len(seen) == 3 and answers["relation"]["choice"] == "supports"


def test_no_key_says_which_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    assert not decisions.available()
    with pytest.raises(decisions.DecisionsError, match="OPENAI_API_KEY"):
        decisions.AsyncDecisionsClient()


def test_state_as_lines():
    assert decisions.render({"claim": "c", "screen_text": ["a", "b"]}, "lines") == "claim: c\nscreen_text:\n- a\n- b"
