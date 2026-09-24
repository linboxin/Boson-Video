"""Scene detection on synthetic videos whose right answer is known."""

import numpy as np

from boson_video.scenes import detect, profile
from boson_video.timeline import Frame

H, W = 180, 320
rng = np.random.default_rng(7)


def _frames(n: int, gap: float) -> list[Frame]:
    return [Frame(i, i * gap, 0, 0, 0, W, H) for i in range(n)]


def _slide(line: int, bullets: int = 0) -> np.ndarray:
    """A white slide: the same title bar, one text line whose height depends on `line`,
    and optionally some bullets below it (a slide being built up)."""
    img = np.full((H, W, 3), 248, np.uint8)
    img[16:30, 40:170] = 40
    y = 44 + 26 * line
    img[y : y + 12, 40:220] = 30
    for b in range(bullets):
        img[100 + 22 * b : 112 + 22 * b, 60:200] = 30
    return img


def _with_webcam(img: np.ndarray) -> np.ndarray:
    """A speaker box in the corner whose content changes on every frame."""
    out = img.copy()
    out[128:176, 250:316] = rng.integers(0, 256, (48, 66, 3), dtype=np.uint8)
    return out


def _host(dx: int, dy: int, arm: int) -> np.ndarray:
    """A person in front of a wall: the body shifts and an arm moves between samples."""
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = np.linspace(90, 150, W, dtype=np.uint8)[None, :, None]  # the wall
    img[:, :, 1] += 20
    cx, cy = 160 + dx, 100 + dy
    img[cy - 50 : cy + 80, cx - 35 : cx + 35] = (200, 150, 120)  # body
    img[cy - 20 + arm : cy - 8 + arm, cx + 35 : cx + 75] = (210, 160, 130)  # arm
    return img


def _chart() -> np.ndarray:
    img = np.full((H, W, 3), (20, 24, 40), np.uint8)
    for i, h in enumerate((40, 90, 60, 130, 110)):
        img[170 - h : 170, 40 + 50 * i : 80 + 50 * i] = (60, 200, 120)
    return img


def test_slides_with_a_moving_webcam_box():
    seq = [0] * 5 + [1] * 8 + [2] * 8 + [3] * 6 + [0] * 3  # the first slide comes back at the end
    pixels = [_with_webcam(_slide(k)) for k in seq]
    scenes = detect(_frames(len(seq), 10), pixels, duration=300)
    assert [s.frames[0] for s in scenes] == [0, 5, 13, 21, 27]
    assert [s.kind for s in scenes] == ["new", "new", "new", "new", "repeat"]
    assert scenes[-1].look == scenes[0].look
    assert len({s.look for s in scenes[:4]}) == 4


def test_isolated_bullet_is_a_cut_but_a_run_of_builds_is_one_scene():
    pixels = [_slide(0)] * 4 + [_slide(1)] * 3 + [_slide(1, bullets=1)] * 3
    scenes = detect(_frames(10, 10), pixels, duration=100)
    assert [s.frames[0] for s in scenes] == [0, 4, 7]  # a bullet out of nowhere is new information

    pixels = [_slide(0)] * 4 + [_slide(1)] * 3 + [_slide(1, bullets=b) for b in (1, 2, 3)]
    scenes = detect(_frames(10, 10), pixels, duration=100)
    assert [s.frames[0] for s in scenes] == [0, 4]  # steady building reads as one scene...
    assert scenes[1].changes == [4, 7, 8, 9]  # ...with every build kept as a step


def test_talking_head_with_a_chart_cutaway():
    pixels = [_host(int(rng.integers(-6, 7)), int(rng.integers(-4, 5)), int(rng.integers(0, 40))) for _ in range(20)]
    pixels += [_chart()] * 4
    pixels += [_host(int(rng.integers(-6, 7)), int(rng.integers(-4, 5)), int(rng.integers(0, 40))) for _ in range(16)]
    scenes = detect(_frames(40, 10), pixels, duration=400)
    assert [s.frames[0] for s in scenes] == [0, 20, 24]
    assert [s.kind for s in scenes] == ["base", "new", "base"]
    assert scenes[0].look == scenes[2].look
    text, stats = profile(scenes, 400)
    assert stats["base_share"] == 0.9 and text.startswith("One shot fills 90%")


def test_fast_cutting_music_video():
    palette = [(230, 30, 30), (30, 200, 60), (40, 60, 230), (240, 220, 40), (20, 20, 20), (240, 240, 240)]
    pixels = []
    for i in range(40):
        img = np.full((H, W, 3), palette[i % len(palette)], np.uint8)
        img[60:120, 100 + (i * 7) % 60 : 180 + (i * 7) % 60] = palette[(i + 3) % len(palette)]
        pixels.append(img)
    scenes = detect(_frames(40, 2), pixels, duration=80)
    assert len(scenes) == 40
    text, stats = profile(scenes, 80)
    assert stats["median_scene_s"] == 2 and text.startswith("Fast cutting")
    assert sum(s.kind == "repeat" for s in scenes) > 0  # the palette comes round again


def test_long_distinct_shots_are_not_base_shots():
    pixels = [_slide(0)] * 4 + [_chart()] * 3 + [_host(0, 0, 10)] * 3  # 40% / 30% / 30%
    scenes = detect(_frames(10, 10), pixels, duration=100)
    assert [s.kind for s in scenes] == ["new", "new", "new"]
    assert profile(scenes, 100)[0] == "3 distinct visuals: the picture carries information."


def test_two_alternating_cameras_are_both_base():
    a, b = _host(0, 0, 10), _chart()  # stand-ins for two podcast camera angles
    pixels = ([a] * 3 + [b] * 3) * 3
    scenes = detect(_frames(18, 10), pixels, duration=180)
    assert {s.kind for s in scenes} == {"base"}
    assert profile(scenes, 180)[0].startswith("2 recurring shots fill 100%")


def test_single_frame_and_empty():
    one = detect(_frames(1, 10), [_slide(0)], duration=5)
    assert len(one) == 1 and one[0].frames == [0] and one[0].changes == [0]
    assert detect([], [], duration=0) == []


def test_scene_times_cover_the_video():
    seq = [0] * 3 + [1] * 3
    scenes = detect(_frames(6, 10), [_slide(k) for k in seq], duration=57)
    assert scenes[0].start == 0 and scenes[-1].end == 57
    assert all(a.end == b.start for a, b in zip(scenes, scenes[1:]))
