"""The product (boson-video web) offline: invite codes, the guard on posts, each code seeing only its
own videos, daily limits, uploads, the hosted refusal of YouTube links, and answers with frames."""

import pytest
from starlette.testclient import TestClient

from boson_video import jobs, library, study, web
from boson_video.timeline import Section, Sentence, Summary

from test_plugin import _tl

POST = {"X-BV": "1"}


@pytest.fixture
def started(monkeypatch):
    """The builds the server started, as (what, title); nothing is downloaded."""
    calls = []
    monkeypatch.setattr(jobs, "start", lambda ref, root=None, words=True, title=None: calls.append((ref, title)) or library.key(ref))
    return calls


@pytest.fixture
def home(tmp_path, monkeypatch, started):
    monkeypatch.setenv("BOSON_VIDEO_HOME", str(tmp_path))
    tl = _tl()
    tl.summary = Summary([Sentence("残差流是主干道", "The residual stream is the main road", [0], "supported")],
                         [Section("引子", "Intro", 0, 20, [Sentence("一百二十八个问题", "128 questions", [1], "unsupported")])],
                         "mercury", "jev+code")
    library.save(tl, tmp_path / "abcdefghijk")
    return tmp_path


def _client(root, hosted=False) -> TestClient:
    return TestClient(web.make_app(root, hosted))


def _join(c: TestClient, root, **limits) -> str:
    code = web.make_invite(root, "test", **limits)
    assert c.post("/api/join", json={"code": code.lower().replace("-", " ")}, headers=POST).json() == {"in": True}
    return code


def test_nothing_without_a_code(home):
    c = _client(home)
    assert c.get("/api/me").json() == {"in": False, "hosted": False}
    assert c.post("/api/join", json={"code": "AAAA-BBBB"}, headers=POST).status_code == 403
    assert c.post("/api/open", json={"link": "abcdefghijk"}, headers=POST).status_code == 401
    assert c.get("/api/video/abcdefghijk").status_code == 401
    assert c.get("/media/abcdefghijk/at/1000").status_code == 401
    assert "<div id=\"root\">" in c.get("/").text and c.get("/app/app.js").status_code == 200
    assert c.get("/app/../web.py").status_code == 404


def test_posts_only_from_the_page_itself(home):
    c = _client(home)
    code = web.make_invite(home)
    assert c.post("/api/join", json={"code": code}).status_code == 403  # no custom header: a cross-site form
    assert c.post("/api/join", json={"code": code}, headers={**POST, "Origin": "https://evil.example"}).status_code == 403
    assert c.post("/api/join", json={"code": code}, headers={**POST, "Origin": "http://testserver"}).status_code == 200


def test_posts_through_the_public_address_in_front(home, monkeypatch):
    """A free *.vercel.app name forwards to the server: its Origin is accepted once named."""
    c = _client(home)
    code = web.make_invite(home)
    vercel = {**POST, "Origin": "https://boson.vercel.app"}
    assert c.post("/api/join", json={"code": code}, headers=vercel).status_code == 403
    monkeypatch.setenv("BOSON_PUBLIC_URL", "https://boson.vercel.app")
    assert c.post("/api/join", json={"code": code}, headers=vercel).status_code == 200
    assert c.post("/api/join", json={"code": code}, headers={**POST, "Origin": "https://evil.vercel.app"}).status_code == 403


def test_a_code_sees_only_the_videos_it_opened(home, started):
    a, b = _client(home), _client(home)
    _join(a, home)
    _join(b, home)
    assert a.post("/api/open", json={"link": "https://youtu.be/abcdefghijk"}, headers=POST).json() == {"key": "abcdefghijk"}
    assert started == [("https://www.youtube.com/watch?v=abcdefghijk", None)]
    doc = a.get("/api/video/abcdefghijk").json()
    assert doc["video"]["title"] == "残差流是什么" and doc["status"]["stage"] == "done"
    assert doc["summary"]["tldr"][0] == {"text": "残差流是主干道", "en": "The residual stream is the main road", "t": 1,
                                         "check": "supported", "p": 0.0, "note": ""}
    # what the ribbon, the frame strips and the Scenes tab draw from
    assert doc["frames"][1] == [10.0, 0, 32, 0, 32, 18] and doc["sheets"] == [{"url": "/media/abcdefghijk/sheets/0.jpg", "w": 64, "h": 36}]
    assert [s["kind"] for s in doc["scenes"]] == ["new", "new", "repeat"] and doc["headline"]
    assert doc["terms"][0]["mentions"] == 1 and doc["terms"][0]["first"] == 1 and doc["terms"][0]["heard"] == "残差流"
    assert a.get("/media/abcdefghijk/sheets/0.jpg").headers["content-type"] == "image/jpeg"
    assert a.get("/media/abcdefghijk/sheets/..%2Ftimeline.json").status_code == 404
    assert doc["summary"]["sections"][0]["sentences"][0]["check"] == "unsupported"
    assert doc["transcript"][1] == {"t": 7, "e": 12, "text": "有害组一百二十八个问题", "en": "128 harmful questions"}
    assert doc["terms"][0]["term"] == "残差流" and doc["chapters"][1] == {"t": 20, "title": "方向"}
    assert [v["key"] for v in a.get("/api/me").json()["videos"]] == ["abcdefghijk"]
    assert b.get("/api/me").json()["videos"] == []
    assert b.get("/api/video/abcdefghijk").status_code == 404
    assert b.get("/media/abcdefghijk/at/1000").status_code == 404
    assert a.get("/media/abcdefghijk/at/1000").headers["content-type"] == "image/jpeg"  # cut from the sheet


