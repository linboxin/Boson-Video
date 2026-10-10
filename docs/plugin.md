# The plugin

`boson-video mcp` is an MCP server, the standard Claude Code, Claude Desktop, Cursor and Codex
use for tools. Your AI opens a video, reads the transcript, looks at the frames that matter at
full resolution, searches, and checks a claim before stating it. It works with no keys; your
AI does the writing. With `TYPESAFE_API_KEY`, the checker (Jev, from TypeSafe) also judges claims by meaning, and search adds its pick of the passage that answers.

| Tool | What your AI gets |
| --- | --- |
| `video_open(video)` | A briefing within seconds: length, language, chapters, what the picture does, the summary and key terms if built, how to go on. A new video builds in the background (the map in about 2 s, the words in 10–50 s) |
| `video_read(video, start, end, lang)` | Timed lines, `[m:ss] original // English`, and each picture change as a moment (`state`, `delta`, `trajectory`, or `seek`) with the lines new on screen; `video_frames` shows its frame. Up to about 12k tokens a reply |
| `video_frames(video, at \| start–end)` | 6 frames by default, up to 12, full resolution, at the new visuals the scene map found (or exact moments), each citing the moment and what was said then |
| `video_search(query, video?)` | Where something is said or shown, in one video or all of them. A hit on the picture cites the same moment as `video_read` |
| `video_check(video, claim, at)` | The claim against what was said and shown at those moments, and which checker judged it |
| `video_list()` | The videos opened so far |

## Install

It needs [uv](https://docs.astral.sh/uv/) and nothing else: no clone, no ffmpeg, no Node (both come
with the package).

| App | How |
| --- | --- |
| Claude Code | `claude mcp add boson-video -- uvx boson-video mcp` |
| Claude Desktop | `claude_desktop_config.json`: `{ "mcpServers": { "boson-video": { "command": "uvx", "args": ["boson-video", "mcp"] } } }` |
| Cursor | `.cursor/mcp.json`: the same JSON |
| Codex | `~/.codex/config.toml`: `[mcp_servers.boson-video]` with `command = "uvx"` and `args = ["boson-video", "mcp"]` |

Optional: add `"env": { "TYPESAFE_API_KEY": "…" }` (or `env = { TYPESAFE_API_KEY = "…" }` in Codex)
so Jev checks claims by meaning. Videos are kept in `~/.boson-video` (`BOSON_VIDEO_HOME` moves them).

**The first video.** On a Mac with macOS 26 and Xcode's command line tools, Apple's transcriber
does the words, with nothing to download. Anywhere else (Windows, Linux, an older Mac) the plugin
downloads one speech model the first time a video needs it: SenseVoice for Chinese (about 166 MB)
or Parakeet for English (about 482 MB), into `~/.cache/boson-video/models`. Your AI is told it is a
one-time wait. `uvx boson-video models` fetches them ahead of time; `BOSON_NO_DOWNLOAD=1` forbids
downloads.

## The video's page in the chat

In apps that support [MCP Apps](https://modelcontextprotocol.io/docs/extensions/apps) (Claude
Desktop, claude.ai, ChatGPT, Cursor, VS Code), `video_open` also shows the video's page in the
chat: the same page as `boson-video web`. It has the player, the ribbon (hover for that second's
frame and words), the readout, and the Summary, Transcript, Terms, Scenes and Ask tabs, in the
original, both or English. It fills itself in as the video is read. **Full view** opens it over
the whole window.

- Your AI still answers. A question typed on the page, or a suggested one, goes to the chat as
  your next message with the video and the second you're at, and your AI answers with the tools.
  Nothing extra runs and no key is needed; it's your usual subscription.
- With no writing key there is no summary, English or terms on the page: one click asks your AI
  to write them in the chat.
- The page gets its data from three tools only it can call (`page_document`, `page_picture`,
  `page_sheet`); apps hide them from the model. It loads YouTube's player and nothing else from
  outside; frames and sheets come from the plugin.
- A video file shows its pictures and words, but doesn't play inside the chat.
- In a terminal (Claude Code, Codex) nothing changes: the AI gets the same text as before.

## How the intelligence works

Three jobs, done by different hands:

| Job | Who does it | What it costs |
| --- | --- | --- |
| **Sense:** the scene map, the transcript, full-resolution frames, the text on screen | This package, on your computer: storyboards and ffmpeg, Apple's transcriber or SenseVoice and Parakeet, RapidOCR | Nothing: no keys, no servers |
| **Judge:** is this claim supported by what was said and shown? | Code always compares the numbers; Jev judges the meaning when `TYPESAFE_API_KEY` is set | Nothing without the key |
| **Speak:** explain, summarize, answer, teach | **Your own AI** (Claude, GPT, whatever runs in your app) | Your usual AI plan |

So no writing model of ours runs in the plugin. Your AI gets a briefing when it opens a video (what
it is, the chapters, what the picture does, how to cite), then decides what to read: a stretch of the
transcript, the frames where something new appears (it sees them as images), a search, a check.
It answers you in its own words, and every claim carries the second it came from, so you can click
through and see for yourself. Text from the video is marked as the video's content, never as
instructions to your AI.

**In web apps (ChatGPT, claude.ai, Grok).** These call the plugin from their own servers, so it
needs a public address. Run it over HTTP and put a tunnel in front; videos are still downloaded
and read on this computer.

```bash
uv run boson-video mcp --http                    # prints http://127.0.0.1:8766/mcp/<secret>
ngrok http 8766                                  # or: cloudflared tunnel --url http://127.0.0.1:8766 (no account)
```

Give the app `https://<tunnel address>/mcp/<secret>` with no sign-in. The secret path is the only
lock: anyone with the full address can use the tools and make this computer download videos, so
stop the tunnel when you're done (delete `~/.boson-video/remote-token` for a new address).

| App | Where to add it | Notes (from their docs, 2026-10-05) |
| --- | --- | --- |
| ChatGPT | Settings → Security and login → Developer mode; then chatgpt.com/plugins → + → URL, no authentication; in a chat, + → Developer mode → pick it | Plus, Pro and up, web only. Images from tools may not reach the model, so each frame's caption carries its screen text |
| claude.ai | Customize → Connectors → Add custom connector → URL → No sign-in; in a chat, + → Connectors | All plans (Free: one connector). Frames reach the model; 240 s per call |
| Grok | grok.com/connectors → New Connector → Custom → URL | Must be a public address |

Videos are kept in one place for the command line, the page and the plugin:
`BOSON_VIDEO_HOME`, by default `~/.boson-video`. Keys are read from the project's `.env`.
`uv run python scripts/mcp_smoke.py <video> [--no-keys]` runs the plugin the way an AI app
does and calls every tool. The format of `timeline.json` is in
[timeline-format.md](timeline-format.md).
