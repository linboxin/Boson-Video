# Boson-Video

Read any video like a document. Boson-Video turns a YouTube link (or a video file) into a
document where every line carries the second it came from. Two ways in: **the website**, where
you paste a link and read (`boson-video serve`, on your computer), and **the plugin**, which
lets your own AI or agent read the same document (no keys needed). Each video's page fills in
as each stage finishes:

1. **Scenes, in about a second:** every new visual and when it appears, the shots that keep
   coming back, the chapters and YouTube's "most replayed" curve, on a ribbon you drag to
   see the frame and the words at any second.
2. **Every word that was said,** transcribed on your Mac and filed under its scene.
3. **A summary in the video's language** (with an English switch) where every sentence links
   to its second and is checked against the transcript, plus search over what was said.

```bash
uv sync
uv run boson-video "https://www.youtube.com/watch?v=zjkBMFhNj_g" --open
uv run boson-video ~/Movies/lecture.mp4
uv run boson-video 9JKT5rBbrwM --lang zh_CN     # speech language; guessed from the title otherwise
uv run boson-video 9JKT5rBbrwM --no-words       # scenes only
uv run boson-video ask zjkBMFhNj_g "how much does it cost to train llama 2?"   # → 5:20
uv run boson-video serve --open qbReD1cGykQ    # the page with the video beside it, and asking
uv run boson-video serve --open                # the website: paste a YouTube link on the front page
```

**The website.** `boson-video serve` serves 127.0.0.1:8765. Paste a YouTube link on the front
page: the video's page opens once the scene map is ready (seconds), and fills in by itself as
the words, the screen text and the summary arrive. It is the same background build the plugin
uses, so a video opened in one is ready in the other. It listens only on your computer; YouTube
downloads stay on your side.

Each run writes `~/.boson-video/<video id>/index.html` (one self-contained file) and
`timeline.json` (frames, scenes, chapters, heatmap, transcript and timings, for the
stages that come next). The page is written twice: with the scenes, then with the words.
The words use Apple's on-device transcriber on a Mac (macOS 26 and Xcode's command line
tools; built on first use), and SenseVoice elsewhere (models in `~/.cache/boson-video/models`). The summary needs `INCEPTION_API_KEY` (Mercury writes it) and
`TYPESAFE_API_KEY` (Jev checks it and answers `ask`) in `.env`.

## The product (invite-only, in progress)

