"""The read view: Mercury's summary, Jev's checks and the ask box, with fake model replies."""

import json
from types import SimpleNamespace

import httpx
import pytest

from boson_video import ask as ask_mod
from boson_video import checker, writer
from boson_video.timeline import Chapter, Screen, Section, Segment, Sentence, Summary, Timeline, Video


def _timeline(n: int = 6, language: str = "zh_CN") -> Timeline:
    segs = [Segment(i * 10.0, i * 10.0 + 9, f"passage {i} says {i * 100}") for i in range(n)]
    return Timeline(video=Video("A talk", "Chan", n * 10.0, "u", "abcdefghijk"), frames=[], sheets=[],
                    language=language, transcript=segs)


# --- writer -----------------------------------------------------------------------------

def test_request_body_is_compact_and_in_the_videos_language():
    body = writer.request_body(_timeline(3), ["Money or Life"], "low")
    system, user = body["messages"][0]["content"], json.loads(body["messages"][1]["content"])
    assert "Simplified Chinese" in system
    assert user["names"] == ["Money or Life"]
    assert user["transcript"].splitlines()[1] == "1 0:10 passage 1 says 100"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["temperature"] == 0.5
    assert "on_screen" not in user  # nothing was read off the screen


def test_the_writer_spells_names_the_way_the_screen_does():
    tl = _timeline(3)
    tl.screens = [Screen(0, 0, "举例英矽智能\n+500%\nPandaOmics\n" + "长" * 60, "发现疾病"),
                  Screen(9, 0, "PANDAOMICS\n举例英矽智能")]
    lines = tl.screen_lines()
    # bare numbers, long paragraphs and repeats (whatever their case) are left out; subtitles count
    assert lines == ["举例英矽智能", "PandaOmics", "发现疾病"]
    assert tl.screen_lines(limit=10) == ["举例英矽智能"]
    user = json.loads(writer.request_body(tl, [], "low")["messages"][1]["content"])
    assert user["on_screen"] == lines


def test_to_summary_cleans_and_orders():
    tl = _timeline(6)
    out = {
        "tldr": [{"text": "总结。", "text_en": "Summary.", "evidence": [0, 99, -1]}],
        "sections": [
            {"title": "后", "title_en": "Later", "start_id": 4, "sentences": [{"text": "四。", "text_en": "", "evidence": [4]}]},
            {"title": "前", "title_en": "前", "start_id": 0, "sentences": [
                {"text": "二。", "text_en": "Two.", "evidence": [2]},
                {"text": "一。", "text_en": "One.", "evidence": [1]},
                {"text": "  ", "text_en": "", "evidence": [1]},
            ]},
        ],
    }
    s = writer.to_summary(out, tl)
    assert s.tldr[0].evidence == [0]  # ids outside the transcript dropped
    assert [sec.title for sec in s.sections] == ["前", "后"]  # sections in time order
    assert s.sections[0].title_en == ""  # an "English" title equal to the original is dropped
    assert [x.text for x in s.sections[0].sentences] == ["一。", "二。"]  # read in video order, blanks dropped
    assert (s.sections[0].start, s.sections[0].end, s.sections[1].end) == (0.0, 40.0, 60.0)


