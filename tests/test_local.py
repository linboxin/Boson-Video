import subprocess

import pytest

from boson_video import local
from boson_video.pipeline import from_file

try:
    FFMPEG = local.ffmpeg()
except local.LocalVideoError:
    FFMPEG = None

pytestmark = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not installed")


@pytest.fixture(scope="module")
def three_shots(tmp_path_factory):
    """18 s of video: 6 s red, 6 s of a test card, 6 s blue, a keyframe every second."""
    path = tmp_path_factory.mktemp("video") / "three shots.mp4"
    src = [f"color=c={c}:s=320x180:d=6:r=25" for c in ("red", "blue")]
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", src[0],
        "-f", "lavfi", "-i", "testsrc2=s=320x180:d=6:r=25",
        "-f", "lavfi", "-i", src[1],
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]",
        "-c:v", "libx264", "-g", "25", "-pix_fmt", "yuv420p", str(path),
    ]
    subprocess.run(cmd, check=True)
    return path


def test_local_file_becomes_frames_and_scenes(three_shots):
    tl = from_file(str(three_shots))
    assert tl.video.title == "three shots" and tl.video.id is None
    assert 17.5 < tl.video.duration < 18.5
    times = [f.t for f in tl.frames]
    assert times == sorted(times) and len(times) == 9  # one frame every 2 s
    assert all(b - a >= 1.99 for a, b in zip(times, times[1:]))
    starts = [s.start for s in tl.scenes]
    assert starts[0] == 0 and any(5 <= t <= 7 for t in starts) and any(11 <= t <= 13 for t in starts)
    assert tl.video.link(12).endswith("three%20shots.mp4#t=12")
    assert tl.sheets[0].jpeg[:2] == b"\xff\xd8"


def test_missing_file_is_a_clear_error(tmp_path):
    with pytest.raises(local.LocalVideoError, match="no such file"):
        local.load(str(tmp_path / "nope.mp4"))