One page per video, built for reading and asking. On the left, the player, the ribbon (most
replayed, scenes by kind, chapters; hover anywhere to see that second's frame and words) and a
readout of what is being said. On the right, in tabs: the summary (frames for each section, every
sentence timed and marked ✓ ? ✗), the transcript (terms glossed above the words, screen text and
chapters in between, search, follows the video), the terms, every scene with its build steps and
what was said, and Ask, which answers with the moments and frames it rests on. Everything shows in
the original, in English, or both.

```bash
uv run boson-video web                      # http://127.0.0.1:8770; the first run prints your invite code
uv run boson-video invite "a friend"        # a new code (10 new videos and 100 questions a day)
uv run boson-video invite --list            # codes and what each has opened · --revoke CODE stops one
```

Paste a YouTube link or drop a video file (up to 2 GB, `BOSON_UPLOAD_MAX_MB`). Each code sees
only the videos it opened and its own questions. On a server, run it with `--hosted`: YouTube
links are refused there (YouTube downloads stay on the user's side; the browser extension will
bring them), uploads still work. Asking needs both keys in `.env`.

## In your own AI (the plugin)

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
[docs/timeline-format.md](docs/timeline-format.md).

## Measured

MacBook on a home connection, 2026-09-24, one run each (the YouTube page time
varies between runs, 0.4 to 1.2 s so far):

| Video | Length | Frames | Result | Page | Thumbnails | Decode | Scenes | Total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Money or Life 美股频道, "Muse 是否能让 Meta 在 AI 上咸鱼翻身？" | 24:53 | 151 | 3 scenes, one shot fills 97% | 0.93 s | 0.15 s | 0.12 s | 0.05 s | **1.26 s** |
| Andrej Karpathy, "Intro to Large Language Models" | 59:48 | 360 | 59 distinct slides, 21 chapters | 1.14 s | 0.15 s | 0.11 s | 0.16 s | **1.56 s** |
| Rick Astley, "Never Gonna Give You Up" | 3:33 | 108 | 87 shots, fast cutting | 0.48 s | 0.13 s | 0.07 s | 0.04 s | **0.73 s** |

Most of the time is YouTube building the watch page. In a browser extension that
page is already loaded, so the same result would take about 0.3 s.

### Words (2026-10-02, M5 MacBook)

| Video | Length | Language | Words ready | Download · prep · speech | Error rate against human captions |
| --- | --- | --- | --- | --- | --- |
| Money or Life 美股频道 (talking head) | 24:53 | Chinese | **13.8 s** (6.9 s with audio cached) | 4.6 · 1.5 · 6.0 s | no captions exist; Chinese is good, English names come out garbled |
| Andrej Karpathy, "Intro to Large Language Models" | 59:48 | English | **30.5 s** | 7.3 · 3.5 · 18.5 s | only automatic captions exist |
| Ken Robinson, "Do schools kill creativity?" (TED) | 20:06 | English | **9.9 s** | 2.8 · 1.1 · 5.1 s | **10.0% of words**; about half are filler words ("you know" alone: 38) that the human captions leave out |
| 陳永儀, TEDxTaipei | 14:29 | Chinese | **7.1 s** | 2.9 · 0.8 · 2.3 s | **5.3% of characters**; mostly look-alikes (裡/裏, 制/製) and sound-alikes (地/的) |

Speech runs at about 200× real time when the audio is cut into 8 pieces transcribed at
once (80× in one stream). "Words ready" counts from the start of the run. Scores come
from `scripts/accuracy.py`.

### Read view (2026-10-02)

| Video | Read view ready | Written (Mercury) | Checked (Jev) | Sentences confirmed | Cost |
| --- | --- | --- | --- | --- | --- |
| Money or Life 美股频道 (Chinese, 24:53) | **13.7 s** (audio cached) | 6.1 s | 0.5 s | 13 / 13 | $0.0006 |
| Ken Robinson, TED (English, 20:06) | **12.1 s** | 4.2 s | 0.8 s | 22 / 25 | $0.0006 |
| 陳永儀, TEDxTaipei (Chinese, 14:29) | **11.2 s** | 5.9 s | 0.5 s | 14 / 14 | $0.0004 |
| Andrej Karpathy (English, 59:48) | **33.0 s** | 8.9 s | 0.7 s | 22 / 23 | $0.0015 |

Is the check real? On the 美股频道 summary, ten sentences with one planted error each (bought
for shorted, 740 → 640, 3.21 → 5.21, the US → China, a friend → himself…) were all
caught, and the thirteen true ones all passed. Among real summaries the flags were mostly
real slips, such as giving Ken Robinson's son's age to the son's girlfriend.

### Learning from it (2026-10-04, Windows laptop, 12 threads, no GPU used)

`boson-video serve --open <video>` shows the page with the video playing beside it. The
transcript reads line by line with its English beneath; technical terms carry their English
above the characters and open a plain explanation; the ask box answers in the language you
ask in, citing the second, with general background kept apart. Questions are saved with the video.

| Video | Words (SenseVoice, audio cached) | Summary, English transcript, glossary, checks | Cost | Asking |
| --- | --- | --- | --- | --- |
| 程序员老王, "llm abliteration是什么？" (Chinese, 11:35) | **10.0 s** for 88 passages | **18–22 s** from start; 13–16 terms; 21–22 of 22–23 summary sentences checked ✓ | $0.0015 | 2.3–2.8 s per question; 3 of 3 spot checks right, including "not in this video" |

### The screen (2026-10-04, Windows laptop, CPU)

After the words, the frames at every new visual and build step are fetched at full resolution
and read by OCR (RapidOCR, local). Burned-in subtitles are kept apart; a build step keeps only
the lines it adds. The text goes into `timeline.json` (`screens`), the page's transcript, and the
plugin's reading, search and checks.

| Video | Moments read | Time | Result |
| --- | --- | --- | --- |
| 程序员老王, abliteration (Chinese, 11:35) | 88 | 54 s from scratch | Diagram labels and on-screen values (KL = 0.08, KL = 2.71); subtitles apart at 85 moments |
| Andrej Karpathy (English, 59:48) | 74 | 87 s (76 s of it seeking frames in the stream) | 19 of 20 hand-checked slides right, tables cell by cell; small text loses its spaces |

### Transcription off the Mac (2026-10-04, Windows laptop, 12 threads, CPU, audio cached)

Scored with `scripts/accuracy.py` against human captions (Chinese compared in simplified
characters on both sides).

| Video | Length | Model | Error rate | Words ready |
| --- | --- | --- | --- | --- |
| 陳永儀, TEDxTaipei (Chinese) | 14:29 | SenseVoice | **4.8% of characters** | 11.0 s |
| Ken Robinson, TED (English) | 20:06 | Parakeet | **10.5% of words** (fillers the captions omit included) | 26.9 s |
| Ken Robinson, TED (English) | 20:06 | SenseVoice | 58.6% of words | |
| Andrej Karpathy (English) | 59:48 | Parakeet | only automatic captions exist | 77 s |

## How it works

1. **One page request.** The watch page holds the title, duration, caption tracks,
   chapters, the most-replayed heatmap and the *storyboard spec*.
2. **Storyboards.** These are the thumbnails YouTube shows when you hover over the
   seek bar, already rendered for every video: 320×180, one every 2 s (short
   videos) to 10 s (long ones), nine to a JPEG sheet. A one-hour video is 40
   sheets (~1 MB), fetched in parallel over one HTTP/2 connection that was opened
   while the page was still loading.
3. **Scenes, without a model** ([scenes.py](src/boson_video/scenes.py)). The frames are
   2 to 10 s apart, so motion can't be seen, only its result. The main signal is
   the *still-pixel change*. First the tool learns which pixels normally stay
   put in this particular video, then it asks what fraction of them clearly
   changed. A host's gestures or a speaker's webcam box sit in pixels that always
   move, so they don't count. A new slide rewrites pixels that never move, so it
   does. Scenes that look alike share a *look*. A look that fills most of the
   video, or keeps coming back, is the *base shot* (the host, the podcast camera).
4. **Page.** Frames are drawn straight from the sheets with CSS offsets: nothing
   is re-encoded, and the file works offline.

Local files take the same path. ffmpeg decodes only keyframes (`-skip_frame nokey`),
keeps one frame every 2 s or more, and packs them into sheets of its own.

5. **Words.** yt-dlp downloads only a low-bitrate audio track (about 9 MB for 25
   minutes). ffmpeg turns it into 16 kHz mono and finds the pauses; the audio is cut at
   pauses into up to 8 pieces, and Apple's on-device transcriber (SpeechAnalyzer, run by
   a small Swift tool, [bv_speech.swift](src/boson_video/bv_speech.swift)) transcribes
   them all at once. Each passage lands in the scene row it was said in.