def _reply(content) -> dict:
    return {"choices": [{"message": {"content": json.dumps(content) if not isinstance(content, str) else content}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 200}}


GOOD = {"tldr": [{"text": "好。", "text_en": "Good.", "evidence": [0]}],
        "sections": [{"title": "一", "title_en": "One", "start_id": 0, "sentences": [{"text": "有。", "text_en": "Yes.", "evidence": [1]}]}]}


def _transport(*replies):
    calls = iter(replies)
    return httpx.MockTransport(lambda request: httpx.Response(200, json=_reply(next(calls))))


def test_write_reads_good_wrapped_and_retries_bad_replies(monkeypatch):
    monkeypatch.setenv("INCEPTION_API_KEY", "test")
    tl = _timeline(3)
    summary, stats = writer.write(tl, [], transport=_transport(GOOD))
    assert [x.text for x in summary.sentences()] == ["好。", "有。"] and stats["attempts"] == 1
    assert stats["cost_usd"] == pytest.approx((1000 * 0.04 + 200 * 0.15) / 1e6, abs=1e-6)
    summary, _ = writer.write(tl, [], transport=_transport([GOOD]))  # wrapped in a list
    assert len(summary.sentences()) == 2
    summary, stats = writer.write(tl, [], transport=_transport({"tldr": [], "sections": []}, GOOD))
    assert stats["attempts"] == 2 and len(summary.sentences()) == 2
    with pytest.raises(writer.WriterError):
        writer.write(tl, [], transport=_transport("not json", {"tldr": [], "sections": []}))


# --- checker ----------------------------------------------------------------------------

@pytest.mark.parametrize("sentence, passages, missing", [
    ("price 5.21", ["at the 3.21 price"], ["5.21"]),
    ("price 3.21", ["at the 3.21 price"], []),
    ("costing 2 million dollars", ["about 2000000 dollars"], []),
    ("the 100 billion parameters", ["these 100000000000 parameters"], []),
    ("6,000 GPUs", ["about 6000 GPUs"], []),
    ("the llama 2 70B model", ["to get a llama 270 B"], []),
    ("提供 1 亿 token", ["免费的一亿 token"], []),
    ("System 1 thinking", ["only have a system one", "system 2"], []),
    ("in the 1930s", ["back in the 30s at school"], ["1930"]),
    ("about 5 things", ["no numbers here at all"], []),  # nothing to compare against
])
def test_missing_numbers(sentence, passages, missing):
    assert checker.missing_numbers(sentence, passages) == missing


def test_repair_evidence_adds_the_neighbour_that_holds_the_number():
    texts = ["intro", "首次买入了 grab", "软件在 3.21的价格买入", "no numbers"]
    assert checker.repair_evidence("买入了 Grab，价格为 3.21", [1], texts) == ([1, 2], [])
    assert checker.repair_evidence("买入了 Grab", [1], texts) == ([1], [])


class FakeJev:
    """Answers the relation question from a table keyed by claim text."""

    def __init__(self, table):
        self.table, self.states = table, []

    async def system_one(self, state, questions):
        self.states.append(state)
        choice = self.table[state["claim"]]
        probs = {"supports": 0.1, "contradicts": 0.1, "says_nothing": 0.1, choice: 0.8}
        return SimpleNamespace(choices={"relation": SimpleNamespace(choice=choice, probabilities=probs)})


def test_check_combines_jev_with_the_number_rule():
    tl = _timeline(4)
    tl.summary = Summary(tldr=[
        Sentence("passage 1 says 100", "", [1]),
        Sentence("passage 1 says 999", "", [1]),
        Sentence("the opposite", "", [2]),
        Sentence("no source", "", []),
    ], sections=[], writer="test")
    fake = FakeJev({"passage 1 says 100": "supports", "passage 1 says 999": "supports", "the opposite": "contradicts"})
    stats = checker.check(tl, client=fake)
    verdicts = [(s.check, s.check_note) for s in tl.summary.sentences()]
    assert verdicts == [("supported", ""), ("unsupported", "999 isn't in the cited passages"),
                        ("contradicted", ""), ("uncited", "")]
    assert stats["counts"] == {"supported": 1, "unsupported": 1, "contradicted": 1, "uncited": 1}
    assert len(fake.states[0]["passages"]) == 3  # the cited passage and its two neighbours


# --- ask --------------------------------------------------------------------------------

class FakeSearch:
    def __init__(self, exists, pick):
        self.exists, self.pick, self.calls = exists, pick, []

    async def system_one(self, state, questions):
        options = list(questions["where"]["criteria"])
        self.calls.append(options)
        target = self.pick(options)
        probs = {o: (0.9 if o == target else 0.1 / max(1, len(options) - 1)) for o in options}
        return SimpleNamespace(choices={"where": SimpleNamespace(probabilities=probs)},
                               nouls={"exists": SimpleNamespace(noul=self.exists)})


def test_ask_short_transcript_in_one_pass():
    segs = [Segment(i, i + 1, f"line {i}") for i in range(20)]
    fake = FakeSearch(0.95, lambda options: "P0007")
    found = ask_mod.ask(segs, "where is line 7?", client=fake)
    assert found["verdict"] == "answered" and found["moments"][0] == (7, 0.9)
    assert len(fake.calls) == 1


def test_ask_long_transcript_in_two_passes_and_says_when_absent():
    segs = [Segment(i, i + 1, f"line {i}") for i in range(600)]
    fake = FakeSearch(0.02, lambda options: "W010" if options[0].startswith("W") else "P0305")
    found = ask_mod.ask(segs, "where is line 305?", client=fake)
    assert len(fake.calls) == 2 and fake.calls[0][0] == "W000" and len(fake.calls[0]) == 20
    assert all(o.startswith("P") for o in fake.calls[1]) and len(fake.calls[1]) <= 2 * ask_mod.WINDOW
    assert found["moments"][0][0] == 305 and found["verdict"] == "not in this video"


def test_a_bare_list_of_sections_is_still_a_summary():
    reply = {"choices": [{"message": {"content": json.dumps([
        {"title": "财报", "title_en": "Earnings", "start_id": 0,
         "sentences": [{"text": "交付了 48 万辆。", "text_en": "480k delivered.", "evidence": [0]}]},
    ], ensure_ascii=False)}}]}
    out = writer._read_output(reply)
    assert out["tldr"] == [] and out["sections"][0]["title_en"] == "Earnings"


def test_numbers_as_sensevoice_writes_them():
    # decimals with 点, years read digit by digit, 幺 for a spoken one
    assert checker.missing_numbers("Share fell from 25.2% to 18.3%", ["从二十五点二下降到十八点三"]) == []
    assert checker.missing_numbers("486,532 delivered in Q3 2026", ["二零二六年第三季度", "交付了四十八万六千五百三十二辆"]) == []
    assert checker.missing_numbers("464,391 produced", ["生产了四六四三九幺"]) == []
    assert checker.missing_numbers("Storage reached 13.7 GWh", ["储能是十三点七吉瓦时"]) == []
    assert checker.missing_numbers("Storage reached 15.7 GWh", ["储能是十三点七吉瓦时"]) == ["15.7"]


def test_a_year_read_digit_by_digit_doesnt_run_into_the_number_before_it():
    said = "他在二零二三年占据了百分之二十五点二二零二四年二十四点二二零二五年二十点九"
    values = [v for _, v in checker._values(said)]
    assert 25.2 in values and 2024 in values and 24.2 in values and 2025 in values and 20.9 in values
    assert checker.missing_numbers("24.2% in 2024", [said]) == []


def test_planted_errors_the_free_number_check_catches(monkeypatch):
    """Offline half of scripts/planted_errors.py: without Jev, code must catch every changed
    number or date and nothing else (it doesn't judge meaning)."""
    from pathlib import Path

    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    cases = json.loads((Path(__file__).parent / "fixtures" / "planted_errors.json").read_text(encoding="utf-8"))
    for c in cases:
        tl = _timeline(0)
        tl.transcript = [Segment(k * 5.0, k * 5.0 + 4, t) for k, t in enumerate(c["passages"])]
        s = Sentence(c["claim"], "", [1])
        checker.check_sentences(tl, [s])
        caught = s.check == "unsupported"
        assert caught == (c["planted"] in ("number", "date")), c["claim"]


def test_a_models_size_spoken_as_words():
    assert checker.missing_numbers("Llama 3 8B outperformed it", ["from LAMA three, eight B, and other models"]) == []


def test_a_number_from_a_name_in_the_title_needs_no_passage(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    tl = _timeline(3)
    tl.video.title = "Stanford CS329A Self-Improving AI Agents"
    s = Sentence("This CS329A lecture covers 100 things", "", [1])
    checker.check_sentences(tl, [s])
    assert s.check == ""  # 329 is in the title, 100 is in passage 1: nothing missing


# --- the writer, rewritten 2026-10-09 ---------------------------------------------------------

def test_the_summary_length_grows_with_the_video():
    assert [writer.target_sentences(m) for m in (2, 11, 28, 60, 180)] == [10, 14, 27, 48, 48]
    user = json.loads(writer.request_body(_timeline(3), [], "low")["messages"][1]["content"])
    assert user["minutes"] == 0 and user["target_sentences"] == 10
    assert "Never narrate the video" in writer.system(_timeline(3))


def test_instructions_can_be_swapped_per_call():
    body = writer.request_body(_timeline(3), [], "low", instructions="Old rules. {language}. {english_rule}")
    assert body["messages"][0]["content"].startswith("Old rules. Simplified Chinese.")


def _model(replies: dict, seen: list | None = None):
    """A fake OpenAI-compatible endpoint answering by the schema name each request asks for."""
    def handler(request):
        body = json.loads(request.content)
        name = body["response_format"]["json_schema"]["name"]
        if seen is not None:
            seen.append((str(request.url), name, body))
        reply = replies[name](json.loads(body["messages"][1]["content"])) if callable(replies[name]) else replies[name]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply, ensure_ascii=False)}}],
                                         "usage": {"prompt_tokens": 100, "completion_tokens": 20}})
    return httpx.MockTransport(handler)


