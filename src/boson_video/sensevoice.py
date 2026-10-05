"""Speech to text anywhere (Windows, Linux, Intel Macs), through sherpa-onnx.

Used where Apple's transcriber isn't available. Two models, chosen by the speech language:
SenseVoice (int8) for Chinese, Cantonese, Japanese and Korean, and Parakeet TDT 0.6B v2 (int8)
for English, because SenseVoice garbles English (letters drop and Chinese numerals slip in:
"ABUT SXH 零" for "about 6,000", 2026-10-04). `BOSON_ASR=sensevoice|parakeet` forces one.

A voice detector (Silero) finds the stretches of speech, and the model transcribes each one as
soon as it is found, on several threads sharing one model; each stretch becomes one passage
with its own start and end. One stretch per thread beat batching them (2026-10-04, 200 s of
Mandarin on a 12-thread laptop: 2.4 s against 4.1 s), because a batch pads every stretch to
the longest. The models live in ~/.cache/boson-video/models (SenseVoice about 165 MB,
Parakeet about 480 MB, each downloaded once with the owner's approval).
"""

from __future__ import annotations

import os
import re
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from .timeline import Segment

MODELS = Path(os.environ.get("BOSON_MODELS", Path.home() / ".cache" / "boson-video" / "models"))
SENSEVOICE = MODELS / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09"
PARAKEET = MODELS / "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
VAD = MODELS / "silero_vad.onnx"
RATE = 16_000
LANGS = {"zh": "zh", "yue": "yue", "en": "en", "ja": "ja", "ko": "ko"}
_SHOUTED = re.compile(r"(?<![A-Za-z])[A-Z]{4,}(?:'[A-Z]+)?(?![A-Za-z])")  # SenseVoice writes English in capitals


class SenseVoiceError(RuntimeError):
    pass


def available() -> bool:
    return (SENSEVOICE / "model.int8.onnx").exists() and VAD.exists()


def model_for(locale: str | None) -> str:
    """"Parakeet" for English when it is installed, else "SenseVoice"."""
    forced = os.environ.get("BOSON_ASR", "").lower()
    if forced in ("sensevoice", "parakeet"):
        return "Parakeet" if forced == "parakeet" else "SenseVoice"
    english = (locale or "").lower().startswith("en")
    return "Parakeet" if english and (PARAKEET / "encoder.int8.onnx").exists() else "SenseVoice"


def _recognizer(name: str, locale: str | None):
    import sherpa_onnx

    if name == "Parakeet":
        return sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(PARAKEET / "encoder.int8.onnx"), decoder=str(PARAKEET / "decoder.int8.onnx"),
            joiner=str(PARAKEET / "joiner.int8.onnx"), tokens=str(PARAKEET / "tokens.txt"),
            num_threads=1, model_type="nemo_transducer")
    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(SENSEVOICE / "model.int8.onnx"),
        tokens=str(SENSEVOICE / "tokens.txt"),
        num_threads=1,
        language=LANGS.get((locale or "").split("_")[0], "auto"),
        use_itn=True,  # punctuation and digits ("三点二一" -> "3.21")
    )


def _read(wav: Path) -> np.ndarray:
    with wave.open(str(wav)) as w:
        if w.getframerate() != RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SenseVoiceError(f"{wav.name} must be 16 kHz mono 16-bit")
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def speech_stretches(samples: np.ndarray, max_len: float = 15.0):
    """Yield (start seconds, samples) for each stretch of speech, as the voice detector finds it."""
    import sherpa_onnx

    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = str(VAD)
    config.silero_vad.min_silence_duration = 0.35
    config.silero_vad.min_speech_duration = 0.25
    config.silero_vad.max_speech_duration = max_len
    config.sample_rate = RATE
    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=60)
    window = config.silero_vad.window_size  # it must be fed one window at a time

    def drain():
        while not vad.empty():
            yield vad.front.start / RATE, np.array(vad.front.samples, dtype=np.float32)
            vad.pop()

    for i in range(0, len(samples), window):
        vad.accept_waveform(samples[i:i + window])
        yield from drain()
    vad.flush()
    yield from drain()


def quiet_cuts(samples: np.ndarray, pieces: int, window: float = 5.0) -> list[int]:
    """Sample offsets splitting the audio into `pieces`, each moved to the quietest 0.2 s within
    `window` seconds, so the voice detector never sees a word cut in half."""
    edges = [0]
    hop = RATE // 5
    for k in range(1, pieces):
        target = len(samples) * k // pieces
        lo, hi = max(edges[-1] + hop, target - int(window * RATE)), min(len(samples) - hop, target + int(window * RATE))
        if hi <= lo:
            continue
        frames = samples[lo:hi - (hi - lo) % hop].reshape(-1, hop)
        edges.append(lo + int(np.argmin((frames ** 2).mean(axis=1))) * hop + hop // 2)
    return edges + [len(samples)]


def tidy(text: str) -> str:
    """English SenseVoice shouts in lower case: long words ("ASSISTANT"), and short ones beside a
    lower-case word ("refusal IN language" -> "refusal in language"). Short ones on their own
    (AI, MOE, KL) are usually acronyms and stay."""
    text = _SHOUTED.sub(lambda m: m.group(0).lower(), text)
    words = re.split(r"(\s+)", text)
    for i in range(0, len(words), 2):
        w = words[i]
        if re.fullmatch(r"[A-Z]{2,3}", w):
            near = [words[j] for j in (i - 2, i + 2) if 0 <= j < len(words)]
            if any(re.fullmatch(r"[a-z][a-z']+", x) for x in near):
                words[i] = w.lower()
    return "".join(words).strip()


def transcribe(wav: Path, locale: str | None = None, threads: int | None = None) -> tuple[list[Segment], dict]:
    """The whole recording -> passages, plus timings in ms (decoding overlaps voice detection)."""
    if not available():
        raise SenseVoiceError(f"SenseVoice isn't installed in {MODELS}")
    name = model_for(locale)
    clock = time.perf_counter()
    recognizer = _recognizer(name, locale)
    load_ms = (time.perf_counter() - clock) * 1000
    clean = tidy if name == "SenseVoice" else str.strip  # Parakeet already writes normal case

    def one(start: float, audio: np.ndarray) -> Segment:
        stream = recognizer.create_stream()
        stream.accept_waveform(RATE, audio)
        recognizer.decode_stream(stream)
        return Segment(round(start, 2), round(start + len(audio) / RATE, 2), clean(stream.result.text))

    samples = _read(wav)
    workers = threads or max(1, min(10, (os.cpu_count() or 4) - 2))
    # The voice detector releases the GIL, so pieces of a long recording are searched at once
    # (35 min: 9.7 s in one piece, 4.0 s in eight, 2026-10-04).
    edges = quiet_cuts(samples, max(1, min(8, len(samples) // (60 * RATE))))
    with ThreadPoolExecutor(workers) as pool, ThreadPoolExecutor(len(edges) - 1) as finders:

        def find(lo: int, hi: int):
            return [pool.submit(one, lo / RATE + start, audio) for start, audio in speech_stretches(samples[lo:hi])]

        jobs = [j for found in finders.map(find, edges[:-1], edges[1:]) for j in found]
        vad_ms = (time.perf_counter() - clock) * 1000 - load_ms
        segments = sorted((seg for seg in (j.result() for j in jobs) if seg.text), key=lambda s: s.start)
    total = (time.perf_counter() - clock) * 1000
    return segments, {"model load": round(load_ms, 1), "voice detection": round(vad_ms, 1),
                      "speech": round(total - load_ms - vad_ms, 1)}
