"""Milestone 6 offline: the screen read into the document (subtitles kept apart, build steps
credited with what they add), and the plugin using it."""

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from boson_video import frames as frames_mod
from boson_video import library, ocr, plugin, screens
from boson_video.timeline import Frame, Scene, Screen, Segment, Sheet, Timeline, Video


def test_subtitles_are_kept_apart_from_what_the_picture_shows():
    w, h = 1280, 720
    lines = [
        [263, 81, 408, 125, "①还拒绝吗", 1.0],
        [991, 551, 1154, 601, "KL = 0.08", 0.98],
        [411, 653, 875, 692, "这个差距用一个叫做KL散度的公式来量化", 0.99],  # bottom, centred, words
        [60, 690, 140, 712, "148.0", 0.99],  # bottom but a number at the edge: a chart axis
        [600, 300, 610, 310, "x", 0.99],  # one character: noise
        [700, 300, 760, 320, "模糊", 0.3],  # low confidence
    ]
    shown, subtitles = screens.split_lines(lines, w, h)
    assert shown == ["①还拒绝吗", "KL = 0.08", "148.0"]
    assert subtitles == ["这个差距用一个叫做KL散度的公式来量化"]


def test_a_footer_is_not_a_subtitle_unless_it_is_being_said():
    said = "这个差距用一个叫做 K L 散多的公式来量化 so the coverage follows a power law"
    assert screens.spoken("这个差距用一个叫做KL散度的公式来量化", said)
    assert screens.spoken("the coverage follows a power law", said)
    assert not screens.spoken("RylanSchaeffer, JoshuaKazdan, JohnHughes, JordanJuravsky", said)
    assert not screens.spoken("Number of Samples (k)", said)
    assert not screens.spoken("number of samples", "as we scaled the number of samples")  # too short to tell


def _tl() -> Timeline:
    import io

    buf = io.BytesIO()
    Image.new("RGB", (32, 18), "gray").save(buf, "JPEG")
    frames = [Frame(i, i * 5.0, 0, 0, 0, 32, 18) for i in range(4)]
    scenes = [Scene(0, 0, 20, [0, 1, 2, 3], 0, 0, "new", [0, 1, 2])]
    tl = Timeline(video=Video("t", "c", 20, "u", "abcdefghijk"), frames=frames,
                  sheets=[Sheet(buf.getvalue(), 32, 18)], scenes=scenes)
    tl.language = "zh_CN"
    tl.transcript = [Segment(0.5, 4, "两个模型的差距"), Segment(5.5, 9, "用 KL 散度量化"), Segment(10.5, 14, "差距越大结果越大")]
    return tl


def test_a_build_step_is_credited_only_with_its_new_lines(tmp_path, monkeypatch):
    tl = _tl()
    reads = {0.0: ["下一个字的概率", "P普通模型"], 5.0: ["下一个字的概率", "P 普通模型", "KL = 0.08"], 10.0: ["下一个字的概率", "KL = 2.71"]}

    def fake_grab(tl_, where, times, labels, on_shot=None):
        shots = []
        for t in times:
            path = where / f"{int(t)}.jpg"
            path.write_bytes(b"x")
            shot = frames_mod.Shot(t, path, True, "")
            on_shot(shot)
            shots.append(shot)
        return shots

    class FakeReader:
        def __init__(self, threads=None):
            self.paths = []

        def submit(self, path):
            self.paths.append(path)

        def finish(self):
            return {str(p): {"w": 1280, "h": 720, "lines": [[100, 100 + 40 * k, 400, 130 + 40 * k, text, 0.99]
                                                            for k, text in enumerate(reads[float(Path(p).stem)])]}
                    for p in self.paths}

    monkeypatch.setattr(frames_mod, "grab", fake_grab)
    monkeypatch.setattr(ocr, "Reader", FakeReader)
    found, laps = screens.read(tl, tmp_path)
    assert [(s.t, s.text) for s in found] == [(0.0, "下一个字的概率\nP普通模型"), (5.0, "KL = 0.08"), (10.0, "KL = 2.71")]
    assert set(laps) == {"frames fetch", "screen text after fetch"}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(screens, "available", lambda: True)
    monkeypatch.setenv("BOSON_VIDEO_HOME", str(tmp_path))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    tl = _tl()
    tl.screens = [Screen(5.0, 0, "KL = 0.08", "用一个叫做KL散度的公式", "frames/5000.jpg"),
                  Screen(10.0, 0, "KL = 2.71", "", "frames/10000.jpg")]
    tl.timings["screens"] = 1.0
    library.save(tl, library.folder("abcdefghijk"))
    return tmp_path


def test_reading_search_and_checks_include_the_screen(home):
    text = plugin.read("abcdefghijk")
    assert "[0:05] ON SCREEN: KL = 0.08" in text and "[0:10] ON SCREEN: KL = 2.71" in text
    assert text.index("ON SCREEN: KL = 0.08") < text.index("用 KL 散度量化")  # in time order
    assert "KL散度的公式" not in text  # subtitles are the speech; they don't repeat in the reading
    assert "[0:10] ON SCREEN: KL = 2.71" in plugin.search("2.71")
    # a number shown only on screen can be confirmed
    ok = plugin.check("abcdefghijk", "The KL value for the broken model was 2.71", ["0:11"])
    assert "every number in the claim is in these passages" in ok and "[on screen] KL = 2.71" in ok
    briefing = plugin.briefing("abcdefghijk")
    assert "Screen text: read at 2 moments, 2 with text" in briefing and "subtitles at 1 of them" in briefing


def test_real_ocr_reads_a_drawn_slide(tmp_path):
    if not ocr.available():
        pytest.skip("RapidOCR isn't installed")
    im = Image.new("RGB", (1280, 720), "white")
    draw = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=56)
    draw.text((120, 120), "Refusal direction", fill="black", font=font)
    draw.text((120, 300), "KL = 0.08", fill="black", font=font)
    path = tmp_path / "slide.jpg"
    im.save(path, quality=95)
    rows = ocr.read([path])
    texts = [ln[4] for ln in rows[str(path)]["lines"]]
    assert any("Refusal" in t for t in texts) and any("0.08" in t for t in texts), texts
