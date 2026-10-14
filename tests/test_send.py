"""boson-video send offline: the zip this computer makes, what the server accepts from it, and a hosted
server never fetching from YouTube (no network, no models)."""

import json
import zipfile

import pytest
from starlette.testclient import TestClient

from boson_video import audio, jobs, library, pipeline, send, web

from test_plugin import _sheet, _tl

POST = {"X-BV": "1"}


@pytest.fixture
def sound(tmp_path):
    path = tmp_path / "audio.m4a"
    path.write_bytes(b"\x00\x00\x00\x20ftypM4A sound")
    return path


@pytest.fixture
def bundle(tmp_path, sound):
    return send.pack(_tl(), sound, tmp_path / "send.zip", "en")


@pytest.fixture
def started(monkeypatch):
    calls = []
    monkeypatch.setattr(jobs, "start", lambda ref, root=None, words=True, title=None: calls.append(ref) or library.key(ref))
    return calls


@pytest.fixture
def home(tmp_path, monkeypatch, started):
    monkeypatch.delenv("BOSON_NO_YOUTUBE", raising=False)  # restored after the hosted app sets it
    root = tmp_path / "home"
    monkeypatch.setenv("BOSON_VIDEO_HOME", str(root))
    return root


def _rezip(src, dst, change=None, compress=zipfile.ZIP_STORED):
    """A copy of the zip at `src`, each part passed through `change(name, data)` (None drops it)."""
    with zipfile.ZipFile(src) as z, zipfile.ZipFile(dst, "w", compress) as out:
        for name in z.namelist():
            got = change(name, z.read(name)) if change else (name, z.read(name))
            if got:
                out.writestr(got[0], got[1])
    return dst


def test_the_zip_carries_only_the_scene_map_its_sheets_and_the_sound(bundle):
    with zipfile.ZipFile(bundle) as z:
        assert sorted(z.namelist()) == ["audio.lang", "audio.m4a", "sheets/0.jpg", "timeline.json"]
        assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())
        data = json.loads(z.read("timeline.json"))
    assert "transcript" not in data and "summary" not in data and data["video"]["id"] == "abcdefghijk"
    tl, sound, lang = send.receive(bundle, 10 * 2**20)
    assert (tl.video.id, len(tl.scenes), len(tl.frames), len(tl.sheets)) == ("abcdefghijk", 3, 4, 1)
    assert tl.video.url == "https://www.youtube.com/watch?v=abcdefghijk" and not tl.transcript
    assert (sound, lang) == ("audio.m4a", "en")
    send.extract(bundle, sound, bundle.with_name("kept.m4a"))
    assert bundle.with_name("kept.m4a").read_bytes() == b"\x00\x00\x00\x20ftypM4A sound"


@pytest.mark.parametrize("change, why", [
    (lambda n, d: (n, d) if n != "timeline.json" else None, "scene map is missing"),
    (lambda n, d: ("../evil.sh", d) if n == "audio.lang" else (n, d), "unexpected part"),
    (lambda n, d: (n, d) if n != "audio.m4a" else ("audio.exe", d), "one sound file"),
    (lambda n, d: (n, d) if n != "sheets/0.jpg" else (n, b"not a picture"), "isn't the picture"),
    (lambda n, d: (n, d.replace(b'"abcdefghijk"', b'null')) if n == "timeline.json" else (n, d), "doesn't read"),
    (lambda n, d: (n, d.replace(b'"duration": 40', b'"duration": 999999')) if n == "timeline.json" else (n, d), "impossible length"),
    (lambda n, d: (n, d.replace(b'"sheet": 0', b'"sheet": 7', 1)) if n == "timeline.json" else (n, d), "missing sheet"),
    (lambda n, d: (n, d.replace(b'"kind": "new"', b'"kind": "<script>"', 1)) if n == "timeline.json" else (n, d), "doesn't read"),
])
def test_the_server_refuses_anything_else(tmp_path, bundle, change, why):
    with pytest.raises(send.SendError, match=why):
        send.receive(_rezip(bundle, tmp_path / "bad.zip", change), 10 * 2**20)


def test_compressed_parts_and_oversize_are_refused(tmp_path, bundle):
    with pytest.raises(send.SendError, match="compressed"):
        send.receive(_rezip(bundle, tmp_path / "deflated.zip", compress=zipfile.ZIP_DEFLATED), 10 * 2**20)
    with pytest.raises(send.SendError, match="too large"):
        send.receive(bundle, 100)
    (tmp_path / "junk.zip").write_bytes(b"PK not a zip")
    with pytest.raises(send.SendError, match="isn't a file"):
        send.receive(tmp_path / "junk.zip", 10 * 2**20)


