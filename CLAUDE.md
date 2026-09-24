# Boson-Video

Near-instant video summaries. Phase 1 (built): YouTube link or file → visual
timeline of scenes in ~1 s, no model. Phase 2 (next): speech + Jev "where to
look" + vision on chosen moments + streamed summary. Phase 3: Chrome extension.

## Commands

- `uv run boson-video <youtube link | id | file> [--open] [-o out] [--level N]`
- `uv run pytest` (offline) · `uv run pytest -m live` (hits YouTube)

## Map

- `youtube.py`: watch page → video, storyboard levels, chapters, heatmap, caption list
- `storyboard.py`: fetch sheets in parallel, slice into frames
- `local.py`: ffmpeg keyframes → frames + our own sheets
- `scenes.py`: cuts, looks, base/repeat/new, `profile()` headline
- `render.py`: self-contained HTML (CSS sprites, no JS)
- `pipeline.py`: orchestration + per-stage timings · `cli.py`: entry point
- `timeline.py`: the shared data model; `timeline.json` is the contract for phase 2

## Rules

- Speed is the product: time every stage (the `Stopwatch` in `pipeline.py`),
  and update the README's measured table when numbers move. Say which numbers
  are measured and which are estimates.
- Scene thresholds were calibrated on three reference videos. Recheck all three
  after any change to `scenes.py`: 9JKT5rBbrwM (talking head, expect 3 scenes),
  zjkBMFhNj_g (slides + webcam box, ~59 new, no false repeats), dQw4w9WgXcQ
  (fast cuts). The synthetic tests in `tests/test_scenes.py` encode the same cases.
- Jev / TypeSafe work (phase 2): use the `typesafe-ai` skill and read the live
  docs first. Jev is text-only and doesn't generate text, so it judges, and
  another model writes.
- No API keys in git (`.env` is ignored). Don't try to get around YouTube's bot
  checks (PO tokens, player API clients); the extension is the route for that.
