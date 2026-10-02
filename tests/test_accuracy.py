import random

from boson_video.accuracy import error_rate, units, vtt_text


def _slow_distance(a, b):
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
        prev = cur
    return prev[-1]


def test_error_rate_matches_textbook_levenshtein():
    rng = random.Random(1)
    for _ in range(200):
        a = [rng.choice("abcd") for _ in range(rng.randint(0, 12))]
        b = [rng.choice("abcd") for _ in range(rng.randint(0, 12))]
        if a:
            assert abs(error_rate(a, b) - _slow_distance(a, b) / len(a)) < 1e-9


def test_error_rate_cases():
    ref = "the cat sat on the mat".split()
    assert error_rate(ref, ref) == 0
    assert error_rate(ref, "the cat sat on mat".split()) == 1 / 6  # one deletion
    assert error_rate(ref, "the dog sat on the mat".split()) == 1 / 6  # one substitution
    assert error_rate([], []) == 0 and error_rate([], ["x"]) == 1


def test_units_mix_chinese_characters_and_english_words():
    assert units("今天做空了 Meta 的股票, price 740！") == ["今", "天", "做", "空", "了", "meta", "的", "股", "票", "price", "740"]
    assert units("[Applause] Thank you (laughs) 谢谢（笑声）") == ["thank", "you", "谢", "谢"]
    assert units("Don't stop") == ["don't", "stop"]


def test_vtt_text_drops_timings_tags_and_repeats():
    vtt = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000
<c>Hello</c> there

00:00:02.000 --> 00:00:04.000
Hello there

00:00:04.000 --> 00:00:06.000
general Kenobi
"""
    assert vtt_text(vtt) == "Hello there general Kenobi"
