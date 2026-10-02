"""The data every stage shares: a video, its frames, and the scenes cut from them."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Video:
    title: str
    channel: str
    duration: float  # seconds
    url: str  # watch URL, or a local file path
    id: str | None = None  # YouTube id; None for local files
    description: str = ""

    def link(self, t: float) -> str:
        """Where to send the viewer to watch second `t`."""
        if self.id:
            return f"https://www.youtube.com/watch?v={self.id}&t={int(t)}s"
        return f"{Path(self.url).resolve().as_uri()}#t={int(t)}"


@dataclass
class Chapter:
    start: float
    title: str


@dataclass
class HeatPoint:
    """One bucket of YouTube's "most replayed" graph."""

    start: float
    duration: float
    intensity: float  # 0..1


@dataclass
class CaptionTrack:
    lang: str
    kind: str  # "manual" or "asr" (auto-generated)
    name: str


@dataclass
class Sheet:
    """A JPEG holding a grid of frames: a YouTube storyboard sheet or our own mosaic."""

    jpeg: bytes
    width: int
    height: int


@dataclass
class Frame:
    index: int
    t: float  # seconds from the start
    sheet: int  # which Sheet holds this frame
    x: int
    y: int
    w: int
    h: int


@dataclass
class Scene:
    index: int
    start: float
    end: float
    frames: list[int]  # Frame indices in time order
    key: int  # the frame that best represents the scene
    look: int  # scenes with the same look resemble each other
    # "new": first time this look appears; "repeat": seen before;
    # "base": the look fills much of the video (host, podcast camera)
    kind: str = "new"
    changes: list[int] = field(default_factory=list)  # frames where the picture visibly changed

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Segment:
    """A stretch of speech: what was said between `start` and `end`."""

    start: float
    end: float
    text: str


@dataclass
class Timeline:
    video: Video
    frames: list[Frame]
    sheets: list[Sheet]
    scenes: list[Scene] = field(default_factory=list)
    chapters: list[Chapter] = field(default_factory=list)
    heat: list[HeatPoint] = field(default_factory=list)
    captions: list[CaptionTrack] = field(default_factory=list)
    language: str | None = None  # locale the speech was transcribed in, e.g. "zh_CN"
    transcript: list[Segment] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)  # milliseconds per stage

    def said_during(self, start: float, end: float) -> list[Segment]:
        """Segments whose middle falls in [start, end)."""
        return [s for s in self.transcript if start <= (s.start + s.end) / 2 < end]

    def to_json(self) -> dict:
        """Everything except the image bytes, for the stages that come next."""
        return {
            "video": asdict(self.video),
            "frames": [asdict(f) for f in self.frames],
            "scenes": [asdict(s) for s in self.scenes],
            "chapters": [asdict(c) for c in self.chapters],
            "heat": [asdict(h) for h in self.heat],
            "captions": [asdict(c) for c in self.captions],
            "language": self.language,
            "transcript": [asdict(s) for s in self.transcript],
            "sheets": [{"width": s.width, "height": s.height} for s in self.sheets],
            "timings_ms": self.timings,
        }
