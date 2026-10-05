# Boson-Video direction

Agreed with the owner on 2026-10-02 and revised with the owner on 2026-10-04 (the plugin
direction). Read this before building anything. Keep the milestone table current as work
lands; change the direction itself only with the owner.

## What we are building

**Read any video like a document.** Boson-Video turns a video into a compact document in
which every line carries the second it came from: what was said, what was shown, and where.
Any AI then works from that document: the user's own Claude, ChatGPT or Cursor through a
plugin, or our own page.

- **For:** people who learn from long videos in a language they only half know: tech talks,
  lectures, finance commentary. They reach it through the AI they already use. The first
  user is the owner (Chinese technical and finance videos).
- **The document is the product.** The page and the plugin are two ways to read it. Scene
  detection, transcripts and models exist to feed it.
- **It works with no keys.** Someone who can't pay for Jev or a writing model still gets the
  document and the plugin; their own AI does the writing. Keys make it sharper, not possible.

Three layers, each with one job:

| Layer | Job | Who does it |
| --- | --- | --- |
| **Sense** | Hear and see the video: transcript, scene map, the right full-resolution frames, screen text | Local code and models, free (Apple's transcriber or SenseVoice, ffmpeg) |
| **Judge** | Decide and check: is this claim supported, which moment answers this, where to look, what kind of statement is it | Jev when there is a key; code checks always |
| **Speak** | Explain, answer, teach | The user's own AI in the plugin; a model of the user's choice for the page (Mercury today) |

## How people use it

1. **The plugin** (milestone 4): an MCP server, the standard that Claude, Cursor, Codex and
   ChatGPT use for tools. Opening a video returns a short briefing within seconds (title,
   length, language, chapters, what the picture does, whether the words are ready, how to
   cite); tools then read a stretch of the transcript, show frames at full resolution, search,
   and check a claim. Long work (download, transcription) runs in the background, so no tool
   call waits long. Claude can't take video, but it can take images, so the frame tool is how
   the user's AI sees the video.
2. **The page:** target design [read-view.html](read-view.html), also published at
   https://claude.ai/artifact/4KTYhto8fKhLPptrokXyUn (owner-only). The ribbon (the whole video
   on one strip: most-replayed curve, scene changes, chapters), the summary with every
   sentence linked and checked, the transcript line by line with English beneath and terms
   glossed, and the ask box (`boson-video serve`). Later the layout follows the kind of video
   (`scenes.profile` decides):

| Kind | Layout | Reference video |
| --- | --- | --- |
| Talking head | Reads like an article | `9JKT5rBbrwM`: one shot fills 97%, no captions |
| Slide talk | Slide deck with speaker notes | `zjkBMFhNj_g`: 59 slides, 21 chapters |
| Tutorial | Numbered steps and code | none yet |
| Fast cuts | Contact sheet of shots | `dQw4w9WgXcQ`: 87 shots in 3:33 |

## Principles

1. **Speed.** The map in about 1 s, the words and the read view within a minute for a
   35-minute video. Time every stage, and say which numbers are measured and which are
   estimates.
2. **Evidence.** No sentence without the timestamp it came from, in the page or in the plugin.
3. **Local first.** The engine runs on the user's computer. Every model sits behind a small
   interface so it can be swapped.
4. **Works without keys.** Jev and writing models are optional layers on a free engine.
5. **Every check says what checked it.** A ✓ from Jev, from a local model, from code, or from
   the user's own AI are different strengths, and the reader sees which one a line got. A ✓
   means "matches what was said or shown", not "true".
6. **Quality is measured, not assumed:** transcript accuracy against human captions, missed
   visuals against a one-frame-per-second pass, numbers on screen against full-resolution
   frames.

## Milestones

