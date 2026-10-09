"""What a stranger's computer needs, offline: the speech models fetched once on first use, the
ffmpeg and the JavaScript runtime that come with the package, and Apple's transcriber only where it
works."""

import io
import sys
import tarfile
from types import SimpleNamespace

import pytest

from boson_video import audio, local, pipeline, sensevoice, speech


@pytest.fixture
def models(tmp_path, monkeypatch):
    """An empty models folder, and downloads served from fake archives (counted)."""
    for name, value in {"MODELS": tmp_path, "SENSEVOICE": tmp_path / sensevoice.SENSEVOICE.name,
                        "PARAKEET": tmp_path / sensevoice.PARAKEET.name, "VAD": tmp_path / "silero_vad.onnx"}.items():
        monkeypatch.setattr(sensevoice, name, value)
    monkeypatch.delenv("BOSON_NO_DOWNLOAD", raising=False)
    monkeypatch.delenv("BOSON_ASR", raising=False)
    fetched = []

    def fake(url, dst):
        fetched.append(url.rsplit("/", 1)[-1])
        if url.endswith(".onnx"):
            dst.write_bytes(b"vad")
            return
        folder = url.rsplit("/", 1)[-1].removesuffix(".tar.bz2")
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:bz2") as tar:
            for f in ("model.int8.onnx", "encoder.int8.onnx", "tokens.txt"):
                info = tarfile.TarInfo(f"{folder}/{f}")
                info.size = 4
                tar.addfile(info, io.BytesIO(b"data"))
        dst.write_bytes(buf.getvalue())

    monkeypatch.setattr(sensevoice, "_download", fake)
    return SimpleNamespace(dir=tmp_path, fetched=fetched)


def test_the_model_a_video_needs_is_fetched_once(models):
    said = []
    sensevoice.ensure_models("zh_CN", said.append)
    assert (models.dir / sensevoice.SENSEVOICE.name / "model.int8.onnx").read_bytes() == b"data"
    assert models.fetched == [f"{sensevoice.SENSEVOICE.name}.tar.bz2", "silero_vad.onnx"]
    assert "about 166 MB, once" in said[0]
    sensevoice.ensure_models("zh_CN")
    assert len(models.fetched) == 2  # nothing again
    assert not list(models.dir.glob(".*"))  # no partial files left behind


def test_english_gets_parakeet_and_falls_back_to_sensevoice_without_downloads(models, monkeypatch):
    assert sensevoice.model_for("en_US") == "Parakeet"
    assert sensevoice.missing("en_US")[0] == (sensevoice.PARAKEET.name, 482)
    monkeypatch.setenv("BOSON_NO_DOWNLOAD", "1")
    assert sensevoice.model_for("en_US") == "SenseVoice"
    with pytest.raises(sensevoice.SenseVoiceError, match="boson-video models"):
        sensevoice.ensure_models("en_US")
    assert models.fetched == []


def test_the_bundled_ffmpeg_when_none_is_installed(monkeypatch):
    monkeypatch.setattr(local, "_installed", lambda: [None])
    path = local.ffmpeg()
    assert "imageio_ffmpeg" in path


def test_youtube_challenges_use_the_bundled_deno():
    flag, value = audio.js_runtimes()
    assert flag == "--js-runtimes" and value.startswith("deno:") and value.endswith(("deno", "deno.exe"))


def test_a_mac_without_apple_s_transcriber_uses_the_local_models(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")

    def no_xcode(locale):
        raise speech.SpeechError("swiftc not found; install Xcode's command line tools")

    monkeypatch.setattr(speech, "ensure", no_xcode)
    assert pipeline.apple_transcriber("zh_CN") is False
    monkeypatch.setattr(speech, "ensure", lambda locale: None)
    assert pipeline.apple_transcriber("zh_CN") is True
    monkeypatch.setenv("BOSON_ASR", "sensevoice")
    assert pipeline.apple_transcriber("zh_CN") is False
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("BOSON_ASR")
    assert pipeline.apple_transcriber("zh_CN") is False


def test_keys_are_found_where_an_installed_copy_looks(tmp_path, monkeypatch):
    """uvx runs the installed package, which has no repo .env: the folder you start in and
    ~/.boson-video/.env are read too, but only for this tool's keys."""
    from boson_video import env

    home, here = tmp_path / "home", tmp_path / "here"
    home.mkdir(), here.mkdir()
    (home / ".env").write_text("INCEPTION_API_KEY=from-home\nSOMEONE_ELSES=1\n")
    (here / ".env").write_text('TYPESAFE_API_KEY="from-here"\nINCEPTION_API_KEY=from-here\nAWS_SECRET=2\n')
    monkeypatch.setattr(env, "PROJECT_ENV", tmp_path / "no-repo" / ".env")
    monkeypatch.setenv("BOSON_VIDEO_HOME", str(home))
    monkeypatch.chdir(here)
    for key in ("INCEPTION_API_KEY", "TYPESAFE_API_KEY", "SOMEONE_ELSES", "AWS_SECRET"):
        monkeypatch.delenv(key, raising=False)
    assert len(env.missing()) == 2
    env.load_env()
    import os

    assert os.environ["TYPESAFE_API_KEY"] == "from-here"
    assert os.environ["INCEPTION_API_KEY"] == "from-here"  # the folder you start in comes first
    assert "SOMEONE_ELSES" not in os.environ and "AWS_SECRET" not in os.environ
    assert env.missing() == []


def test_a_build_without_the_writing_key_says_so(tmp_path, monkeypatch):
    import json

    from boson_video import jobs, library, pipeline, screens
    from boson_video.timeline import Segment

    from test_plugin import _tl

    def fake_build(ref, level=None):
        tl = _tl()
        tl.transcript, tl.translation, tl.terms, tl.summary = [], [], [], None
        return tl

    def fake_words(tl, where, locale=None, fresh_audio=False, say=None):
        tl.transcript = [Segment(1, 2, "你好")]

    monkeypatch.setattr(pipeline, "build", fake_build)
    monkeypatch.setattr(pipeline, "add_words", fake_words)
    monkeypatch.setattr(screens, "available", lambda: False)
    monkeypatch.delenv("INCEPTION_API_KEY", raising=False)
    jobs._build("abcdefghijk", "abcdefghijk", tmp_path, True)
    status = json.loads((library.folder("abcdefghijk", tmp_path) / "status.json").read_text())
    assert status["stage"] == "done" and "INCEPTION_API_KEY" in status["note"]
