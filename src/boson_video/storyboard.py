"""Storyboard sheets -> frames: fetch every sheet at once, then cut out the grid cells."""

from __future__ import annotations

import asyncio
import io

import httpx
import numpy as np
from PIL import Image

from .timeline import Frame, Sheet
from .youtube import HEADERS, StoryboardLevel


async def fetch_sheets(client: httpx.AsyncClient, level: StoryboardLevel) -> list[bytes]:
    async def one(m: int) -> bytes:
        r = await client.get(level.sheet_url(m), headers=HEADERS)
        r.raise_for_status()
        return r.content

    return list(await asyncio.gather(*(one(m) for m in range(level.sheet_count))))


def cut_frames(
    level: StoryboardLevel, sheet_jpegs: list[bytes], duration: float
) -> tuple[list[Sheet], list[Frame], list[np.ndarray]]:
    """Decode the sheets and slice them into frames.

    Returns the sheets (the renderer shows frames straight from them), the frames
    (position + time), and each frame's RGB pixels for analysis.
    """
    sheets: list[Sheet] = []
    frames: list[Frame] = []
    pixels: list[np.ndarray] = []
    for m, data in enumerate(sheet_jpegs):
        img = Image.open(io.BytesIO(data)).convert("RGB")
        arr = np.asarray(img)
        sheets.append(Sheet(data, img.width, img.height))
        for i in range(level.per_sheet):
            k = m * level.per_sheet + i
            if k >= level.count:
                break
            x, y = (i % level.cols) * level.width, (i // level.cols) * level.height
            if x + level.width > img.width or y + level.height > img.height:
                break  # a short last sheet
            t = level.frame_time(k, duration)
            if frames and t <= frames[-1].t:
                continue  # frames past the end all clamp to the same moment
            frames.append(Frame(len(frames), t, m, x, y, level.width, level.height))
            pixels.append(arr[y : y + level.height, x : x + level.width])
    return sheets, frames, pixels