def _sentence(text, *ids):
    return {"text": text, "text_en": "", "evidence": list(ids)}


def test_any_openai_compatible_endpoint_writes_by_configuration(monkeypatch):
    monkeypatch.setenv("BOSON_WRITER_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("BOSON_WRITER_MODEL", "qwen3")
    monkeypatch.delenv("BOSON_WRITER_EFFORT", raising=False)
    seen = []
    reply = {"tldr": [_sentence("一句", 0)], "sections": [{"title": "要点", "title_en": "", "start_id": 0, "sentences": [_sentence("二", 1)]}]}
    summary, _ = writer.write(_timeline(3), [], transport=_model({"read_view": reply}, seen))
    url, _, body = seen[0]
    assert url == "http://localhost:11434/v1/chat/completions" and body["model"] == "qwen3"
    assert "temperature" not in body and "reasoning_effort" not in body  # Mercury-only settings
    assert summary.writer == "qwen3"


def test_a_long_video_is_written_part_by_part(monkeypatch):
    monkeypatch.delenv("BOSON_WRITER_BASE_URL", raising=False)
    monkeypatch.setenv("INCEPTION_API_KEY", "test")
    tl = _timeline(100)  # 1,000 s
    tl.chapters = [Chapter(0, "开场"), Chapter(5, "一闪而过"), Chapter(300, "方法"), Chapter(700, "结论")]
    seen = []

    def section(body):
        first = int(body["transcript"].split(" ", 1)[0])
        assert body["with_numbers"] and body["target_sentences"] >= 2
        return {"title": f"第{first}段的要点", "title_en": "", "sentences": [_sentence(f"段落{first}", first)]}

    summary, stats = writer.write(tl, [], transport=_model({"section": section, "tldr": {"tldr": [_sentence("总的结论", 0, 70)]}}, seen))
    names = [name for _, name, _ in seen]
    assert names.count("section") == 3 and names[-1] == "tldr"  # a 5-second chapter joins its neighbour
    assert [sec.title for sec in summary.sections] == ["第0段的要点", "第30段的要点", "第70段的要点"]
    assert summary.tldr[0].text == "总的结论" and stats["parts"] == 3


def test_without_chapters_an_outline_finds_the_parts(monkeypatch):
    monkeypatch.delenv("BOSON_WRITER_BASE_URL", raising=False)
    monkeypatch.setenv("INCEPTION_API_KEY", "test")
    tl = _timeline(100)
    outline = {"sections": [{"start_id": 0, "covers": "a"}, {"start_id": 40, "covers": "b"}, {"start_id": 80, "covers": "c"}]}

    def section(body):
        first = int(body["transcript"].split(" ", 1)[0])
        return {"title": f"T{first}", "title_en": "", "sentences": [_sentence("x", first)]}

    summary, _ = writer.write(tl, [], transport=_model({"outline": outline, "section": section, "tldr": {"tldr": [_sentence("y", 0)]}}))
    assert [round(sec.start) for sec in summary.sections] == [0, 400, 800]


def test_repair_rewrites_drops_and_retitles(monkeypatch):
    monkeypatch.delenv("BOSON_WRITER_BASE_URL", raising=False)
    monkeypatch.setenv("INCEPTION_API_KEY", "test")
    tl = _timeline(6)
    wrong = Sentence("每段都说 999", "", [1], "unsupported")
    narrating = Sentence("本期视频介绍了第二段", "", [2], "supported")
    hopeless = Sentence("与视频无关的说法", "", [3], "unsupported")
    fine = Sentence("第五段说 500", "", [5], "supported")
    tl.summary = Summary([fine], [Section("开场", "", 0, 60, [wrong, narrating, hopeless])], "mercury-2.5")
    reply = {"items": [{"id": 0, "text": "第一段说 100", "text_en": "", "evidence": [1]},
                       {"id": 1, "text": "第二段说 200", "text_en": "", "evidence": [2]},
                       {"id": 2, "text": "", "text_en": "", "evidence": []}],
             "titles": [{"id": 0, "title": "各段的数字", "title_en": ""}]}
    rechecked = []

    def check(tl, sentences):
        rechecked.extend(sentences)
        for x in sentences:
            x.check = "supported"

    out = writer.repair(tl, transport=_model({"repair": reply}), check=check)
    sec = tl.summary.sections[0]
    assert [x.text for x in sec.sentences] == ["第一段说 100", "第二段说 200"] and sec.title == "各段的数字"
    assert rechecked == sec.sentences and out["dropped"] == 1 and out["still_failing"] == 0
    assert tl.summary.tldr == [fine]  # untouched
