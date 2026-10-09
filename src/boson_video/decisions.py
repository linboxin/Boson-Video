"""OpenAI's Decisions API (gpt-6-luna): typed judgments over text and images, the judge that can
look at a frame. Jev reads text only. This client answers in Jev's shape (a Choice's probabilities
by label, `client.system_one(state, questions)`), so the checker can ask either one, and a state
that carries `frames` (paths to JPEGs) sends them as images.

Measured 2026-10-09: about 0.4 s a call (0.2 s of it OpenAI's processing), 160 tokens for a short
claim, and a 1280x720 frame about 940 tokens more.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import httpx

URL = "https://api.openai.com/v1/decisions"
MODEL = "gpt-6-luna"
PRICE_PER_MTOK = 0.10  # input tokens; output is free (OpenAI's guide, public beta, 2026-10)


class DecisionsError(RuntimeError):
    pass


def available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def image_part(path: str | Path) -> dict:
    """A frame as the API takes it: inline base64 (hosted URLs and file ids are refused)."""
    data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return {"type": "input_image", "image_url": f"data:image/jpeg;base64,{data}"}


def question(name: str, spec: dict) -> dict:
    """A Jev-style question ({"type": "choice", "instructions", "criteria": {label: meaning}}) as
    the Decisions API asks it: the options become `choices` in the same order."""
    if spec["type"] != "choice":
        raise DecisionsError(f"only choices are translated, not {spec['type']}")
    return {"type": "choice", "name": name, "instructions": spec["instructions"],
            "choices": [{"value": k, "description": v} for k, v in spec["criteria"].items()]}


class AsyncDecisionsClient:
    """One client per event loop (the checker runs its own). `usage` adds up every call."""

    label = "openai"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, render: str = "json"):
        self.render = render  # how the state is written for the model: "json", or "lines" (key: value)
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise DecisionsError("no OPENAI_API_KEY in .env (OpenAI's Decisions API judges frames)")
        self._headers = {"Authorization": f"Bearer {key}"}
        self._transport = transport
        self._http: httpx.AsyncClient | None = None
        self.usage = {"calls": 0, "input_tokens": 0, "seconds": 0.0}

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def ask(self, content: str | list[dict], questions: list[dict]) -> dict[str, dict]:
        """{name: answer} for one request; a refused question is left out. A 429, a 5xx or a
        dropped connection is retried twice."""
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30, transport=self._transport)
        body = {"model": MODEL, "questions": questions,
                "input": content if isinstance(content, str) else [{"role": "user", "content": content}]}
        started = time.perf_counter()
        r = None
        for tries in range(3):
            try:
                r = await self._http.post(URL, json=body, headers=self._headers)
            except httpx.HTTPError as e:
                if tries == 2:
                    raise DecisionsError(f"could not reach OpenAI: {type(e).__name__}") from None
                await asyncio.sleep(0.5 * (tries + 1))
                continue
            if r.status_code in (429, 500, 502, 503, 504) and tries < 2:
                await asyncio.sleep(float(r.headers.get("retry-after") or 0.5 * (tries + 1)))
                continue
            break
        if r.status_code != 200:
            hint = {401: "the key was rejected; check OPENAI_API_KEY", 429: "rate limited or out of credit"}
            raise DecisionsError(f"Decisions API error {r.status_code}: {hint.get(r.status_code, r.text[:200])}")
        res = r.json()
        self.usage["calls"] += 1
        self.usage["input_tokens"] += (res.get("usage") or {}).get("input_tokens", 0)
        self.usage["seconds"] += time.perf_counter() - started
        return {a["name"]: a for a in res.get("answers", []) if a.get("type") != "refusal"}

    async def system_one(self, state: dict, questions: dict) -> SimpleNamespace:
        """Jev's call shape: the state as JSON text (plus its `frames` as images), each Choice's
        probabilities by label in `.choices[name].probabilities`."""
        frames = [image_part(p) for p in state.get("frames", [])]
        text = render({k: v for k, v in state.items() if k != "frames"}, self.render)
        content = [{"type": "input_text", "text": text}, *frames] if frames else text
        answers = await self.ask(content, [question(name, spec) for name, spec in questions.items()])
        return SimpleNamespace(choices={
            name: SimpleNamespace(probabilities={p["value"]: p["probability"] for p in a.get("probabilities", [])})
            for name, a in answers.items() if a.get("type") == "choice"
        })


def render(state: dict, how: str = "json") -> str:
    """The state as text: JSON (what Jev takes), or one `key: value` per field with lists as lines."""
    if how == "json":
        return json.dumps(state, ensure_ascii=False)
    out = []
    for k, v in state.items():
        out.append(f"{k}:\n" + "\n".join(f"- {x}" for x in v) if isinstance(v, list) else f"{k}: {v}")
    return "\n".join(out)


def cost_usd(input_tokens: int) -> float:
    return round(input_tokens * PRICE_PER_MTOK / 1e6, 6)