| # | Milestone | Status | Done when |
| --- | --- | --- | --- |
| 1 | Map: link or file → scene timeline page | Done, 2026-09-24 | About 1 s; the 3 reference videos come out right |
| 2 | Words: Chinese and English transcripts on the Mac, lined up with the scenes | Done, 2026-10-02 | Measured: 25 min of Chinese in 13.8 s end to end; 5.3% character errors (Mandarin TEDx), 10.0% word errors (English TED, about half fillers the captions omit) |
| 3 | Read view: sections written and checked, ask box, ribbon | Done, 2026-10-02 | Works on all four test videos: live ribbon, summary in the video's language with an English switch, every sentence checked, in-page search, `boson-video ask` |
| 3b | Learn from it: video beside the page, transcript with English beneath, terms glossed and explained, asking in the page, questions saved; SenseVoice off the Mac | Done, 2026-10-04 | `qbReD1cGykQ` (11:35) and `slFa9Vx3crw` (35:04) on Windows: words in 10 s and 25 s, full page in about 20 s and 50 s (audio cached) |
| 4 | **Plugin:** engine runs without keys; `timeline.json` versioned with a spec; MCP server with briefing, read, frames (full resolution), search, check; jobs in the background; Jev's first-option bias handled | Built, 2026-10-04; open: English off the Mac, Cursor | Claude Code explained `qbReD1cGykQ` from the plugin alone in 51 s, citing times and reading numbers shown only on screen. `slFa9Vx3crw` works through every tool. `zjkBMFhNj_g` with no keys: map in 10 s, words at 47 s, but SenseVoice's English is unusable (needs another model). Cursor not tried yet |
| 5 | **Judge:** check the English the reader sees; ranked check labels on every line; a local check model if it passes the planted-error test; Jev picks where to look; Jev's cost recorded | Next | Planted-error test passes for each checker; the label on every line is right |
| 6 | **Screen text:** OCR at the chosen frames; burned-in subtitles kept apart and used to correct and score the transcript | Needs the OCR model download | Slide text of `zjkBMFhNj_g` right on 20 hand-checked slides; SenseVoice's error rate measured against burned-in subtitles |
| 7 | Bring your own model for the page (any OpenAI-compatible endpoint: OpenAI, Gemini, Ollama, Mercury) | | The page builds with each of them |
| 8 | Hosted plugin (ChatGPT and other web apps) and the Chrome extension | | YouTube downloads stay on the user's side; the hosted part never downloads YouTube |
| 9 | Later: a library across videos, layouts by kind of video, creator tools | | |

## Who does what

- **Code** owns the order of steps. Boson-Video is a workflow, not an agent: the steps are
  known in advance, so they run in parallel. The agent is the user's AI, using the document
  through the plugin. Inside Boson-Video, loops stay small and bounded (look again when a
  check fails).
- **Apple's on-device transcriber** (SpeechAnalyzer) makes the transcripts on a Mac: 80× real
  time in one stream and about 200× with the audio cut into 8 pieces on the owner's M5.
- **SenseVoice** (through sherpa-onnx) makes them elsewhere: 11:35 of Mandarin in 10 s and
  35 minutes in 25 s on a 12-thread Windows laptop (CPU). Its error rate isn't measured yet.
- **Mercury** (Inception, text) writes the page's summary, English transcript and glossary.
  In the plugin the user's own AI writes instead.
- **Jev** (TypeSafe, text only, typed answers) judges and never writes. Today it checks each
  sentence against the transcript and finds the moments that answer a question. Next it
  chooses where to look (which moments deserve a full-resolution frame, which passages are
  garbled), labels statements (prediction, fact, opinion: the basis for track records), and
  screens video text before it reaches the user's AI (a video can carry instructions aimed at
  an AI). Jev's known weaknesses are handled in code: numbers, counting, dates, and a lean
  toward the option listed first.
- **Backups:** Gemini if a writing or vision model is needed. A local vision model was tried
  and is too slow on this hardware (see Facts).

## Quality bars

Each needs a number we track; "today" is as of 2026-10-04.