6. **Summary.** Mercury (Inception's diffusion model) gets the transcript as compact
   numbered lines, the chapters and the names the video writes itself (title, channel,
   description), and returns a strict JSON summary in the video's language with an English
   version, every sentence citing the passages it rests on. Speech recognition garbles
   English names inside Chinese ("Monelife"); the name list lets the writer spell them right.
7. **Checks.** Jev (TypeSafe) judges each sentence against its cited passages and their
   neighbours: supported, contradicted or says nothing. Numbers are checked in code by
   value, because Jev is weak at them; a neighbouring passage that holds a number joins the
   sentence's citations.
8. **Ask.** `boson-video ask` follows TypeSafe's line-search recipe: one Choice over passage
   ids plus a Noul for "is it answered at all?", in two passes for transcripts longer than
   255 passages.

## What YouTube allows (checked 2026-09-24 and 2026-10-02)

- **Captions:** the page lists the caption tracks, but downloading one from a
  script returns HTTP 200 with an empty body, because the real player sends a
  token. The tool shows which languages exist and doesn't download them.
- **Internal player API:** it answers in ~170 ms, but it refuses scripted clients
  ("UNPLAYABLE", "Sign in to confirm you're not a bot"), so the watch page is
  the dependable source.
- **Some videos have no captions at all**, like the 美股频道 video above. A
  summarizer that only reads transcripts has nothing to work with there.
- **Audio downloads vary.** The same 9 MB took 4 s when YouTube offered a plain audio
  file and 18 s when it only offered streaming segments, and a request was sometimes
  refused (so the download retries once). Starting speech-to-text while the audio is
  still arriving is the planned fix.

## Where it's going

The goal is to read any video like a document: one page with a scrubbable ribbon, short
sections where every sentence links to its second, and an ask box. The agreed direction,
milestones and open decisions are in [docs/DIRECTION.md](docs/DIRECTION.md), and the
target screen is [docs/read-view.html](docs/read-view.html).

Milestones 1 (scenes), 2 (words), 3 (read view) and 3b (learning) are done. Milestone 4,
the plugin, is in progress: the engine runs without keys and any MCP app can read a video.
Layouts by kind of video come later.

## Tests

```bash
uv run pytest            # offline: parsing, sheet slicing, scenes and audio cutting on synthetic media, the page, scoring
uv run pytest -m live    # hits YouTube and runs Apple's transcriber
uv run python scripts/accuracy.py snZ811wvjjw zh-TW zh_TW   # score a transcript against human captions
```

## Limits

- This is a personal research prototype. YouTube's terms don't allow automated
  access for products, which is one more reason the extension is the plan for
  anything shared.
- Storyboard frames are small. They show *what's on screen and when*, not small
  text. That is what the full-resolution step is for.
- Live streams aren't supported. Private and age-restricted videos fail with
  YouTube's own reason.
- For local files, frames follow the encoder's keyframes, which can be 8 s or more
  apart in some files.
- English names inside Chinese speech come out garbled in the transcript ("Money or Life"
  became "Monelife"). Apple's transcriber ignored hint words; the summary spells them right
  from the video's own name list, but the transcript keeps the garbled form.
- Asking in your own words works from the command line, in the page when it is served
  (`boson-video serve`), and through the plugin.
- Off the Mac, English goes to Parakeet and everything else to SenseVoice, because SenseVoice
  garbles English (58.6% word errors on a TED talk, against Parakeet's 10.5%). Parakeet is the
  slower of the two: about a minute of decoding per hour of English on a 12-thread laptop.
