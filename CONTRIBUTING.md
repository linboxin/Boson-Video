# Contributing

Thanks for helping. Boson-Video turns a video into a document any AI can read: what was said, what
was shown, and the second each line came from. [docs/DIRECTION.md](docs/DIRECTION.md) says what we're
building and what is out of scope for now; [docs/workflow.md](docs/workflow.md) shows how the pieces
fit.

## Set up

```bash
git clone https://github.com/linboxin/Boson-Video && cd Boson-Video
uv sync
uv run pytest            # the offline tests, a few seconds
uv run pytest -m live    # also hits YouTube and runs Apple's transcriber (macOS 26)
```

You don't need any keys to work on it. Optional keys go in `.env`, which git ignores (the README
lists them). Never commit a key.

Try a change the way people meet it:

- `uv run boson-video <link or file>` builds a video and prints each stage's time
- `uv run boson-video web` (or `serve`) for the pages
- `uv run python scripts/mcp_smoke.py <video> --no-keys` runs the plugin like an AI app and calls every tool

## Before you open a pull request

- **The tests pass** (`uv run pytest`), and new behaviour comes with a test.
- **Scene detection:** after any change to `scenes.py`, recheck the three reference videos:
  `9JKT5rBbrwM` (a talking head, about 3 scenes), `zjkBMFhNj_g` (slides, about 59 new and no false
  repeats) and `dQw4w9WgXcQ` (fast cuts). `tests/test_scenes.py` encodes the same cases.
- **Speed is measured:** if a stage gets faster or slower, update `docs/measured.md` and say which
  numbers are measured and which are estimates.
- **It works with no keys:** anything that needs a model key is an extra, and it says what wrote
  or checked its result.
- **YouTube:** don't add ways around YouTube's bot checks (tokens, player API clients).
- **Downloads:** say so in the pull request if your change downloads a model or media onto a user's
  computer.

Commits follow [Conventional Commits](https://www.conventionalcommits.org) (`feat:`, `fix:`,
`docs:` and so on).

## Bigger changes

For a change to the direction (a new kind of video, a new source, hosting), open an issue first, so
we can agree on it before you build. [AGENTS.md](AGENTS.md) is the same guide written for coding
agents.

## Writing docs

Plain words, short sentences, and a time or a number wherever there is one. Name optional models
by what they do first: the writer (Mercury by default), the checker (Jev).

By contributing, you agree that your work is released under the project's MIT license.
