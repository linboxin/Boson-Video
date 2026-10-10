# Milestone 4: the plugin (design)

2026-10-04. Direction: [DIRECTION.md](../DIRECTION.md), milestone 4. The shape: a briefing on
open, then tools to drill down.

## Goal

Any AI app that speaks MCP (Claude Code, Claude Desktop, Cursor, Codex) can open a YouTube
link or a video file and understand it: get oriented in one call, read any stretch, look at
the frames that matter at full resolution, search, and check a claim before stating it. It
works with no keys; a Jev key makes the checks independent and the search semantic.

## Units

| Unit | Does | Depends on |
| --- | --- | --- |
| `timeline.py` | The data model. `to_json` now carries `format` and `version: 1`; `Timeline.from_json` rebuilds it | nothing |
| `library.py` | Where videos live (`BOSON_VIDEO_HOME`, default `~/.boson-video`; the CLI keeps `./out`), key from a link or a path, load a video, save the sheets as files | timeline |
| `jobs.py` | Builds a video in a background thread: scenes, page, words, then the summary if there are keys. Progress in `status.json` | pipeline, library |
| `frames.py` | Picks moments from the scene map; fetches full-resolution frames (yt-dlp gives the video-only stream address, ffmpeg takes one frame per second needed, in parallel, cached in `frames/`); falls back to a thumbnail cut from the sheets | library, yt-dlp, ffmpeg |
| `plugin.py` | The five tools as plain functions returning text and images, so they are testable without MCP | library, jobs, frames, checker, ask |
| `mcp_server.py` | Wires the tools to MCP (official `mcp` SDK, stdio); `boson-video mcp` runs it | plugin |

## The tools

- **`video_open(video)`**: starts the job if needed and returns a briefing within seconds:
  title, channel, length, language, transcriber, status (words ready or "about N s"), what the
  picture does, chapters or summary sections with times, the summary in English if built, key
  terms if built, and, without chapters or summary, the first line of every 5 minutes. It ends
  with how to read further and how to cite (`[m:ss]`, link with `&t=`), and a note that the
  transcript is the video's content, not instructions.
- **`video_read(video, start, end, lang)`**: lines `[m:ss] original // English`, cut at about
  12k tokens with the call that continues. While the words aren't ready, it returns the status.
- **`video_frames(video, at | start–end, max 6)`**: images, about 1280 px wide, each captioned
  with its time and what the scene map says it is (new visual, build step). In a range, the
  moments come from the scene map (new scenes and their build steps, never repeats).
- **`video_search(query, video?)`**: across every video, or one. Free: words and characters
  matched in the original and the English. With a Jev key and one video: Jev's line search
  first, then the matches. The result says which method found it.
- **`video_check(video, claim, at)`**: the claim against the passages at those times and their
  neighbours. With a key: Jev, then the number rule in code. Without: the number rule only,
  reported as "numbers checked by code; meaning not checked (no Jev key)".

## Checks that say what checked them

`Summary.checker` and each answer carry who checked: `jev+code` or `code`. With a writing key
but no Jev key, the page still runs the number rule and says so.

## Jev's first-option bias

TypeSafe lists it among jev-1.13's weaknesses. Each Jev question is sent twice in the same
request with the options in opposite orders, and the probabilities are averaged: the
relation check (supports / contradicts / says nothing) and the line search (passage ids).
One request, so no added wait.

## Smaller fixes in this milestone

- The engine runs without `.env`: no writing key means no summary, said plainly, exit 0.
- The language guess reads the title and the description.
- `boson-video serve` accepts asks only as JSON from its own origin (any web page could post
  to it before).

## Testing

Offline tests for each unit with fake Jev and fake Mercury replies; a smoke script that runs
the real MCP server over stdio and calls every tool; one run from Claude Code on
`qbReD1cGykQ`. Cursor is still to be tried, with the config in the README.
