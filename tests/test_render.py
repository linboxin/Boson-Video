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
    assert "http://" not in page.replace("http://www.w3.org", "")
    assert "scenes ready in 0.95 s" in page
    assert "const DATA = " in page and 'id="rib"' in page


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
    assert "its audio transcribed on this Mac" in page


def test_fast_cutting_leaves_the_words_to_the_transcript():
    tl = _timeline(n_scenes=36, gap=1.0)
    tl.language = "en_US"
    tl.transcript = [Segment(0, 3, "hello there")]
    page = render(tl)
    html_part = page.split("<script>")[0]  # the words also travel in the page data for the ribbon and search
    assert html_part.count("hello there") == 1
    assert 'id="p0"' in html_part  # in the transcript tab, not under the grid


def test_summary_sentences_link_check_and_switch_language():
    from boson_video.timeline import Section, Sentence, Summary

    tl = _timeline()
    tl.language = "zh_CN"
    tl.transcript = [Segment(1, 5, "做空了 Meta"), Segment(21, 25, "买入 Grab")]
    tl.summary = Summary(
        tldr=[Sentence("博主做空 Meta。", "He shorted Meta.", [0], "supported", 0.97)],
        sections=[Section("操作", "Trades", 0, 30, [
            Sentence("买入 Grab。", "Bought Grab.", [1], "unsupported", 0.61),
            Sentence("没有出处。", "", [], "uncited", 1.0),
        ])],
        writer="mercury-2.5", checker="jev",
    )
    page = render(tl)
    assert 'data-lang="en"' in page and "中文" in page
    assert '<span class="t-en" lang="en">He shorted Meta.</span>' in page
    assert "watch?v=abcdefghijk&amp;t=21s" in page  # the sentence links to its passage
    assert 'class="mark ok"' in page and 'class="mark warn"' in page
    assert "1 of 3 sentences checked" in page
    assert 'id="q"' in page  # search over what was said


def test_transcript_reads_side_by_side_with_terms_glossed():
    from boson_video.timeline import Sentence, Term

    tl = _timeline()
    tl.language = "zh_CN"
    tl.transcriber = "SenseVoice"
    tl.transcript = [Segment(1, 5, "先通过 ibedding 转化"), Segment(21, 25, "每一层残差流 <b>"), Segment(26, 28, "残差流又来了")]
    tl.translation = ["First through the embedding", "Each layer's residual stream", "The residual stream again"]
    tl.terms = [
        Term("ibedding", "embedding", "embedding", "", "Turns tokens into vectors.", Sentence("", "", []), [0]),
        Term("残差流", "残差流", "residual stream", "cánchā liú", "The model's running state.",
             Sentence("每层都写入残差流。", "Every layer writes to it.", [1], "supported", 0.9), [1, 2]),
    ]
    tl.questions = ["What is the residual stream?"]
    page = render(tl)
    html_part = page.split("<script>")[0]
    assert 'class="lang-both"' in html_part and 'data-lang="both"' in html_part
    assert '<p class="t-en" lang="en">Each layer&#x27;s residual stream</p>' in html_part
    assert '每一层<ruby class="term" data-k="1"' in html_part and "<rt>residual stream</rt>" in html_part
    assert "&lt;b&gt;" in html_part and "<b>" not in html_part
    # a garbled English term is glossed with its real spelling
    assert ">ibedding<rt>embedding</rt></ruby>" in html_part
    assert 'id="term-1"' in html_part and "cánchā liú" in html_part and "said 2×" in html_part
    assert "What is the residual stream?" in html_part and 'id="ask-form"' in html_part
    assert "transcribed on this computer by SenseVoice" in html_part