def test_a_sent_video_is_kept_and_built_on_the_server(home, bundle, started):
    c = TestClient(web.make_app(home, hosted=True))
    data = bundle.read_bytes()
    assert c.post("/api/send", content=data, headers=POST).status_code == 401
    code = web.make_invite(home)
    assert c.post("/api/join", json={"code": code}, headers=POST).status_code == 200
    assert c.post("/api/send", content=data).status_code == 403  # not from the page or the command
    r = c.post("/api/send", content=data, headers=POST)
    assert r.json() == {"key": "abcdefghijk"}
    where = home / "abcdefghijk"
    assert (where / "audio.m4a").read_bytes() == b"\x00\x00\x00\x20ftypM4A sound"
    assert (where / "audio.lang").read_text() == "en" and (where / "sheets/0.jpg").exists()
    assert library.load("abcdefghijk", home).video.title == "残差流是什么"
    assert started == ["https://www.youtube.com/watch?v=abcdefghijk"]
    assert c.get("/api/video/abcdefghijk").json()["video"]["yt"] == "abcdefghijk"
    assert not list((home / "uploads").glob(".send-*"))  # nothing half-received stays


def test_a_bad_send_keeps_nothing(home, tmp_path, bundle, started):
    c = TestClient(web.make_app(home, hosted=True))
    assert c.post("/api/join", json={"code": web.make_invite(home)}, headers=POST).status_code == 200
    bad = _rezip(bundle, tmp_path / "bad.zip", lambda n, d: (n, d) if n != "timeline.json" else None)
    r = c.post("/api/send", content=bad.read_bytes(), headers=POST)
    assert r.status_code == 400 and "scene map" in r.json()["error"]
    assert not (home / "abcdefghijk").exists() and not list((home / "uploads").glob(".send-*")) and started == []


def test_a_hosted_page_answers_a_link_with_the_command_to_send_it(home, started):
    c = TestClient(web.make_app(home, hosted=True))
    assert c.post("/api/join", json={"code": web.make_invite(home)}, headers=POST).status_code == 200
    r = c.post("/api/open", json={"link": "https://youtu.be/zyxwvutsrqp"}, headers=POST)
    assert r.status_code == 403
    assert r.json()["command"] == "uvx boson-video send zyxwvutsrqp --to http://testserver"
    assert started == []


def test_a_hosted_server_never_fetches_from_youtube(tmp_path, monkeypatch):
    monkeypatch.setenv("BOSON_NO_YOUTUBE", "1")
    monkeypatch.setattr(audio, "fetch_youtube", lambda *a, **k: pytest.fail("fetched from YouTube"))
    with pytest.raises(audio.AudioError, match="boson-video send"):
        pipeline.add_words(_tl(), tmp_path / "abcdefghijk")
    from boson_video import frames, screens

    monkeypatch.setattr(screens, "available", lambda: True)
    assert not jobs.reads_screens("abcdefghijk") and jobs.reads_screens(None)  # an upload's own file is fine
    with pytest.raises(RuntimeError, match="doesn't fetch"):
        frames._source(_tl(), tmp_path)


def test_a_restarted_server_resumes_sent_videos_and_not_bare_links(tmp_path, monkeypatch, sound):
    library.save(_tl(), tmp_path / "abcdefghijk")
    (tmp_path / "abcdefghijk/audio.m4a").write_bytes(sound.read_bytes())
    for name in ("abcdefghijk", "zyxwvutsrqp"):
        library.atomic_text(tmp_path / name / "job.json", json.dumps({"ref": f"https://youtu.be/{name}"}))
        jobs._write_status(tmp_path / name, stage="words")
    calls = []
    monkeypatch.setattr(jobs, "start", lambda ref, root, **kwargs: calls.append(ref))
    assert jobs.resume(tmp_path, hosted=True) == 1
    assert calls == ["https://youtu.be/abcdefghijk"]


def test_the_command_says_where_to_send(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BOSON_VIDEO_HOME", str(tmp_path))
    monkeypatch.delenv("BOSON_SERVER", raising=False)
    assert send.main(["abcdefghijk"]) == 2
    assert "--to" in capsys.readouterr().err


def test_a_video_sent_twice_asks_youtube_once(tmp_path, monkeypatch, sound):
    monkeypatch.setenv("BOSON_VIDEO_HOME", str(tmp_path / "home"))
    fetched = []

    def fetch(vid, folder, fresh=False):
        fetched.append(vid)
        (folder / "audio.m4a").write_bytes(sound.read_bytes())
        (folder / "audio.lang").write_text("en")
        return folder / "audio.m4a"

    monkeypatch.setattr(pipeline, "build", lambda link: _tl())
    monkeypatch.setattr(audio, "fetch_youtube", fetch)
    for _ in range(2):  # a retry, or the same video to another site
        tl, got, lang = send.prepare("https://youtu.be/abcdefghijk", say=lambda text: None)
        assert (tl.video.id, got.read_bytes(), lang, len(tl.sheets)) == ("abcdefghijk", sound.read_bytes(), "en", 1)
    assert fetched == ["abcdefghijk"]
