# The plugin

`boson-video mcp` is an MCP server, the standard Claude Code, Claude Desktop, Cursor and Codex
use for tools. Your AI opens a video, reads the transcript, looks at the frames that matter at
full resolution, searches, and checks a claim before stating it. It works with no keys; your
AI does the writing. With `TYPESAFE_API_KEY`, checks come from Jev and search adds Jev's pick.

| Tool | What your AI gets |
| --- | --- |
| `video_open(video)` | A briefing within seconds: length, language, chapters, what the picture does, the summary and key terms if built, how to go on. A new video builds in the background (the map in about 2 s, the words in 10–50 s) |
| `video_read(video, start, end, lang)` | Timed lines, `[m:ss] original // English`, and each picture change as a moment (`state`, `delta`, `trajectory`, or `seek`) with the lines new on screen; `video_frames` shows its frame. Up to about 12k tokens a reply |
| `video_frames(video, at \| start–end)` | 6 frames by default, up to 12, full resolution, at the new visuals the scene map found (or exact moments), each citing the moment and what was said then |
| `video_search(query, video?)` | Where something is said or shown, in one video or all of them. A hit on the picture cites the same moment as `video_read` |
| `video_check(video, claim, at)` | The claim against what was said and shown at those moments, and which checker judged it |
| `video_list()` | The videos opened so far |

Claude Code:

```bash
claude mcp add boson-video -- uv --directory /path/to/Boson-Video run boson-video mcp
```

Claude Desktop (`claude_desktop_config.json`) or Cursor (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "boson-video": {
      "command": "uv",
      "args": ["--directory", "/path/to/Boson-Video", "run", "boson-video", "mcp"]
    }
  }
}
```

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
