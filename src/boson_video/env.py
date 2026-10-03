"""Load keys from the project's .env (ignored by git) without overriding the real environment."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ENV = Path(__file__).resolve().parents[2] / ".env"


def load_env(path: Path = PROJECT_ENV) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
