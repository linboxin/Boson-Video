"""Reading text in images, locally: RapidOCR (PP-OCR models for Chinese and English, on
onnxruntime; about 15 MB, bundled with the package).

OCR runs in a worker process, never in the process that transcribes: sherpa-onnx brings its own
onnxruntime library, and two in one process can clash (a different copy in System32 already
broke it once, 2026-10-04). One worker reading frames as they arrive beat several reading in
parallel on a 12-thread laptop (94 frames: 42 s with one, 53 s with three, 75 s with six), so a
`Reader` takes paths while the frames are still being fetched and hands back what it read.

    python -m boson_video.ocr [--threads N] image.jpg ...   # one JSON line per image
    python -m boson_video.ocr [--threads N] --stdin         # paths on stdin, as they come
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
from pathlib import Path


def available() -> bool:
    return importlib.util.find_spec("rapidocr_onnxruntime") is not None


class Reader:
    """A worker that reads images as they are handed to it; `finish()` returns everything it read:
    {path: {"w", "h", "lines": [[x0, y0, x1, y1, text, score], ...]}}."""

    def __init__(self, threads: int | None = None):
        n = str(threads or max(1, (os.cpu_count() or 4) // 2))
        # OpenCV and numpy's maths libraries otherwise start a thread per core of their own.
        env = {**os.environ, "PYTHONIOENCODING": "utf-8",
               **{k: n for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}}
        self._proc = subprocess.Popen([sys.executable, "-m", "boson_video.ocr", "--threads", n, "--stdin"],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True, encoding="utf-8", errors="replace", env=env)
        self._lock = threading.Lock()
        self._results: dict[str, dict] = {}
        # Read as it writes, or a full pipe would stall the worker.
        self._reader = threading.Thread(target=self._collect, daemon=True)
        self._reader.start()

    def _collect(self) -> None:
        for line in self._proc.stdout:
            if line.startswith("{"):
                row = json.loads(line)
                self._results[row["path"]] = row

    def submit(self, path: Path) -> None:
        with self._lock:
            self._proc.stdin.write(f"{path}\n")
            self._proc.stdin.flush()

    def finish(self, timeout: float = 600) -> dict[str, dict]:
        self._proc.stdin.close()
        self._proc.wait(timeout=timeout)
        self._reader.join(timeout=5)
        if self._proc.returncode != 0:
            raise RuntimeError(f"OCR worker failed: {self._proc.stderr.read().strip()[-300:]}")
        return self._results


def read(paths: list[Path], threads: int | None = None) -> dict[str, dict]:
    """Read a batch of images in one worker."""
    reader = Reader(threads)
    for p in paths:
        reader.submit(p)
    return reader.finish()


def _read_one(engine, path: str) -> dict:
    from PIL import Image

    with Image.open(path) as im:
        w, h = im.size
    result, _ = engine(path, use_cls=False)  # slides and charts are upright
    lines = []
    for box, text, score in result or []:
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        lines.append([round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys)), text, round(float(score), 3)])
    return {"path": path, "w": w, "h": h, "lines": lines}


def _main(args: list[str]) -> None:
    import logging

    threads = -1
    if args[:1] == ["--threads"]:
        threads, args = int(args[1]), args[2:]
    logging.disable(logging.WARNING)
    sys.stdout.reconfigure(encoding="utf-8")
    if threads > 0:
        import cv2

        cv2.setNumThreads(threads)
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR(**({f"{m}_intra_op_num_threads": threads for m in ("det", "cls", "rec")} if threads > 0 else {}))
    paths = (line.strip() for line in sys.stdin) if args[:1] == ["--stdin"] else iter(args)
    for path in paths:
        if path:
            print(json.dumps(_read_one(engine, path), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    _main(sys.argv[1:])
