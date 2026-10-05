# Boson-Video: guide for coding agents

Read any video like a document. **Read [docs/DIRECTION.md](docs/DIRECTION.md) first.** It
holds the agreed direction, the milestones, who does what, and the owner's open
decisions. The target screen is [docs/read-view.html](docs/read-view.html); open it in a
browser.

## Commands

- `uv sync` once, then `uv run boson-video <youtube link | id | file> [--open] [--no-words] [--no-summary] [--lang zh_CN] [-o out]`
- `uv run boson-video ask <video> "question"`: the moment that answers it (needs the page to exist)
- `uv run boson-video serve [--open <video>]`: the pages on 127.0.0.1:8765 with the video playing beside them and a working ask box
- `uv run boson-video mcp`: the plugin (MCP over stdio) for Claude Code, Claude Desktop, Cursor, Codex; setup in the README
- `uv run python scripts/mcp_smoke.py <video> [--no-keys]`: run the plugin like an AI app and call every tool
- `uv run pytest` (offline) · `uv run pytest -m live` (hits YouTube, runs Apple's transcriber)
- `uv run python scripts/accuracy.py <video id> <caption language> <locale>`: score our transcript against human captions

## Map

- `src/boson_video/youtube.py`: watch page → video, storyboard levels, chapters, heatmap, caption list
- `storyboard.py`: fetch sheets in parallel, slice into frames
- `local.py`: ffmpeg keyframes → frames + our own sheets
- `audio.py`: yt-dlp audio download, 16 kHz WAV, pauses, cutting into pieces
- `speech.py` + `bv_speech.swift`: Apple's on-device transcriber (macOS 26), built on first use into
  `~/Library/Caches/boson-video/`; pieces run at once; `names()` lists the video's own names for the writer
- `sensevoice.py`: SenseVoice through sherpa-onnx, where Apple's transcriber isn't available (Windows, Linux)
- `mercury.py`: the one Mercury client (strict JSON, retries, cost)
- `study.py`: English for every passage, the glossary, and answers to questions (Jev finds, Mercury explains, Jev checks)
- `server.py`: `boson-video serve`: library, pages, `/api/ask` (JSON from its own origin only), questions kept in `out/<id>/notes.json`
- `library.py`: where videos live (`BOSON_VIDEO_HOME`), load and save (page, `timeline.json`, `sheets/`)
- `jobs.py`: builds a video in a background thread; progress in `status.json`
- `frames.py`: picks moments from the scene map; full-resolution frames (yt-dlp stream address + ffmpeg, one per second needed); thumbnail fallback
- `plugin.py`: the plugin's tools as plain functions (briefing, read, frames, search, check, list) · `mcp_server.py`: wires them to MCP
- `accuracy.py`: error rates against human captions (words; characters for Chinese)
- `writer.py`: Mercury writes the summary and sections (strict JSON schema, every sentence cites passages, one retry)
- `checker.py`: Jev checks each sentence against its passages; numbers compared in code; citations repaired
- `ask.py`: Jev finds the passage that answers a question (one pass, or two for more than 255 passages)
- `env.py`: loads keys from `.env`
- `scenes.py`: cuts, looks, base/repeat/new, `profile()` headline
- `render.py`: the self-contained read view (ribbon, summary with language switch, search, scenes); a little JS, no libraries
- `pipeline.py`: `build` (scenes), `add_words` (speech), `add_summary` (write + check), with per-stage timings · `cli.py`: entry point
- `timeline.py`: the shared data model; `timeline.json` is the contract between stages and for other tools, versioned, spec in `docs/timeline-format.md`
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
  writes. It leans toward the option listed first, so every Choice goes out twice in the same
  request with the options reversed, and the answers are averaged (`checker.both_orders`).
- The engine must work with no keys. Anything that needs Jev or a writing model is an extra
  that says what it is and what checked it. Read TypeSafe's live docs (https://docs.typesafe.ai/llms.txt) before
  integrating it.
- Keys live in `.env`, which git ignores: `TYPESAFE_API_KEY` (Jev), `INCEPTION_API_KEY`
  (Mercury). Never commit keys.
- Don't try to get around YouTube's bot checks (PO tokens, player API clients). The
  Chrome extension is the route for that.
- Ask the owner before downloading models or media. `docs/DIRECTION.md` lists what is pending.
