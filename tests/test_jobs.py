"""Hosted jobs survive a restart and limit simultaneous engine runs; no network or models."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from boson_video import jobs, library


@pytest.fixture
def queue(monkeypatch):
    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(jobs, "_pool", pool)
    monkeypatch.setattr(jobs, "_running", {})
    yield
    pool.shutdown(wait=True)


def test_jobs_queue_and_keep_inputs_for_recovery(tmp_path, monkeypatch, queue):
    entered, release = threading.Event(), threading.Event()
    seen = []

    def build(ref, name, root, words, title):
        seen.append(name)
        entered.set()
        assert release.wait(3)
        jobs._write_status(root / name, stage="done")

    monkeypatch.setattr(jobs, "_build", build)
    jobs.start("abcdefghijk", tmp_path, words=False)
    try:
        assert entered.wait(2)
        jobs.start("zyxwvutsrqp", tmp_path, words=False)
        assert seen == ["abcdefghijk"]
        assert jobs.status("zyxwvutsrqp", tmp_path)["stage"] == "queued"
        assert jobs.running("zyxwvutsrqp", tmp_path)
        assert not jobs.running("zyxwvutsrqp", tmp_path / "another-home")
        assert json.loads((tmp_path / "zyxwvutsrqp/job.json").read_text())["ref"] == "zyxwvutsrqp"
        jobs.start("abcdefghijk", tmp_path, words=False)  # same job is not enqueued twice
    finally:
        release.set()
    assert jobs.wait("zyxwvutsrqp", 3, tmp_path)["stage"] == "done"
    assert seen == ["abcdefghijk", "zyxwvutsrqp"]


def test_hosted_recovery_only_resumes_unfinished_uploads(tmp_path, monkeypatch):
    upload = tmp_path / "uploads" / "123456abcdef.mp4"
    upload.parent.mkdir()
    upload.write_bytes(b"test")
    for name, ref, stage in [(upload.stem, str(upload), "words"),
                             ("abcdefghijk", "https://youtu.be/abcdefghijk", "scenes"),
                             ("failed", "failed", "error"), ("done", "done", "done")]:
        library.atomic_text(tmp_path / name / "job.json", json.dumps({"ref": ref, "title": "My video"}))
        jobs._write_status(tmp_path / name, stage=stage)
    calls = []
    monkeypatch.setattr(jobs, "start", lambda ref, root, **kwargs: calls.append((ref, kwargs)))
    assert jobs.resume(tmp_path, hosted=True) == 1
    assert calls == [(str(upload), {"words": True, "title": "My video"})]


def test_completed_silent_video_does_not_retranscribe(tmp_path, monkeypatch):
    from boson_video import llm, screens
    from test_plugin import _tl

    tl = _tl(None)
    tl.transcript = []
    tl.translation, tl.terms = [], []
    tl.timings.update({"words total": 12, "screens": 3})
    library.save(tl, tmp_path / "silent")
    monkeypatch.setattr(screens, "available", lambda: True)
    monkeypatch.setattr(llm, "configured", lambda: True)
    assert jobs._complete("silent", tmp_path)


def test_atomic_save_preserves_previous_document_on_failure(tmp_path, monkeypatch):
    from pathlib import Path

    document = tmp_path / "timeline.json"
    document.write_text('{"old": true}')

    def fail_replace(self, target):
        raise OSError("disk failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        library.atomic_text(document, '{"new": true}')
    assert json.loads(document.read_text()) == {"old": True}
    assert list(tmp_path.iterdir()) == [document]
