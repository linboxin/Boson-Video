import io
import re

from PIL import Image

from boson_video.render import render
from boson_video.timeline import Chapter, Frame, HeatPoint, Scene, Segment, Sheet, Timeline, Video


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


def test_words_sit_in_their_scene_rows():
    tl = _timeline()
    tl.language = "zh_CN"
    tl.transcript = [Segment(1, 5, "大家好 <b>"), Segment(21, 25, "第二段")]
    page = render(tl)
    assert '<div class="said" lang="zh-CN">' in page
    assert "大家好 &lt;b&gt;" in page and "第二段" in page
    first_row = page[page.index('id="s0"'): page.index('id="s1"')]
    assert "大家好" in first_row and "第二段" not in first_row
    assert "words: 2 passages in Chinese, transcribed on this Mac" in page
    assert "and its audio, transcribed on this Mac" in page


def test_fast_cutting_puts_the_words_after_the_grid():
    tl = _timeline(n_scenes=36, gap=1.0)
    tl.language = "en_US"
    tl.transcript = [Segment(0, 3, "hello there")]
    page = render(tl)
    assert "What&#x27;s said" in page or "What's said" in page
    assert page.count("hello there") == 1