| Bar | Measured as | Today |
| --- | --- | --- |
| Faithful | Share of summary sentences that fail the check | 4 of 75 flagged on four videos (Apple transcripts), mostly real writer slips; 1 of 12 on `slFa9Vx3crw` (SenseVoice); planted errors caught 10 of 10, true sentences accepted 13 of 13 |
| Complete | Chapter starts, "most replayed" peaks and points from human summaries that the page covers | Not measured (`slFa9Vx3crw`'s summary skipped its first 3½ minutes) |
| Names and numbers right | Errors in names, tickers and figures | Names fixed by the writer from the video's own name list; numbers checked in code, including Chinese numerals as SenseVoice writes them |
| Fast | Time to first view, time to full read view | 1.4 s and 14.4 s (Mac, 25 min, audio cached); about 2 s and 50 s (Windows, 35 min, audio cached) |
| Findable | Ask lands within 10 s of the right moment | 7 of 7 spot checks right, including "not in this video" |
| Sees the screen | Numbers and code read from full-resolution frames | Slide titles only |
| Works without keys | What the plugin and page give with no `.env` | The plugin works fully (its AI writes); the page has scenes, words and search; checks fall back to numbers in code and say so |

## Research directions

1. **How few frames are enough:** our scene-map frames against evenly spaced frames at the
   same token budget, on public long-video question benchmarks (Video-MME, LongVideoBench).
2. **A small judge deciding where to look:** Jev picking the moments worth a vision model,
   against a large model doing the same, by cost and accuracy.
3. **Verified summaries:** how often summaries invent things, with and without checks, and
   with each checker (Jev, a local model, the writer's own AI).
4. **Names in mixed-language speech:** fixing names from the video's own text, scored by name
   error rate before and after.
5. **Claims over time:** predictions pulled from videos with timestamps, checked later
   against what happened: a channel's track record.

## The business, later

The plugin is free and spreads the format. Money could come later from Jev's sharper checking,
hosted processing, and **creator tools**: creators bring their own videos and get articles,
show notes, chapters and Chinese↔English versions, every line linked to its second (they own
the rights and have a reason to pay). Libraries of other people's videos, such as a channel's
predictions and whether they came true, depend on rights we don't have yet.

## Not now

Accounts, a mobile app, live streams, sites other than YouTube, and downloading YouTube
videos on our servers (bot checks and other people's rights).

## Decisions (owner)

- 2026-10-02: downloads for milestone 2 approved: yt-dlp (from PyPI) and Apple's Chinese
  speech model. Test-video audio stays in `out/`, which git ignores.
- 2026-10-02: summaries are written in the video's language, with a one-click switch to
  English.
- 2026-10-04: product first. The owner learns from Chinese technical videos and needs the
  terms explained and questions answered, so milestone 3b (learning) came before layouts.
- 2026-10-04: downloads approved for the Windows PC: ffmpeg (scoop), SenseVoice int8 and the
  Silero voice detector (sherpa-onnx, about 165 MB in ~/.cache/boson-video/models).
- 2026-10-04: **the plugin direction.** The owner can't run everyone on his own Jev and
  writing model, so the engine runs without keys and people plug it into their own AI. The
  owner first, then people who can't pay. Plugin before layouts.
- 2026-10-04: full-resolution frames approved: yt-dlp fetches only the needed seconds of
  video, at the moments the scene map picks; thumbnails remain the fallback.
- 2026-10-04: a hosted plugin is fine, as long as YouTube downloads happen on the user's side
  (their computer or their browser) or the video is the user's own file.
- 2026-10-04: the plugin's shape: a briefing on open, then tools to drill down (chosen by
  Claude under the owner's hand-off; the owner can overturn it).

## Facts to build on (checked 2026-09-24 to 2026-10-04)

- YouTube from a script: the watch page works; caption downloads come back empty; the
  internal player API refuses scripted clients. Don't try to get around these checks.
- YouTube auto-dubs some videos: `qbReD1cGykQ` (Chinese) also offers an English dub, and
  yt-dlp's `worstaudio` picked it. The audio format asks for the track marked "original".
- Storyboard thumbnails are 320×180, one every 2 s on short videos and 10 s on long ones.
  Slide titles are readable after 3× enlargement; body text and numbers are not, so
  numbers need full-resolution frames. Anything on screen for less than the thumbnail
  interval can be missed entirely.
- On `slFa9Vx3crw` the scenes the map calls "repeat" really are the same picture (the same
  chart, table and post shown again), so skipping them loses nothing. On `qbReD1cGykQ` the
  "changes" inside a scene are real build steps of animated diagrams (89 frames in 11.6 min),
  and the video has Chinese subtitles burned into the picture.
- Apple's transcriber on the owner's M5: about 200× real time with the audio cut at
  pauses into 8 pieces. Mandarin is good; English names inside Chinese speech come out
  garbled ("Money or Life" → "Monelife"). Hint words (`AnalysisContext.contextualStrings`)
  changed nothing, so the writer gets the names from the title and description
  (`speech.names`) and spells them right.
- SenseVoice writes English words in capitals and spoken numbers in Chinese characters
  (十八点三, 二零二六, 幺); the code lower-cases the first and reads the second. Decoding one
  stretch of speech per thread beat batching (2.4 s against 4.1 s for 200 s of speech), and
  voice detection on 8 pieces at once took 35 minutes from 9.7 s to 4.0 s.
- Audio downloads vary from 4 s to 18 s for the same 9 MB, and YouTube sometimes refuses
  a request. Starting speech-to-text while the audio is still arriving is the fix to try.
- Mercury writes a 25-minute video's summary in about 5 s and a 1-hour one in about 9 s,
  for well under a cent; about one reply in ten has the wrong shape (a list, a bare list of
  sections, or empty), so the writer retries once and accepts a bare list of sections.
  Jev checks a summary in about a second (once 10 s).
- Jev is weak at numbers (it let "3.21" become "5.21"), so numbers are compared in code by
  value ("2 million" = 2000000, 1亿 = 一亿, 十八点三 = 18.3) against the cited passages and
  their neighbours. Jev also leans toward the option listed first (TypeSafe's own list of
  jev-1.13's weaknesses); both "not in this video" questions on 2026-10-04 named 0:01 as the
  top moment.
- Claude takes images (JPEG, PNG, GIF, WebP), not video: up to 20 images per message on
  claude.ai, 100 or 600 per API request. Claude Code caps an MCP tool's result at 25,000
  tokens by default (`MAX_MCP_OUTPUT_TOKENS`). Third-party products may not offer claude.ai
  login or subscription limits (Agent SDK docs); a plugin the user adds to their own AI is
  the allowed route.
- A transcript costs roughly 14k tokens per hour per language as compact lines (estimate,
  not Claude's tokenizer); Gemini reading video directly uses roughly 1M per hour.
- SenseVoice int8 (2025-09-09) garbles English whatever the settings (language en or auto,
  punctuation on or off): letters drop and Chinese numerals slip in ("ABUT SXH 零" for "about
  6,000"). Candidates through sherpa-onnx: Parakeet TDT 0.6B v2 int8 (482 MB, English only),
  Moonshine base English (111 MB), or the older SenseVoice int8 (163 MB). Needs the owner's OK.
- Full-resolution frames from YouTube: yt-dlp gives the video-only stream address and ffmpeg
  reads one frame per needed second from it: 3 frames in 3.5–8 s including the address, about
  20–125 KB each at 1280 px.
- Claude Code with only the plugin (2026-10-04, `qbReD1cGykQ`): 8 turns in 51 s; it read the
  section, looked at the scene map's frames, then at exact moments, and checked two of its own
  claims before answering.
- The local qwen3.5 (9.7B, vision) took 64 s to describe one chart thumbnail on the RTX 4050
  (6 GB) and misread the chart; too slow and too vague to be the vision step here.
