"""The speech track: cutting audio at pauses, transcribing pieces, lining words up with scenes."""

import json
import subprocess
import wave
from pathlib import Path

import pytest

from boson_video import audio, speech
from boson_video.local import LocalVideoError, ffmpeg
from boson_video.timeline import Segment, Timeline, Video


def test_plan_pieces_moves_seams_to_nearby_pauses():
    pauses = [(24.0, 26.0), (48.0, 52.0), (74.0, 76.0)]
    assert audio.plan_pieces(100, pauses, 4) == [(0.0, 25.0), (25.0, 50.0), (50.0, 75.0), (75.0, 100)]
    assert audio.plan_pieces(100, [], 2) == [(0.0, 50.0), (50.0, 100)]  # no pause near: even split
    assert audio.plan_pieces(100, [(90.0, 91.0)], 2) == [(0.0, 50.0), (50.0, 100)]  # too far away
    assert audio.plan_pieces(42, pauses, 1) == [(0.0, 42)]


def test_piece_count_keeps_workers_busy_without_tiny_pieces():
    assert audio.piece_count(1493) == 8
    assert audio.piece_count(300) == 3
    assert audio.piece_count(60) == 1


def _tone_wav(path: Path, seconds: float, rate: int = 16_000) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x01\x00" * int(seconds * rate))


def test_cut_writes_pieces_with_their_offsets(tmp_path):
    src = tmp_path / "a.wav"
    _tone_wav(src, 3.0)
    pieces = audio.cut(src, [(0.0, 1.0), (1.0, 3.0)], tmp_path)
    assert [off for _, off in pieces] == [0.0, 1.0]
    assert [round(audio.duration(p), 3) for p, _ in pieces] == [1.0, 2.0]


def _has_ffmpeg() -> bool:
    try:
        ffmpeg()
        return True
    except LocalVideoError:
        return False


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not installed")
def test_to_wav_and_silences_find_the_pause(tmp_path):
    src = tmp_path / "tone-gap-tone.m4a"
    subprocess.run(
        [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=1",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5",
         "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[a]", "-map", "[a]", str(src)],
        check=True,
    )
    wav = audio.to_wav(src, tmp_path / "out.wav")
    with wave.open(str(wav)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16_000, 1, 2)
    assert 3.9 < audio.duration(wav) < 4.2
    (start, end), = audio.silences(wav)
    assert 1.3 < start < 1.7 and 2.3 < end < 2.7


def test_guess_locale_and_names():
    assert speech.guess_locale("Muse 是否能让 Meta 在 AI 上咸鱼翻身？") == "zh_CN"
    assert speech.guess_locale("[1hr Talk] Intro to Large Language Models") == "en_US"
    found = speech.names("Money or Life 美股频道 on GPT-5, NVDA and SpaceX. https://x.com/a?b=1 code SHKN00019&x A")
    assert found == ["Money or Life", "GPT-5", "NVDA", "SpaceX"]


def test_transcribe_shifts_piece_times_and_sorts(monkeypatch, tmp_path):
    outputs = {
        "p0.wav": [{"start": 0.5, "end": 4.0, "text": "first"}, {"start": 5.0, "end": 9.0, "text": ""}],
        "p1.wav": [{"start": 1.0, "end": 3.5, "text": "second"}],
    }

    def fake_run(cmd, capture_output, text):
        lines = "\n".join(json.dumps(d) for d in outputs[Path(cmd[2]).name])
        return subprocess.CompletedProcess(cmd, 0, stdout=lines, stderr="")

    monkeypatch.setattr(speech, "tool", lambda: tmp_path / "bv-speech")
    monkeypatch.setattr(speech.subprocess, "run", fake_run)
    got = speech.transcribe([(tmp_path / "p1.wav", 60.0), (tmp_path / "p0.wav", 0.0)], "en_US")
    assert got == [Segment(0.5, 4.0, "first"), Segment(61.0, 63.5, "second")]  # empty text dropped


def test_said_during_uses_each_segments_middle():
    tl = Timeline(video=Video("t", "c", 30, "u", "abcdefghijk"), frames=[], sheets=[],
                  transcript=[Segment(0, 4, "a"), Segment(8, 14, "b"), Segment(20, 30, "c")])
    assert [s.text for s in tl.said_during(0, 10)] == ["a"]  # b's middle (11 s) is in the next scene
    assert [s.text for s in tl.said_during(10, 30)] == ["b", "c"]
