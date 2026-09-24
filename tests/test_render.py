import io
import re

from PIL import Image

from boson_video.render import render
from boson_video.timeline import Chapter, Frame, HeatPoint, Scene, Sheet, Timeline, Video


def _timeline(n_scenes: int = 3, gap: float = 10.0) -> Timeline:
    buf = io.BytesIO()
    Image.new("RGB", (96, 54), (200, 30, 30)).save(buf, "JPEG")
    sheet = Sheet(buf.getvalue(), 96, 54)
    frames = [Frame(i, i * gap, 0, (i % 3) * 32, (i // 3 % 3) * 18, 32, 18) for i in range(n_scenes * 2)]
    kinds = ["new", "base", "repeat"]
    scenes = [
        Scene(k, 2 * k * gap, 2 * (k + 1) * gap, [2 * k, 2 * k + 1], 2 * k, look=k % 2, kind=kinds[k % 3],
              changes=[2 * k, 2 * k + 1])
        for k in range(n_scenes)
    ]
    video = Video(title='Talk <b>"quotes"</b>', channel="Chan & Co", duration=2 * n_scenes * gap, url="u", id="abcdefghijk")
    return Timeline(
        video=video, frames=frames, sheets=[sheet], scenes=scenes,
        chapters=[Chapter(0, "Intro"), Chapter(20, "Middle part")],
        heat=[HeatPoint(0, 30, 0.2), HeatPoint(30, 30, 1.0)],
        timings={"page": 700.0, "thumbnails": 150.0, "scenes": 40.0, "total": 950.0},
    )


def test_page_is_self_contained_and_escaped():
    page = render(_timeline())
    assert page.startswith("<!doctype html>")
    assert "Talk &lt;b&gt;&quot;quotes&quot;&lt;/b&gt;" in page and "<b>" not in page
    assert "Chan &amp; Co" in page
    assert "data:image/jpeg;base64," in page
    assert "<script" not in page and "http://" not in page.replace("http://www.w3.org", "")
    assert "Ready in 0.95 s" in page


def test_scene_rows_link_to_their_moment():
    page = render(_timeline())
    assert 'id="s0"' in page and 'id="s2"' in page
    assert "https://www.youtube.com/watch?v=abcdefghijk&amp;t=20s" in page
    assert re.search(r'<h2 class="chapter">Intro</h2>.*<h2 class="chapter">Middle part</h2>', page, re.S)
    assert "Base shot" in page and 'Same picture as <a href="#s0">' in page
    assert "<polyline" in page  # the most-replayed line


def test_fast_cutting_switches_to_a_grid():
    assert 'class="scenes dense"' in render(_timeline(n_scenes=36, gap=1.0))
    assert 'class="scenes"' in render(_timeline(n_scenes=3))
