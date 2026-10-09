"""The writing model: one strict-JSON chat request to an OpenAI-compatible endpoint, retried when the
network or the reply fails. Every model that writes text (the summary, the English, the glossary,
answers) goes through here, so swapping the model is configuration, not code.

Mercury (Inception's diffusion model) is the default: cheap and fast. Another endpoint (a local
Ollama, Gemini, OpenAI, a newer Mercury) is three settings: BOSON_WRITER_BASE_URL (e.g.
http://localhost:11434/v1), BOSON_WRITER_MODEL and BOSON_WRITER_API_KEY; BOSON_WRITER_PRICES ("0.1,0.5"
per million tokens in and out) lets the cost be counted.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import httpx

MERCURY_URL = "https://api.inceptionlabs.ai/v1/chat/completions"
MERCURY_MODEL = "mercury-2.5"
MERCURY_PRICES = (0.04, 0.15)  # per million tokens, input and output (list price, 2026-09)


class LLMError(RuntimeError):
    pass


@dataclass
class Endpoint:
    url: str
    model: str
    key: str | None
    prices: tuple[float, float]
    mercury: bool  # Mercury takes `reasoning_effort` and a temperature floor; other endpoints get neither unless asked


def endpoint() -> Endpoint:
    """Where the writing goes, read from the environment at call time."""
    base = os.environ.get("BOSON_WRITER_BASE_URL", "").strip()
    if not base:
        return Endpoint(MERCURY_URL, os.environ.get("BOSON_WRITER_MODEL") or MERCURY_MODEL,
                        os.environ.get("INCEPTION_API_KEY"), MERCURY_PRICES, True)
    url = base if base.rstrip("/").endswith("/chat/completions") else base.rstrip("/") + "/chat/completions"
    model = os.environ.get("BOSON_WRITER_MODEL")
    if not model:
        raise LLMError("BOSON_WRITER_BASE_URL is set but BOSON_WRITER_MODEL isn't")
    try:
        prices = tuple(float(x) for x in os.environ.get("BOSON_WRITER_PRICES", "0,0").split(","))[:2]
    except ValueError:
        prices = (0.0, 0.0)
    return Endpoint(url, model, os.environ.get("BOSON_WRITER_API_KEY"), prices, False)


def configured() -> bool:
    """A writer is set up: Mercury's key, or another endpoint."""
    return bool(os.environ.get("BOSON_WRITER_BASE_URL", "").strip() or os.environ.get("INCEPTION_API_KEY"))


def model_name() -> str:
    try:
        return endpoint().model
    except LLMError:
        return "unknown"


def body(system: str, payload: dict, schema: dict, name: str, effort: str | None = "low", max_tokens: int = 12000) -> dict:
    ep = endpoint()
    request = {
        "model": ep.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "max_completion_tokens": max_tokens,
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}},
    }
    if ep.mercury:
        request["temperature"] = 0.5  # the lowest Mercury allows
    if effort and (ep.mercury or os.environ.get("BOSON_WRITER_EFFORT")):
        request["reasoning_effort"] = effort
    return request


def post(request: dict, transport=None) -> dict:
    """The raw reply; a 5xx or a dropped connection is retried twice."""
    ep = endpoint()
    if ep.mercury and not ep.key:
        raise LLMError("no INCEPTION_API_KEY in .env (Mercury writes the text)")
    headers = {"Authorization": f"Bearer {ep.key}"} if ep.key else {}
    # Mercury writes an hour-long video's summary in about 9 s; a call still going after two minutes
    # is stuck (one took 126 s, 2026-10-04), so it is dropped and tried again.
    with httpx.Client(timeout=120, transport=transport) as client:
        r = None
        for tries in range(4):
            try:
                r = client.post(ep.url, json=request, headers=headers)
            except httpx.HTTPError as e:
                if tries == 3:
                    raise LLMError(f"could not reach the writing model ({ep.model}): {type(e).__name__}") from None
                time.sleep(0.5 * (tries + 1))
                continue
            if r.status_code == 429 and tries < 3:  # rate limited: wait as long as asked (or 2, 4, 8 s)
                time.sleep(_retry_after(r, 2 ** (tries + 1)))
                continue
            if r.status_code in (500, 502, 503, 504) and tries < 3:
                time.sleep(1.0 * (tries + 1))
                continue
            break
    if r.status_code != 200:
        hint = {401: "the key was rejected", 402: "no credits left", 429: "rate limited; wait a minute"}.get(
            r.status_code, r.text[:200])
        raise LLMError(f"{ep.model} API error {r.status_code}: {hint}")
    return r.json()


def _retry_after(r: httpx.Response, default: float) -> float:
    try:
        return min(20.0, max(0.5, float(r.headers.get("retry-after", default))))
    except ValueError:
        return default


def content(res: dict):
    """The JSON the schema asked for, or None when the reply isn't JSON."""
    try:
        return json.loads(res["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None


def stats(res: dict, started: float, attempts: int = 1) -> dict:
    usage = res.get("usage") or {}
    prices = endpoint().prices
    out = {
        "seconds": round(time.perf_counter() - started, 2),
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "attempts": attempts,
    }
    out["cost_usd"] = round((out["input_tokens"] * prices[0] + out["output_tokens"] * prices[1]) / 1e6, 5)
    return out


def ask_json(system: str, payload: dict, schema: dict, name: str, usable, effort: str | None = "low",
             max_tokens: int = 12000, transport=None) -> tuple[dict, dict]:
    """One request; asked once more if `usable(reply)` is false (about one Mercury reply in ten has the wrong shape)."""
    started = time.perf_counter()
    request = body(system, payload, schema, name, effort, max_tokens)
    for attempt in (1, 2):
        res = post(request, transport)
        out = content(res)
        if isinstance(out, list):  # Mercury once wrapped the object in a list
            out = next((x for x in out if isinstance(x, dict)), None)
        if isinstance(out, dict) and usable(out):
            return out, stats(res, started, attempt)
    raise LLMError(f"{endpoint().model} returned no usable {name} twice")
