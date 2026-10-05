"""Speech to text on the Mac with Apple's on-device transcriber (SpeechAnalyzer, macOS 26+).

`bv_speech.swift` is compiled on first use and cached per version of its source.
Several pieces of audio are transcribed at once, one process each.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .timeline import Segment

SOURCE = Path(__file__).with_name("bv_speech.swift")
CACHE = Path.home() / "Library" / "Caches" / "boson-video"
_CJK = re.compile(r"[\u3400-\u9fff]")
# Names the video writes itself: capitalised Latin words, joined by "or/of/the" into names like
# "Money or Life", as written in the title, channel and description ("SpaceX", "NVDA", "GPT-5").
_NAME = re.compile(r"[A-Z][A-Za-z0-9.&'-]*(?:\s+(?:or|of|the)\s+[A-Z][A-Za-z0-9.&'-]*)*")
_URLISH = re.compile(r"\S*(?:https?://|www\.|[/?&=@#])\S*")  # links, invite codes, handles
MAX_NAMES = 60


class SpeechError(RuntimeError):
    pass


def tool() -> Path:
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()[:12]
    binary = CACHE / f"bv-speech-{digest}"
    if binary.exists():
        return binary
    swiftc = shutil.which("swiftc")
    if not swiftc:
        raise SpeechError("swiftc not found; install Xcode's command line tools (xcode-select --install)")
    CACHE.mkdir(parents=True, exist_ok=True)
    done = subprocess.run([swiftc, "-O", "-parse-as-library", "-o", str(binary), str(SOURCE)],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise SpeechError(f"could not build the speech tool: {done.stderr.strip()[-500:]}")
    return binary


def locales() -> dict[str, list[str]]:
    done = subprocess.run([str(tool()), "locales"], capture_output=True, text=True)
    if done.returncode != 0:
        raise SpeechError(done.stderr.strip() or "speech tool failed")
    return json.loads(done.stdout)


def ensure(locale: str) -> None:
    """Make sure the model for `locale` is on the Mac (macOS downloads it if needed)."""
    known = locales()
    if locale in known["installed"]:
        return
    if locale not in known["supported"]:
        raise SpeechError(f"Apple's transcriber doesn't support {locale}")
    done = subprocess.run([str(tool()), "install", locale], stderr=sys.stderr, stdout=subprocess.PIPE, text=True)
    if done.returncode != 0:
        raise SpeechError(f"could not install the {locale} speech model")


def guess_locale(*texts: str) -> str:
    """Chinese if the title or description is written in Chinese, else English."""
    return "zh_CN" if any(_CJK.search(t or "") for t in texts) else "en_US"


def names(*texts: str) -> list[str]:
    """Names the speaker is likely to say, from the video's own title, channel and description.

    Apple's transcriber ignores hint words (AnalysisContext.contextualStrings had no effect
    on a Mandarin video, 2026-10-02), so names like "Money or Life" come out garbled. This
    list goes to the summary writer instead, which can spell them right.
    """
    seen: dict[str, None] = {}
    for text in texts:
        for m in _NAME.finditer(_URLISH.sub(" ", text or "")):
            name = m.group(0).strip(" .-'&")
            digits = sum(c.isdigit() for c in name)
            if not 2 <= len(name) <= 30 or (digits and (digits > 3 or len(name) > 8)):
                continue  # too short, too long, or a code / order number rather than a name
            seen.setdefault(name)
    return list(seen)[:MAX_NAMES]


def title_terms(title: str) -> list[str]:
    """Lower-case Latin words in a title written in Chinese: "llm abliteration是什么？" names a
    term the writer otherwise spells "obliteration" (2026-10-04). Capitalised ones are already
    names; in an English title every word is plain English, so none count."""
    if not _CJK.search(title or ""):
        return []
    return list(dict.fromkeys(re.findall(r"(?<![A-Za-z])[a-z][a-z0-9+-]{3,}(?![A-Za-z])", _URLISH.sub(" ", title))))


def transcribe(pieces: list[tuple[Path, float]], locale: str) -> list[Segment]:
    """Transcribe all pieces at once; times are shifted back onto the whole recording."""
    binary = tool()

    def one(piece: tuple[Path, float]) -> list[Segment]:
        path, offset = piece
        done = subprocess.run([str(binary), "transcribe", str(path), locale], capture_output=True, text=True)
        if done.returncode != 0:
            raise SpeechError(f"transcription failed on {path.name}: {done.stderr.strip()[-300:]}")
        return [
            Segment(round(d["start"] + offset, 2), round(d["end"] + offset, 2), d["text"])
            for d in map(json.loads, done.stdout.splitlines())
            if d.get("text")
        ]

    with ThreadPoolExecutor(max_workers=max(1, len(pieces))) as pool:
        parts = list(pool.map(one, pieces))
    return sorted((s for part in parts for s in part), key=lambda s: s.start)
