"""OpenAI's writing models (GPT-6 Luna, Sol, Astra) through the Responses API: one strict-JSON
request, retried when the network or the server fails. The writer can use them in place of
Mercury (`BOSON_WRITER=gpt-6.1-sol`); the key is OPENAI_API_KEY.
"""

from __future__ import annotations

import json
import os
import time

import httpx

URL = "https://api.openai.com/v1/responses"
# Per million tokens, input and output (reasoning tokens bill as output); OpenAI's model page, 2026-10-09.
PRICES = {"gpt-6-luna": (0.10, 0.50), "gpt-6.1-sol": (2.0, 10.0), "gpt-6-astra": (10.0, 50.0)}


class OpenAIError(RuntimeError):
    pass


def ask_json(system: str, payload: dict, schema: dict, name: str, model: str, effort: str = "medium",
             transport=None) -> tuple[dict, dict]:
    """The JSON object the schema asks for, and the call's stats (seconds, tokens, cost)."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise OpenAIError("no OPENAI_API_KEY (an OpenAI model was chosen to write)")
    request = {
        "model": model,
        "reasoning": {"effort": effort},
        "input": [{"role": "system", "content": system},
                  {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        "text": {"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
    }
    started = time.perf_counter()
    with httpx.Client(timeout=300, transport=transport) as client:  # high effort on an hour of speech takes a while
        r = None
        for tries in range(3):
            try:
                r = client.post(URL, json=request, headers={"Authorization": f"Bearer {key}"})
            except httpx.HTTPError as e:
                if tries == 2:
                    raise OpenAIError(f"could not reach OpenAI: {type(e).__name__}") from None
                time.sleep(1 + tries)
                continue
            if r.status_code in (429, 500, 502, 503, 504) and tries < 2:
                time.sleep(2 * (tries + 1))
                continue
            break
    if r.status_code != 200:
        raise OpenAIError(f"OpenAI API error {r.status_code}: {r.text[:300]}")
    res = r.json()
    text = res.get("output_text") or next(
        (c.get("text") for o in res.get("output", []) if o.get("type") == "message"
         for c in o.get("content", []) if c.get("type") == "output_text"), None)
    try:
        out = json.loads(text or "")
    except json.JSONDecodeError:
        raise OpenAIError(f"{model} returned no JSON for {name}") from None
    usage = res.get("usage") or {}
    tokens_in, tokens_out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    price = PRICES.get(model, (0.0, 0.0))
    return out, {"seconds": round(time.perf_counter() - started, 2), "input_tokens": tokens_in,
                 "output_tokens": tokens_out, "attempts": 1,
                 "cost_usd": round((tokens_in * price[0] + tokens_out * price[1]) / 1e6, 5)}
