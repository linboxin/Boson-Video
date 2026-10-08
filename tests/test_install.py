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
