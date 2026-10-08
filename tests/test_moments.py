"""The moment: words, a picture code, and a frame, built from scenes and screens."""

import io

from PIL import Image

from boson_video.moments import build
from boson_video.timeline import Frame, Scene, Screen, Segment, Sheet, Timeline, Video


def _video(scenes, frames, screens, segments, duration=20):
    buf = io.BytesIO()
    Image.new("RGB", (32, 18), "gray").save(buf, "JPEG")
    tl = Timeline(video=Video("t", "c", duration, "u", "abcdefghijk"), frames=frames,
                  sheets=[Sheet(buf.getvalue(), 32, 18)], scenes=scenes)
    tl.transcript = segments
    tl.screens = screens
    return tl


def test_a_build_is_a_state_then_deltas_each_with_its_frame():
    frames = [Frame(i, i * 5.0, 0, 0, 0, 32, 18) for i in range(4)]
    scenes = [Scene(0, 0, 20, [0, 1, 2, 3], 0, 0, "new", [0, 1, 2])]
    screens = [Screen(0.0, 0, "下一个字的概率\nP普通模型", "", "frames/0.jpg"),
               Screen(5.0, 0, "KL = 0.08", "", "frames/5000.jpg"),
               Screen(10.0, 0, "KL = 2.71", "", "frames/10000.jpg")]
    segments = [Segment(0.5, 4, "两个模型的差距"), Segment(5.5, 9, "用 KL 散度量化"), Segment(10.5, 14, "差距越大结果越大")]
    found = build(_video(scenes, frames, screens, segments))
    assert [(m.code, m.text, m.image) for m in found] == [
        ("state", "下一个字的概率\nP普通模型", "frames/0.jpg"),
        ("delta", "KL = 0.08", "frames/5000.jpg"),
        ("delta", "KL = 2.71", "frames/10000.jpg"),
    ]
    assert found[0].passages == [0] and found[1].passages == [1] and found[2].passages == [2]
    assert found[0].end == found[1].start == 5.0 and found[-1].end == 20.0


def test_a_held_shot_is_one_state_and_an_unread_step_is_not_a_seek_yet():
    frames = [Frame(i, t, 0, 0, 0, 32, 18) for i, t in enumerate((0.0, 30.0, 31.0))]
    scenes = [Scene(0, 0, 30, [0], 0, 0, "base", [0]),
              Scene(1, 30, 40, [1, 2], 1, 1, "new", [1, 2])]
    screens = [Screen(31.0, 1, "only the second step was read", "", "frames/31000.jpg")]
    segments = [Segment(2, 8, "the host talks"), Segment(32, 36, "then a diagram")]
    tl = _video(scenes, frames, screens, segments, duration=40)
    found = build(tl)
    assert [(m.start, m.code) for m in found] == [(0.0, "state"), (30.0, "state"), (31.0, "delta")]
    assert found[0].passages == [0] and found[2].passages == [1]
    assert found[0].text == "" and found[2].text == "only the second step was read"
    # once the screen has been read, a step with no frame at all is a gap: watch it
    tl.timings["screens"] = 1.0
    assert [m.code for m in build(tl)] == ["state", "seek", "delta"]


def test_a_frame_on_disk_belongs_to_its_moment_even_without_text(tmp_path):
    frames = [Frame(i, t, 0, 0, 0, 32, 18) for i, t in enumerate((0.0, 5.0))]
    scenes = [Scene(0, 0, 10, [0, 1], 0, 0, "new", [0, 1])]
    tl = _video(scenes, frames, [], [], duration=10)
    tl.timings["screens"] = 1.0
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "5000.jpg").write_bytes(b"jpeg")  # OCR found nothing: a photo, a face
    found = build(tl, tmp_path)
    assert [(m.code, m.image) for m in found] == [("seek", ""), ("delta", "frames/5000.jpg")]


def test_a_picture_that_changes_on_every_sample_is_a_trajectory():
    frames = [Frame(i, float(i), 0, 0, 0, 32, 18) for i in range(4)]
    scenes = [Scene(0, 0, 4, [0, 1, 2, 3], 0, 0, "new", [0, 1, 2, 3])]
    screens = [Screen(float(i), 0, f"f{i}", "", f"frames/{i}.jpg") for i in range(4)]
    found = build(_video(scenes, frames, screens, [], duration=4))
    assert [m.code for m in found] == ["trajectory"] * 4


def test_a_speaker_moving_is_not_a_trajectory():
    """Every 10 s sample of a lecturer at a podium differs, but nothing on screen changes: no text."""
    frames = [Frame(i, i * 10.0, 0, 0, 0, 32, 18) for i in range(5)]
    scenes = [Scene(0, 0, 50, [0, 1, 2, 3, 4], 0, 0, "new", [0, 1, 2, 3, 4])]
    found = build(_video(scenes, frames, [], [], duration=50))
    assert [m.code for m in found] == ["state", "delta", "delta", "delta", "delta"]
