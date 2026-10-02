# Boson-Video

Read any video like a document. Give it a YouTube link (or a video file) and you get
a page that lays the video out as scenes in about a second (every new visual and when
it appears, which shots keep coming back, the chapters, YouTube's "most replayed"
curve), then fills in every word that was said, transcribed on your Mac, each passage
linked to its second.

```bash
uv sync
uv run boson-video "https://www.youtube.com/watch?v=zjkBMFhNj_g" --open
uv run boson-video ~/Movies/lecture.mp4
uv run boson-video 9JKT5rBbrwM --lang zh_CN     # speech language; guessed from the title otherwise
uv run boson-video 9JKT5rBbrwM --no-words       # scenes only
```

Each run writes `out/<video id>/index.html` (one self-contained file) and
`timeline.json` (frames, scenes, chapters, heatmap, transcript and timings, for the
stages that come next). The page is written twice: with the scenes, then with the words.
The words need macOS 26 and Xcode's command line tools (Apple's on-device transcriber
is built on first use).

## Measured

MacBook on a home connection, 2026-09-24, one run each (the YouTube page time
varies between runs, 0.4 to 1.2 s so far):

| Video | Length | Frames | Result | Page | Thumbnails | Decode | Scenes | Total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Money or Life 美股频道, "Muse 是否能让 Meta 在 AI 上咸鱼翻身？" | 24:53 | 151 | 3 scenes, one shot fills 97% | 0.93 s | 0.15 s | 0.12 s | 0.05 s | **1.26 s** |
| Andrej Karpathy, "Intro to Large Language Models" | 59:48 | 360 | 59 distinct slides, 21 chapters | 1.14 s | 0.15 s | 0.11 s | 0.16 s | **1.56 s** |
| Rick Astley, "Never Gonna Give You Up" | 3:33 | 108 | 87 shots, fast cutting | 0.48 s | 0.13 s | 0.07 s | 0.04 s | **0.73 s** |

Most of the time is YouTube building the watch page. In a browser extension that
page is already loaded, so the same result would take about 0.3 s.

### Words (2026-10-02, M5 MacBook)

| Video | Length | Language | Words ready | Download · prep · speech | Error rate against human captions |
| --- | --- | --- | --- | --- | --- |
| Money or Life 美股频道 (talking head) | 24:53 | Chinese | **13.8 s** (6.9 s with audio cached) | 4.6 · 1.5 · 6.0 s | no captions exist; Chinese is good, English names come out garbled |
| Andrej Karpathy, "Intro to Large Language Models" | 59:48 | English | **30.5 s** | 7.3 · 3.5 · 18.5 s | only automatic captions exist |
| Ken Robinson, "Do schools kill creativity?" (TED) | 20:06 | English | **9.9 s** | 2.8 · 1.1 · 5.1 s | **10.0% of words**; about half are filler words ("you know" alone: 38) that the human captions leave out |
| 陳永儀, TEDxTaipei | 14:29 | Chinese | **7.1 s** | 2.9 · 0.8 · 2.3 s | **5.3% of characters**; mostly look-alikes (裡/裏, 制/製) and sound-alikes (地/的) |

Speech runs at about 200× real time when the audio is cut into 8 pieces transcribed at
once (80× in one stream). "Words ready" counts from the start of the run. Scores come
from `scripts/accuracy.py`.

## How it works

1. **One page request.** The watch page holds the title, duration, caption tracks,
   chapters, the most-replayed heatmap and the *storyboard spec*.
2. **Storyboards.** These are the thumbnails YouTube shows when you hover over the
   seek bar, already rendered for every video: 320×180, one every 2 s (short
   videos) to 10 s (long ones), nine to a JPEG sheet. A one-hour video is 40
   sheets (~1 MB), fetched in parallel over one HTTP/2 connection that was opened
   while the page was still loading.
3. **Scenes, without a model** ([scenes.py](src/boson_video/scenes.py)). The frames are
   2 to 10 s apart, so motion can't be seen, only its result. The main signal is
   the *still-pixel change*. First the tool learns which pixels normally stay
   put in this particular video, then it asks what fraction of them clearly
   changed. A host's gestures or a speaker's webcam box sit in pixels that always
   move, so they don't count. A new slide rewrites pixels that never move, so it
   does. Scenes that look alike share a *look*. A look that fills most of the
   video, or keeps coming back, is the *base shot* (the host, the podcast camera).
4. **Page.** Frames are drawn straight from the sheets with CSS offsets: nothing
   is re-encoded, and the file works offline.

Local files take the same path. ffmpeg decodes only keyframes (`-skip_frame nokey`),
keeps one frame every 2 s or more, and packs them into sheets of its own.

5. **Words.** yt-dlp downloads only a low-bitrate audio track (about 9 MB for 25
   minutes). ffmpeg turns it into 16 kHz mono and finds the pauses; the audio is cut at
   pauses into up to 8 pieces, and Apple's on-device transcriber (SpeechAnalyzer, run by
   a small Swift tool, [bv_speech.swift](src/boson_video/bv_speech.swift)) transcribes
   them all at once. Each passage lands in the scene row it was said in.

## What YouTube allows (checked 2026-09-24 and 2026-10-02)

- **Captions:** the page lists the caption tracks, but downloading one from a
  script returns HTTP 200 with an empty body, because the real player sends a
  token. The tool shows which languages exist and doesn't download them.
- **Internal player API:** it answers in ~170 ms, but it refuses scripted clients
  ("UNPLAYABLE", "Sign in to confirm you're not a bot"), so the watch page is
  the dependable source.
- **Some videos have no captions at all**, like the 美股频道 video above. A
  summarizer that only reads transcripts has nothing to work with there.
- **Audio downloads vary.** The same 9 MB took 4 s when YouTube offered a plain audio
  file and 18 s when it only offered streaming segments, and a request was sometimes
  refused (so the download retries once). Starting speech-to-text while the audio is
  still arriving is the planned fix.

## Where it's going

The goal is to read any video like a document: one page with a scrubbable ribbon, short
sections where every sentence links to its second, and an ask box. The agreed direction,
milestones and open decisions are in [docs/DIRECTION.md](docs/DIRECTION.md), and the
target screen is [docs/read-view.html](docs/read-view.html).

Milestones 1 (scenes) and 2 (words) are done. Next is milestone 3, the read view:
short sections written in the video's language, each sentence checked against the
transcript, plus the ask box.

## Tests

```bash
uv run pytest            # offline: parsing, sheet slicing, scenes and audio cutting on synthetic media, the page, scoring
uv run pytest -m live    # hits YouTube and runs Apple's transcriber
uv run python scripts/accuracy.py snZ811wvjjw zh-TW zh_TW   # score a transcript against human captions
```

## Limits

- This is a personal research prototype. YouTube's terms don't allow automated
  access for products, which is one more reason the extension is the plan for
  anything shared.
- Storyboard frames are small. They show *what's on screen and when*, not small
  text. That is what the full-resolution step is for.
- Live streams aren't supported. Private and age-restricted videos fail with
  YouTube's own reason.
- For local files, frames follow the encoder's keyframes, which can be 8 s or more
  apart in some files.
- English names inside Chinese speech come out garbled ("Money or Life" became
  "Monelife"). Apple's transcriber ignored hint words, so the summary writer gets the
  names from the title and description instead (`speech.names`).
