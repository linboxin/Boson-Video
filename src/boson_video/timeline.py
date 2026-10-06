"""The data every stage shares: a video, its frames, and the scenes cut from them."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

FORMAT = "boson-video.timeline"
VERSION = 1  # bump when a field changes meaning or goes away; adding fields keeps the version


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
class Sentence:
    """One sentence of the read view, resting on transcript passages."""

    text: str  # in the video's language
    text_en: str  # English version; empty when the video is in English
    evidence: list[int]  # indices into Timeline.transcript
    check: str = ""  # "supported" | "contradicted" | "unsupported" | "uncited"; "" = not checked
    check_p: float = 0.0  # Jev's probability for that verdict
    check_note: str = ""  # why a sentence failed, when code (not Jev) found the reason


@dataclass
class Section:
    title: str
    title_en: str
    start: float
    end: float
    sentences: list[Sentence]


@dataclass
class Summary:
    tldr: list[Sentence]
    sections: list[Section]
    writer: str  # the model that wrote it
    checker: str = ""  # the model that checked it

    def sentences(self) -> list[Sentence]:
        return self.tldr + [s for sec in self.sections for s in sec.sentences]


@dataclass
class Term:
    """A technical term a learner may not know, as the video uses it."""

    heard: str  # exactly as it appears in the transcript (speech recognition may garble it)
    term: str  # written correctly, as the video means it (e.g. 残差流, or "embedding")
    en: str  # in English
    reading: str  # pinyin for Chinese terms; empty otherwise
    explain: str  # plain-English background for a non-expert; general knowledge, not from the video
    said: Sentence  # what the video says about it, citing the passages (checked like the summary)
    mentions: list[int] = field(default_factory=list)  # passages that contain `heard`


@dataclass
class Screen:
    """What one full-resolution frame shows, read by OCR (screens.py)."""

    t: float
    scene: int
    text: str  # lines new on screen at this moment (all of them on a scene's first frame), top to bottom
    subtitles: str = ""  # burned-in captions at the bottom: the speech written out, kept apart
    image: str = ""  # the frame, relative to the video's folder (frames/<ms>.jpg)


@dataclass
class Moment:
    """One span the page and the plugin cite: the words, the picture's code, and the frame.

    `code` is state (the picture holds), delta (new lines on a build), trajectory (the motion
    is the content), or seek (open the original range; the frame could not be read).
    """

    start: float
    end: float
    code: str
    scene: int
    t: float  # the frame that represents this span
    passages: list[int] = field(default_factory=list)  # indices into Timeline.transcript
    text: str = ""  # lines new at t; empty when the picture held and showed nothing new
    image: str = ""  # full-resolution frame, relative to the video's folder


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
    transcriber: str = ""  # "Apple SpeechAnalyzer", "SenseVoice" or "Parakeet"
    translation: list[str] = field(default_factory=list)  # English for each transcript passage
    terms: list[Term] = field(default_factory=list)  # the glossary, in order of first mention
    questions: list[str] = field(default_factory=list)  # questions a learner might ask, in English
    screens: list[Screen] = field(default_factory=list)  # what was shown, read at the new visuals
    moments: list[Moment] = field(default_factory=list)  # words joined to a picture code and a frame
    summary: Summary | None = None
    timings: dict[str, float] = field(default_factory=dict)  # milliseconds per stage

    def said_during(self, start: float, end: float) -> list[Segment]:
        """Segments whose middle falls in [start, end)."""
        return [s for s in self.transcript if start <= (s.start + s.end) / 2 < end]

    def to_json(self) -> dict:
        """Everything except the image bytes, for the stages that come next (docs/timeline-format.md)."""
        return {
            "format": FORMAT,
            "version": VERSION,
            "video": asdict(self.video),
            "frames": [asdict(f) for f in self.frames],
            "scenes": [asdict(s) for s in self.scenes],
            "chapters": [asdict(c) for c in self.chapters],
            "heat": [asdict(h) for h in self.heat],
            "captions": [asdict(c) for c in self.captions],
            "language": self.language,
            "transcript": [asdict(s) for s in self.transcript],
            "transcriber": self.transcriber,
            "translation": self.translation,
            "terms": [asdict(t) for t in self.terms],
            "questions": self.questions,
            "screens": [asdict(s) for s in self.screens],
            "moments": [asdict(m) for m in self.moments],
            "summary": asdict(self.summary) if self.summary else None,
            "sheets": [{"width": s.width, "height": s.height} for s in self.sheets],
            "timings_ms": self.timings,
        }

    @classmethod
    def from_json(cls, data: dict, sheets: list[Sheet] | None = None) -> "Timeline":
        """The inverse of to_json; the sheets' image bytes travel separately (library.py)."""
        if data.get("version", 1) > VERSION:
            raise ValueError(f"timeline.json version {data['version']} is newer than this boson-video ({VERSION})")

        def sentence(d: dict) -> Sentence:
            return Sentence(**d)

        summary = None
        if data.get("summary"):
            s = data["summary"]
            summary = Summary(
                tldr=[sentence(x) for x in s["tldr"]],
                sections=[Section(**{**sec, "sentences": [sentence(x) for x in sec["sentences"]]}) for sec in s["sections"]],
                writer=s.get("writer", ""), checker=s.get("checker", ""),
            )
        return cls(
            video=Video(**data["video"]),
            frames=[Frame(**f) for f in data.get("frames", [])],
            sheets=sheets or [],
            scenes=[Scene(**s) for s in data.get("scenes", [])],
            chapters=[Chapter(**c) for c in data.get("chapters", [])],
            heat=[HeatPoint(**h) for h in data.get("heat", [])],
            captions=[CaptionTrack(**c) for c in data.get("captions", [])],
            language=data.get("language"),
            transcript=[Segment(**s) for s in data.get("transcript", [])],
            transcriber=data.get("transcriber", ""),
            translation=data.get("translation", []),
            terms=[Term(**{**t, "said": sentence(t["said"])}) for t in data.get("terms", [])],
            questions=data.get("questions", []),
            screens=[Screen(**s) for s in data.get("screens", [])],
            moments=[Moment(**m) for m in data.get("moments", [])],
            summary=summary,
            timings=data.get("timings_ms", {}),
        )
