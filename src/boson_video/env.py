"""Load keys without overriding the real environment, from (in order) the project's .env (a clone),
the .env in the folder you start in, and BOSON_VIDEO_HOME/.env (default ~/.boson-video/.env), which
is where an installed copy (`uvx boson-video …`) finds them. From the last two, only this tool's own
keys are taken. A server that starts without a key says so (`missing`), so a page never goes
quietly without its summary (2026-10-09: started with uvx, the repo's .env was never read).
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ENV = Path(__file__).resolve().parents[2] / ".env"
KEYS = {
    "INCEPTION_API_KEY": "no summaries, English or terms (Mercury writes them)",
    "TYPESAFE_API_KEY": "no asking, and checks fall back to the numbers, compared in code (Jev judges the rest)",
    "OPENAI_API_KEY": "",
}


def load_env(path: Path | None = None) -> None:
    if path is not None:
        _load(path, everything=True)
        return
    _load(PROJECT_ENV, everything=True)
    _load(Path.cwd() / ".env", everything=False)
    home = Path(os.environ.get("BOSON_VIDEO_HOME") or Path.home() / ".boson-video").expanduser()
    _load(home / ".env", everything=False)


def missing() -> list[str]:
    """What a page loses for each key that isn't set, ready to print."""
    return [f"no {key}: {loss}" for key, loss in KEYS.items() if loss and not os.environ.get(key)]


def _load(path: Path, everything: bool) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if everything or key in KEYS or key.startswith("BOSON_"):
            os.environ.setdefault(key, value.strip('"').strip("'"))
