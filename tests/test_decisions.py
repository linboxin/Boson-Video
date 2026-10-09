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
    monkeypatch.setenv("BOSON_SCREEN_CHECK", "1")


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


# ---- the second look: frames for a sentence the words didn't confirm ------------------------------

from types import SimpleNamespace  # noqa: E402

from boson_video.timeline import Scene, Screen  # noqa: E402


class FakeJev:
    """Jev with fixed verdicts by claim: "supports", "contradicts" or "says_nothing"."""

    def __init__(self, verdicts):
        self.verdicts = verdicts

    async def system_one(self, state, questions):
        v = self.verdicts[state["claim"]]
        return SimpleNamespace(choices={k: SimpleNamespace(probabilities={v: 1.0}) for k in questions})


def _video(tmp_path):
    """0-30 s a slide that builds (frames at 2 s and 12 s), 30-60 s the next topic (frame at 31 s)."""
    tl = Timeline(video=Video("t", "", 60, "u"), frames=[], sheets=[])
    tl.transcript = [Segment(0, 9, "here is the request"), Segment(10, 25, "the model is tpt six luna"),
                     Segment(31, 40, "now images")]
    tl.scenes = [Scene(0, 0, 30, [], 0, 0, "new"), Scene(1, 30, 60, [], 1, 1, "new")]
    tl.screens = [Screen(2, 0, "POST /v1/decisions", image="frames/2000.jpg"),
                  Screen(12, 0, 'model: "gpt-6-luna"', image="frames/12000.jpg"),
                  Screen(31, 1, "input_image", image="frames/31000.jpg")]
    (tmp_path / "frames").mkdir()
    for sc in tl.screens:
        (tmp_path / sc.image).write_bytes(b"\xff\xd8jpeg")
    return tl


def test_on_screen_gives_the_last_build_step_and_stays_in_the_span(tmp_path):
    tl = _video(tmp_path)
    found = checker.on_screen(tl, tmp_path, 10, 25)
    assert [(p.name, lines, t) for p, lines, t in found] == [("12000.jpg", ["POST /v1/decisions", 'model: "gpt-6-luna"'], 12)]
    tl.scenes.append(Scene(2, 60, 70, [], 2, 0, "repeat"))  # the slide again: its frames are the first appearance's
    assert [p.name for p, _, _ in checker.on_screen(tl, tmp_path, 61, 65)] == ["12000.jpg"]


REAL = decisions.AsyncDecisionsClient


def _judge_frames(answer, seen):
    return _transport(lambda b: [_choice(q["name"], answer) for q in b["questions"]], seen)


def test_the_screen_confirms_what_speech_garbled_and_says_so(tmp_path, monkeypatch):
    tl = _video(tmp_path)
    garbled = Sentence("The model is gpt-6-luna.", "", [1])
    said = Sentence("Here is the request.", "", [0])
    seen = []
    monkeypatch.setattr(decisions, "AsyncDecisionsClient",
                        lambda: REAL(transport=_judge_frames({"supports": 0.9, "contradicts": 0.1}, seen)))
    stats = checker.check_sentences(tl, [garbled, said], client=FakeJev({garbled.text: "says_nothing", said.text: "supports"}),
                                    where=tmp_path)
    assert garbled.check == "supported" and garbled.check_note == "seen on screen (0:12; OpenAI looked at the frame)"
    assert said.check == "supported" and said.check_note == ""
    assert len(seen) == 1  # only the sentence the words didn't confirm was asked again
    assert seen[0]["input"][0]["content"][1]["image_url"].startswith("data:image/jpeg")
    assert stats["checked_by"] == "jev+code+frames" and stats["frames"]["confirmed"] == 1


def test_numbers_must_be_said_or_shown_whatever_the_judge_says(tmp_path, monkeypatch):
    tl = _video(tmp_path)
    wrong = Sentence("The request goes to /v2/decisions.", "", [1])
    unshown = Sentence("The model answers in 211 ms.", "", [1])
    monkeypatch.setattr(decisions, "AsyncDecisionsClient",
                        lambda: REAL(transport=_judge_frames({"supports": 1.0}, [])))
    checker.check_sentences(tl, [wrong, unshown], client=FakeJev({wrong.text: "contradicts", unshown.text: "says_nothing"}),
                            where=tmp_path)
    assert wrong.check == "contradicted"  # the judge said yes, but the 2 of /v2 is neither said nor shown (/v1 is)
    assert unshown.check == "unsupported"  # 211 is neither said nor on screen, whatever the judge says


def test_a_key_alone_spends_nothing_the_switch_is_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("BOSON_SCREEN_CHECK")
    tl = _video(tmp_path)
    s = Sentence("The model is gpt-6-luna.", "", [1])
    seen = []
    monkeypatch.setattr(decisions, "AsyncDecisionsClient", lambda: REAL(transport=_judge_frames({"supports": 1.0}, seen)))
    stats = checker.check_sentences(tl, [s], client=FakeJev({s.text: "says_nothing"}), where=tmp_path)
    assert not decisions.screen_check_on() and seen == []
    assert s.check == "unsupported" and stats["checked_by"] == "jev+code"


def test_no_folder_or_no_key_means_no_second_look(tmp_path, monkeypatch):
    tl = _video(tmp_path)
    s = Sentence("The model is gpt-6-luna.", "", [1])
    assert checker.check_sentences(tl, [s], client=FakeJev({s.text: "says_nothing"}))["checked_by"] == "jev+code"
    monkeypatch.delenv("OPENAI_API_KEY")
    assert checker.check_sentences(tl, [s], client=FakeJev({s.text: "says_nothing"}), where=tmp_path)["checked_by"] == "jev+code"
    assert s.check == "unsupported"
