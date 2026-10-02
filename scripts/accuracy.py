"""Score our transcript against a video's human-made captions.

    uv run python scripts/accuracy.py <video id> <caption language> <speech locale>
    uv run python scripts/accuracy.py iG9CE55wbtY en en_US
    uv run python scripts/accuracy.py snZ811wvjjw zh-TW zh_TW

Writes out/<id>/ (page, timeline.json, captions) and prints the error rate:
words for English, characters for Chinese (an English word inside Chinese counts once).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from boson_video.accuracy import error_rate, units, vtt_text
from boson_video.cli import _write
from boson_video.pipeline import add_words, build


def human_captions(video_id: str, lang: str, folder: Path) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"captions.{lang}.vtt"
    if not target.exists():
        cmd = [sys.executable, "-m", "yt_dlp", "--js-runtimes", "node", "--skip-download", "--write-subs",
               "--sub-langs", lang, "--sub-format", "vtt", "-o", str(folder / "captions"), "--quiet",
               "--no-warnings", f"https://www.youtube.com/watch?v={video_id}"]
        subprocess.run(cmd, check=True)
    if not target.exists():
        raise SystemExit(f"no human {lang} captions downloaded for {video_id}")
    return vtt_text(target.read_text(encoding="utf-8"))


def main() -> None:
    video_id, lang, locale = sys.argv[1:4]
    folder = Path("out") / video_id
    reference = units(human_captions(video_id, lang, folder))
    started = time.perf_counter()
    tl = build(video_id)
    add_words(tl, folder, locale)
    _write(tl, folder)
    took = time.perf_counter() - started
    hypothesis = units(" ".join(s.text for s in tl.transcript))
    rate = error_rate(reference, hypothesis)
    unit = "characters" if locale.startswith(("zh", "yue")) else "words"
    print(f"{tl.video.title} ({tl.video.duration / 60:.1f} min, {locale})")
    print(f"human captions: {len(reference)} units · ours: {len(hypothesis)} units · error rate over {unit}: {rate:.1%}")
    print(f"page with words in {took:.1f} s ({' · '.join(f'{k} {v / 1000:.2f} s' for k, v in tl.timings.items())})")


if __name__ == "__main__":
    main()
