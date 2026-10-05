"""Mercury (Inception's diffusion model): one strict-JSON request, retried when the network or
the reply fails. Every model that writes text for the page goes through here."""

from __future__ import annotations

import json
import os
import time

import httpx

URL = "https://api.inceptionlabs.ai/v1/chat/completions"
MODEL = "mercury-2.5"
PRICE_PER_MTOK = (0.04, 0.15)  # input, output (list price, 2026-09)


class MercuryError(RuntimeError):
    pass


def body(system: str, payload: dict, schema: dict, name: str, effort: str = "low", max_tokens: int = 12000) -> dict:
    return {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "reasoning_effort": effort,
        "temperature": 0.5,  # the lowest the API allows
        "max_completion_tokens": max_tokens,
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}},
    }


def post(request: dict, transport=None) -> dict:
    """The raw reply; a 5xx or a dropped connection is retried twice."""
    key = os.environ.get("INCEPTION_API_KEY")
    if not key:
        raise MercuryError("no INCEPTION_API_KEY in .env (Mercury writes the text)")
    # Mercury writes an hour-long video's summary in about 9 s; a call still going after a minute
    # is stuck (one took 126 s, 2026-10-04), so it is dropped and tried again.
    with httpx.Client(timeout=60, transport=transport) as client:
        r = None
        for tries in range(3):
            try:
                r = client.post(URL, json=request, headers={"Authorization": f"Bearer {key}"})
            except httpx.HTTPError as e:
                if tries == 2:
                    raise MercuryError(f"could not reach Mercury: {type(e).__name__}") from None
                time.sleep(0.5 * (tries + 1))
                continue
            if r.status_code in (500, 502, 503, 504) and tries < 2:
                time.sleep(0.5 * (tries + 1))
                continue
            break
    if r.status_code != 200:
        hint = {401: "the key was rejected; check INCEPTION_API_KEY", 402: "no Mercury credits left",
                429: "Mercury is rate limited; wait a minute"}.get(r.status_code, r.text[:200])
        raise MercuryError(f"Mercury API error {r.status_code}: {hint}")
    return r.json()


def content(res: dict):
    """The JSON the schema asked for, or None when the reply isn't JSON."""
    try:
        return json.loads(res["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None


def stats(res: dict, started: float, attempts: int = 1) -> dict:
    usage = res.get("usage") or {}
    out = {
        "seconds": round(time.perf_counter() - started, 2),
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "attempts": attempts,
    }
    out["cost_usd"] = round((out["input_tokens"] * PRICE_PER_MTOK[0] + out["output_tokens"] * PRICE_PER_MTOK[1]) / 1e6, 5)
    return out


def ask_json(system: str, payload: dict, schema: dict, name: str, usable, effort: str = "low",
             max_tokens: int = 12000, transport=None) -> tuple[dict, dict]:
    """One request; asked once more if `usable(reply)` is false (about one reply in ten has the wrong shape)."""
    started = time.perf_counter()
    request = body(system, payload, schema, name, effort, max_tokens)
    for attempt in (1, 2):
        res = post(request, transport)
        out = content(res)
        if isinstance(out, list):  # Mercury once wrapped the object in a list
            out = next((x for x in out if isinstance(x, dict)), None)
        if isinstance(out, dict) and usable(out):
            return out, stats(res, started, attempt)
    raise MercuryError(f"Mercury returned no usable {name} twice")
