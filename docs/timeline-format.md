# timeline.json, version 1

The document Boson-Video makes from a video: what was said, what was shown, and where. One
file per video, UTF-8 JSON, written by `library.save` and read by `Timeline.from_json`. Other
tools may read it; this page is the contract.

**Versioning.** `version` changes when a field changes meaning or goes away; added fields keep
the version, so readers ignore what they don't know. A reader refuses a version newer than it
knows.

**Times** are seconds from the start of the video (floats). **Indices** point into the arrays
of the same file: a passage index into `transcript`, a frame index into `frames`.

| Field | Type | Meaning |
| --- | --- | --- |
| `format` | `"boson-video.timeline"` | Identifies the file |
| `version` | `1` | See above |
| `video` | object | `title`, `channel`, `duration` (s), `url` (watch URL or file path), `id` (YouTube id, or null for a file), `description` |
| `frames` | array | Thumbnails, in time order: `index`, `t`, `sheet` (which image in `sheets/`), `x`, `y`, `w`, `h` (the frame's box in that sheet) |
| `sheets` | array | Size of each thumbnail sheet: `width`, `height`. The images are `sheets/<n>.jpg` next to this file |
| `scenes` | array | `index`, `start`, `end`, `frames` (frame indices), `key` (the frame that best shows it), `look` (scenes with the same look show the same picture), `kind` (`new`: first time this picture appears; `repeat`: seen before; `base`: the shot the video keeps returning to, such as the host), `changes` (frames where the picture visibly changed, such as slide builds; the first is the scene's start) |
| `chapters` | array | The video's own chapters: `start`, `title` |
| `heat` | array | YouTube's "most replayed" curve: `start`, `duration`, `intensity` (0 to 1) |
| `captions` | array | Caption tracks YouTube lists (not downloaded): `lang`, `kind` (`manual` or `asr`), `name` |
| `language` | string or null | The locale the speech was transcribed in, such as `zh_CN` or `en_US` |
| `transcript` | array | Passages in time order: `start`, `end`, `text`. Machine-made |
| `transcriber` | string | `Apple SpeechAnalyzer`, `SenseVoice` (Chinese and other non-English speech off the Mac) or `Parakeet` (English off the Mac) |
| `translation` | array of strings | English for each passage, same length and order as `transcript`; empty when not made |
| `terms` | array | Technical terms: `heard` (as written in the transcript), `term` (written correctly), `en`, `reading` (pinyin for Chinese), `explain` (general background, not from the video), `said` (a sentence, below), `mentions` (passage indices) |
| `questions` | array of strings | Questions a learner might ask, in English |
| `screens` | array | What was shown, read by OCR at each new visual and build step: `t`, `scene`, `text` (the lines new on screen at that moment, top to bottom; all of them on a scene's first frame), `subtitles` (burned-in captions, kept apart because they are the speech written out), `image` (the frame, relative to this folder). Machine-read |
| `moments` | array | The unit the page and the plugin cite. One span: `start`, `end`, `code` (`state`: the picture holds; `delta`: lines added on a build; `trajectory`: the picture changed on every sample; `seek`: open the original range), `scene`, `t` (the frame's time), `passages` (transcript indices whose middle falls in the span), `text` (lines new at `t`), `image` (the frame, relative to this folder). Built from scenes, transcript, and screens |
| `summary` | object or null | `tldr` (sentences), `sections` (`title`, `title_en`, `start`, `end`, `sentences`), `writer` (the model), `checker` (`jev+code`, `code`, or `jev` in files from before 2026-10-04) |
| `timings_ms` | object | Milliseconds per stage, as measured on the machine that built it |

**A sentence** is `text` (the video's language), `text_en` (English; empty if the video is in
English), `evidence` (passage indices it rests on), `check` (`supported`, `contradicted`,
`unsupported`, `uncited`, or empty when not checked), `check_p` (the checker's probability),
`check_note` (why code flagged it, such as a number not found).

A `✓` (`supported`) means the sentence matches what the transcript says. The transcript is
machine-made, so it is not a guarantee that the sentence is true.

Files next to `timeline.json` (not part of the contract, but stable): `index.html` (the page),
`frames/<ms>.jpg` (full-resolution frames fetched so far), `status.json` (a build in progress),
`notes.json` (questions asked in the page).
