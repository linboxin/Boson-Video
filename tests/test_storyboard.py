import io

import numpy as np
from PIL import Image

from boson_video.storyboard import cut_frames
from boson_video.youtube import StoryboardLevel

W, H = 32, 18


def _sheet(values: list[int], cols: int = 3, rows: int = 3) -> bytes:
    """A sheet whose cells are flat grey at the given levels, row by row."""
    img = Image.new("RGB", (cols * W, rows * H), (0, 0, 0))
    for i, v in enumerate(values):
        img.paste((v, v, v), ((i % cols) * W, (i // cols) * H, (i % cols + 1) * W, (i // cols + 1) * H))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    return buf.getvalue()


def test_cut_frames_positions_times_and_pixels():
    level = StoryboardLevel(3, W, H, count=11, cols=3, rows=3, interval_ms=10_000, url_template="$M")
    values = [20 * i for i in range(11)]
    sheets_jpeg = [_sheet(values[:9]), _sheet(values[9:], rows=1)]  # the last sheet is short
    sheets, frames, pixels = cut_frames(level, sheets_jpeg, duration=103)

    assert len(sheets) == 2 and (sheets[1].width, sheets[1].height) == (3 * W, H)
    assert len(frames) == len(pixels) == 11
    assert [f.t for f in frames[:3]] == [0, 10, 20]
    assert frames[10].t == 100
    f4 = frames[4]
    assert (f4.sheet, f4.x, f4.y, f4.w, f4.h) == (0, W, H, W, H)
    assert (frames[9].sheet, frames[9].x, frames[9].y) == (1, 0, 0)
    for k, p in enumerate(pixels):
        assert p.shape == (H, W, 3)
        assert abs(float(p.mean()) - values[k]) < 3  # JPEG is close, not exact


def test_cut_frames_drops_frames_clamped_to_the_end():
    level = StoryboardLevel(3, W, H, count=9, cols=3, rows=3, interval_ms=10_000, url_template="$M")
    _, frames, _ = cut_frames(level, [_sheet([0] * 9)], duration=61)
    assert [f.t for f in frames] == [0, 10, 20, 30, 40, 50, 60, 60.5]