def test_a_revoked_code_stops_working(home):
    c = _client(home)
    code = _join(c, home)
    assert c.get("/api/me").json()["in"] is True
    web.revoke(home, code)
    assert c.get("/api/me").json()["in"] is False


def test_new_videos_count_against_the_daily_limit_and_built_ones_dont(home):
    c = _client(home)
    _join(c, home, per_day=1)
    assert c.post("/api/open", json={"link": "abcdefghijk"}, headers=POST).status_code == 200  # already built
    assert c.post("/api/open", json={"link": "zyxwvutsrqp"}, headers=POST).status_code == 200  # new: 1 of 1
    r = c.post("/api/open", json={"link": "https://www.youtube.com/watch?v=qwertyuiopa"}, headers=POST)
    assert r.status_code == 429 and "limit" in r.json()["error"]
    assert c.post("/api/open", json={"link": "not a link"}, headers=POST).status_code == 400


def test_hosted_refuses_to_download_youtube_but_opens_what_is_built(home, started):
    c = _client(home, hosted=True)
    _join(c, home)
    r = c.post("/api/open", json={"link": "zyxwvutsrqp"}, headers=POST)
    assert r.status_code == 403 and "extension" in r.json()["error"]
    assert c.post("/api/open", json={"link": "abcdefghijk"}, headers=POST).status_code == 200
    assert started == []  # not even to finish a half-built one


def test_upload_keeps_the_file_under_its_hash_and_its_name_as_the_title(home, started):
    c = _client(home)
    _join(c, home)
    assert c.post("/api/upload", content=b"not a video", headers={**POST, "X-Name": "notes.txt"}).status_code == 400
    r = c.post("/api/upload", content=b"\x00\x01video bytes", headers={**POST, "X-Name": "My%20talk.mp4"})
    key = r.json()["key"]
    assert len(key) == 12 and (home / "uploads" / f"{key}.mp4").read_bytes() == b"\x00\x01video bytes"
    assert started == [(str(home / "uploads" / f"{key}.mp4"), "My talk")]
    assert c.post("/api/upload", content=b"\x00\x01video bytes", headers={**POST, "X-Name": "again.mp4"}).json() == {"key": key}
    assert c.post("/api/upload", content=b"", headers={**POST, "X-Name": "empty.mp4"}).status_code == 400


def test_ask_answers_with_frames_keeps_the_note_and_counts_the_question(home, monkeypatch):
    def answer(tl, q):
        return {"question": q, "verdict": "found", "moments": [{"i": 2, "t": 21, "p": 0.9, "text": "", "en": ""}],
                "answer": [{"text": "KL measures the gap.", "t": 21, "check": "supported", "note": ""}],
                "background": [], "seconds": 1.2, "cost_usd": 0.0, "asked": "now"}

    monkeypatch.setattr(study, "answer", answer)
    c = _client(home)
    _join(c, home, asks_per_day=1)
    c.post("/api/open", json={"link": "abcdefghijk"}, headers=POST)
    r = c.post("/api/ask", json={"key": "abcdefghijk", "q": "What is KL?"}, headers=POST).json()
    assert r["answer"][0]["text"] == "KL measures the gap." and len(r["frames"]) == 1
    assert c.get(r["frames"][0]["img"]).headers["content-type"] == "image/jpeg"
    assert c.get("/api/video/abcdefghijk").json()["notes"][0]["question"] == "What is KL?"
    assert c.post("/api/ask", json={"key": "abcdefghijk", "q": "Again?"}, headers=POST).status_code == 429
    other = _client(home)
    _join(other, home)
    other.post("/api/open", json={"link": "abcdefghijk"}, headers=POST)
    assert other.get("/api/video/abcdefghijk").json()["notes"] == []  # each code sees its own questions


def test_codes_read_the_same_however_they_are_typed():
    assert web.normal("abcd efgh") == web.normal("ABCD-EFGH") == web.normal("abcdefgh") == "ABCD-EFGH"
