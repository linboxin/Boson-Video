# Boson-Video: guide for coding agents

Read any video like a document. **Read [docs/DIRECTION.md](docs/DIRECTION.md) first.** It
holds the agreed direction, the milestones, who does what, and the owner's open
decisions. The target screen is [docs/read-view.html](docs/read-view.html); open it in a
browser.

## Commands

- `uv sync` once, then `uv run boson-video <youtube link | id | file> [--open] [--no-words] [--lang zh_CN] [-o out]`
- `uv run pytest` (offline) · `uv run pytest -m live` (hits YouTube, runs Apple's transcriber)
- `uv run python scripts/accuracy.py <video id> <caption language> <locale>`: score our transcript against human captions

## Map

- `src/boson_video/youtube.py`: watch page → video, storyboard levels, chapters, heatmap, caption list
- `storyboard.py`: fetch sheets in parallel, slice into frames
- `local.py`: ffmpeg keyframes → frames + our own sheets
- `audio.py`: yt-dlp audio download, 16 kHz WAV, pauses, cutting into pieces
- `speech.py` + `bv_speech.swift`: Apple's on-device transcriber (macOS 26), built on first use into
  `~/Library/Caches/boson-video/`; pieces run at once; `names()` lists the video's own names for the writer
- `accuracy.py`: error rates against human captions (words; characters for Chinese)
- `scenes.py`: cuts, looks, base/repeat/new, `profile()` headline
- `render.py`: today's self-contained page (CSS sprites, no JS); milestone 3 grows it into the read view
- `pipeline.py`: `build` (scenes) and `add_words` (speech), with per-stage timings · `cli.py`: entry point
- `timeline.py`: the shared data model; `timeline.json` is the contract between stages
- `docs/`: `DIRECTION.md` (source of truth) and `read-view.html` (target design)

## Rules

- Follow `docs/DIRECTION.md`: build the next milestone, respect "Not now", and update the
  milestone table when work lands. Don't change the direction without the owner.
- Speed is the product. Time every stage (`Stopwatch` in `pipeline.py`) and update the
  README's measured table when numbers move. Say which numbers are measured and which
  are estimates.
- Scene thresholds were calibrated on three reference videos. After any change to
  `scenes.py`, recheck all three: 9JKT5rBbrwM (talking head, expect 3 scenes),
  zjkBMFhNj_g (slides + webcam box, about 59 new, no false repeats), dQw4w9WgXcQ (fast
  cuts). `tests/test_scenes.py` encodes the same cases.
- Jev is text-only and doesn't write text: it judges (checks, finds) and another model
  writes. Read TypeSafe's live docs (https://docs.typesafe.ai/llms.txt) before
  integrating it.
- Keys live in `.env`, which git ignores: `TYPESAFE_API_KEY` (Jev), `INCEPTION_API_KEY`
  (Mercury). Never commit keys.
- Don't try to get around YouTube's bot checks (PO tokens, player API clients). The
  Chrome extension is the route for that.
- Ask the owner before downloading models or media. `docs/DIRECTION.md` lists what is pending.
