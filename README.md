# Boson-Video

See what happens in a video, and when, in about a second, before any AI runs.

Give it a YouTube link (or a video file) and you get a page that lays the video out
as a timeline of scenes: every new visual and when it appears, which shots keep
coming back, the chapters, and YouTube's "most replayed" curve. It is the first
stage of a near-instant video summarizer: it tells the later stages where the
picture matters and where it's just a talking head.

```bash
uv sync
uv run boson-video "https://www.youtube.com/watch?v=zjkBMFhNj_g" --open
uv run boson-video ~/Movies/lecture.mp4
```

Each run writes `out/<video id>/index.html` (one self-contained file) and
`timeline.json` (frames, scenes, chapters, heatmap, captions list and timings, for
the stages that come next).

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

## What YouTube allows (checked 2026-09-24)

- **Captions:** the page lists the caption tracks, but downloading one from a
  script returns HTTP 200 with an empty body, because the real player sends a
  token. The tool shows which languages exist and doesn't download them.
- **Internal player API:** it answers in ~170 ms, but it refuses scripted clients
  ("UNPLAYABLE", "Sign in to confirm you're not a bot"), so the watch page is
  the dependable source.
- **Some videos have no captions at all**, like the 美股频道 video above. A
  summarizer that only reads transcripts has nothing to work with there.

## Where it's going

The goal is to read any video like a document: one page with a scrubbable ribbon, short
sections where every sentence links to its second, and an ask box. The agreed direction,
milestones and open decisions are in [docs/DIRECTION.md](docs/DIRECTION.md), and the
target screen is [docs/read-view.html](docs/read-view.html).

Next is milestone 2: Chinese and English transcripts made on the Mac with Apple's
on-device transcriber, lined up with the scenes.

## Tests

```bash
uv run pytest            # offline: parsing, sheet slicing, scenes on synthetic videos, the page, the ffmpeg path
uv run pytest -m live    # hits YouTube
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
