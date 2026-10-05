"""Run the real plugin over stdio, the way an AI app does, and call every tool once.

    uv run python scripts/mcp_smoke.py <video> [--home out]

Prints what an AI would get (text, and the size of each image). Uses the network for
full-resolution frames and Jev (if TYPESAFE_API_KEY is set); no writing model is called.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import os
import sys
import time
from pathlib import Path

from mcp import Client, StdioServerParameters


async def main(video: str, home: str, no_keys: bool, read: tuple[str, str], frames: tuple[str, str],
               query: str, claim: str, claim_at: str) -> None:
    env = {"BOSON_VIDEO_HOME": str(Path(home).resolve()), "PYTHONIOENCODING": "utf-8"}
    if no_keys:  # empty values win over .env (it never overrides what is already set)
        env |= {"TYPESAFE_API_KEY": "", "INCEPTION_API_KEY": ""}
    params = StdioServerParameters(command=sys.executable, args=["-m", "boson_video.cli", "mcp"], env=env,
                                   cwd=str(Path(__file__).resolve().parents[1]))
    async with Client(params, read_timeout_seconds=180) as c:
        tools = await c.list_tools()
        print("tools:", ", ".join(t.name for t in tools.tools))
        started = time.perf_counter()
        for attempt in range(40):  # a new video: the map first, then poll until the words are ready
            res = await c.call_tool("video_open", {"video": video})
            text = res.content[0].text
            done = "Status: words ready" in text or "failed" in text
            if attempt == 0 or done:
                print(f"\n=== video_open after {time.perf_counter() - started:.1f} s")
                print(text[:2500])
            if done:
                break
            await asyncio.sleep(5)
        calls = [
            ("video_read", {"video": video, "start": read[0], "end": read[1]}),
            ("video_search", {"query": query, "video": video}),
            ("video_frames", {"video": video, "start": frames[0], "end": frames[1], "limit": 3}),
            ("video_check", {"video": video, "claim": claim, "at": [claim_at]}),
            ("video_list", {}),
        ]
        for name, args in calls:
            t = time.perf_counter()
            res = await c.call_tool(name, args)
            took = time.perf_counter() - t
            print(f"\n=== {name} {args} ({took:.1f} s){' ERROR' if res.is_error else ''}")
            for block in res.content:
                if block.type == "text":
                    print(block.text[:1500] + (" …" if len(block.text) > 1500 else ""))
                elif block.type == "image":
                    print(f"[image {block.mime_type}, {len(base64.b64decode(block.data)) // 1024} KB]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--home", default=os.environ.get("BOSON_VIDEO_HOME", "out"))
    ap.add_argument("--no-keys", action="store_true", help="run as a user with no Jev or writing key")
    ap.add_argument("--read", nargs=2, default=["4:25", "5:10"])
    ap.add_argument("--frames", nargs=2, default=["8:10", "9:30"])
    ap.add_argument("--query", default="KL")
    ap.add_argument("--claim", default="KL divergence measures how different the two models' next-word probabilities are")
    ap.add_argument("--claim-at", default="9:05")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main(a.video, a.home, a.no_keys, tuple(a.read), tuple(a.frames), a.query, a.claim, a.claim_at))
