# Boson-Video direction

Agreed with the owner on 2026-10-02 and revised with the owner on 2026-10-04 (the plugin
direction) and on 2026-10-05 (cost follows states; the moment). Read this before building
anything. Keep the milestone table current as work lands; change the direction itself only
with the owner.

## What we are building

**Read any video like a document.** Boson-Video turns a video into a compact document in
which every line carries the second it came from: what was said, what was shown, and where.
Any AI then works from that document: the user's own Claude, ChatGPT or Cursor through a
plugin, or our own page.

- **For:** people who learn from long videos in a language they only half know: tech talks,
  lectures, finance commentary. They reach it through the AI they already use. The first
  user is the owner (Chinese technical and finance videos).
- **The document is the product, with two ways in.** The website: anyone pastes a video link
  and reads it. The plugin: any AI or agent (Claude, ChatGPT, Cursor, Codex, Grok) connects
  and reads the same document. Scene detection, transcripts and models exist to feed it.
- **It works with no keys.** Someone who can't pay for Jev or a writing model still gets the
  document and the plugin; their own AI does the writing. Keys make it sharper, not possible.
- **Cost follows states, not runtime.** Visual complexity K is the number of distinct
  pictures, not the length in seconds. Speech complexity S is the words, not the silence.
  Sharp frames, OCR, and what a model is shown cost on the order of K + S. An hour-long talk
  with about 70 visual states is a document of those states. A montage's K is its shot count,
  and it does not compress the same way.

**Where people stop.** People learn from the document without sitting through the runtime,
until the second they came for still has to be watched: a derivation, a demo, a number the page
got wrong or never captured. Past that point the tool is a slower way to find the playhead, and
pasting the link into a model that can see video is easier. So the document says where it
can't carry the video before the reader finds out (trajectory and seek moments, "better watched
than read" in the plugin's briefing), puts the player at that second, and keeps the original
line with English beneath it beside the player. One wrong number costs more trust than a missing
one, so screen text is for finding and the frame is what gets cited. The test is on questions
people actually ask: how many are answered right without watching; when watching was needed,
whether the tool said so first and landed within 10 s; and the same questions put to a video
model given the link, as the baseline.

**The moment is the unit.** One moment is a span of time: the words said then, which of the
four picture codes applies, the lines new since the previous moment, and the frame. Search,
checks, and the page all point at that same moment. Passages, scenes, and screens stay the
measurements the moment is built from. OCR text is for search. The frame is what gets read.

| Code | When | What is stored |
| --- | --- | --- |
| State | The picture holds | One frame, and how long it lasted |
| Delta | A slide build, a board, or code appearing | The base frame, plus each new line |
| Trajectory | The motion is the content | Samples along the path, or a short clip |
| Seek | That code is not enough | The original range |

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
2. **The website** (`boson-video serve`): paste a YouTube link on the front page; the page
   opens once the scene map is ready (seconds) and fills in as the words, the screen and the
   summary arrive. It runs on the user's computer, so YouTube downloads stay on their side; a
   hosted version waits for the Chrome extension (milestone 9). Each video's page: target design
   [read-view.html](read-view.html), also published at
   https://claude.ai/artifact/4KTYhto8fKhLPptrokXyUn (owner-only). The ribbon (the whole video
   on one strip: most-replayed curve, scene changes, chapters), the summary with every
   sentence linked and checked, the transcript line by line with English beneath and terms
   glossed, and the ask box (`boson-video serve`). Later the layout follows the kind of video
   (`scenes.profile` decides; see the table below).
3. **The product page** (`boson-video web`, from 2026-10-06): an invite-only site with a new,
   simpler design and no product name. Paste a YouTube link or drop a video file; each video
   gets one page: the player, the ribbon (hover for that second's frame and words) and a
   readout on one side; Summary, Transcript, Terms, Scenes and Ask in tabs on the other, in the
   original, both or English. On a server, uploads work and YouTube links come through the
   browser extension (milestone 9). Items 2 and 3 were built in parallel on 2026-10-06 and do
   the same job; which one stays is the owner's call.

Layouts by kind of video, for later:

| Kind | Layout | Reference video |
| --- | --- | --- |
| Talking head | Reads like an article | `9JKT5rBbrwM`: one shot fills 97%, no captions |
| Slide talk | Slide deck with speaker notes | `zjkBMFhNj_g`: 59 slides, 21 chapters |
| Tutorial | Numbered steps: a delta per new line, the frame beside it | none yet |
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
   frames. Cost is plotted against K and S, not against runtime alone.
7. **Represent change, not time.** A stable picture is one state. New ink is a delta. Motion
   that carries the idea is a trajectory or a clip. Anything the code cannot hold is a seek
   back to the original second.

## Milestones

| # | Milestone | Status | Done when |
| --- | --- | --- | --- |
| 1 | Map: link or file → scene timeline page | Done, 2026-09-24 | About 1 s; the 3 reference videos come out right |
| 2 | Words: Chinese and English transcripts on the Mac, lined up with the scenes | Done, 2026-10-02 | Measured: 25 min of Chinese in 13.8 s end to end; 5.3% character errors (Mandarin TEDx), 10.0% word errors (English TED, about half fillers the captions omit) |
| 3 | Read view: sections written and checked, ask box, ribbon | Done, 2026-10-02 | Works on all four test videos: live ribbon, summary in the video's language with an English switch, every sentence checked, in-page search, `boson-video ask` |
| 3b | Learn from it: video beside the page, transcript with English beneath, terms glossed and explained, asking in the page, questions saved; SenseVoice off the Mac | Done, 2026-10-04 | `qbReD1cGykQ` (11:35) and `slFa9Vx3crw` (35:04) on Windows: words in 10 s and 25 s, full page in about 20 s and 50 s (audio cached) |
| 4 | **Plugin:** engine runs without keys; `timeline.json` versioned with a spec; MCP server with briefing, read, frames (full resolution), search, check; jobs in the background; Jev's first-option bias handled | Done, 2026-10-04 (Cursor still untried). Packaged 2026-10-08: `uvx boson-video mcp` on a fresh machine, no Node, ffmpeg or keys; published the same day: PyPI `boson-video` 0.2.0 and the MCP Registry (`io.github.linboxin/boson-video`, active); the repo is public, MIT | Claude Code explained `qbReD1cGykQ` from the plugin alone in 51 s, citing times and reading numbers shown only on screen. `slFa9Vx3crw` works through every tool. `zjkBMFhNj_g` with no keys: map in 10 s, English words by Parakeet in 77 s, numbers in claims found by the free check |
| 5 | **Judge:** check the English the reader sees; ranked check labels on every line; a local check model if it passes the planted-error test; Jev picks where to look; Jev's cost recorded | After the product (owner, 2026-10-06) | Planted-error test passes for each checker; the label on every line is right |
| 6 | **Screen text:** OCR at the chosen frames; burned-in subtitles kept apart and used to correct and score the transcript | Done, 2026-10-04 (correcting the transcript from subtitles: later) | 19 of 20 hand-checked slides of `zjkBMFhNj_g` read right (one small-print paragraph garbled; small text loses its spaces). `qbReD1cGykQ`'s subtitles land apart at 85 of 88 moments. SenseVoice differs from them on 14.4% of characters (an upper bound: OCR errors and script-vs-speech differences included); against human captions it scores 4.8% |
| 6b | **Product page:** an invite-only page per video in a new design, no product name: a link or an uploaded file in; the ribbon with a frame preview at any second; Summary, Transcript, Terms, Scenes and Ask tabs; the original, both or English everywhere | In progress, 2026-10-07: runs on this computer (`boson-video web`), checked on three videos at desktop and phone size; hosting next | Invited people use it on a server: uploads there, YouTube links through the extension (milestone 9) |
| 7 | **Moment:** one object joins the words, the picture code, the new lines, and the frame; the four codes (state, delta, trajectory, seek) | Done, 2026-10-06 (the summary still cites passages, not moments: next) | `qbReD1cGykQ`: 90 moments (22 state, 44 delta, 24 trajectory: its animated chat demos and diagrams). KL = 2.71, shown and never said, comes back as the delta at 9:15 with its frame. Search, check, frame captions and the page cite that same moment. On six videos, a run of changes with no text on screen (a speaker at a podium) stays state and delta; `slFa9Vx3crw`'s scrolled article (21:50–23:20) is a trajectory, "better watched than read" |
| 8 | Bring your own model for the page (any OpenAI-compatible endpoint: OpenAI, Gemini, Ollama, Mercury) | Started 2026-10-09: `llm.py` takes any OpenAI-compatible endpoint by configuration; only Mercury tested | The page builds with each of them |
| 9 | Hosted plugin (ChatGPT and other web apps) and the Chrome extension | | YouTube downloads stay on the user's side; the hosted part never downloads YouTube |
| 10 | Later: a library across videos, layouts by kind of video, creator tools | | After one lecture can be retrieved as moments |

## Who does what

- **Code** owns the order of steps. Boson-Video is a workflow, not an agent: the steps are
  known in advance, so they run in parallel. The agent is the user's AI, using the document
  through the plugin. Inside Boson-Video, loops stay small and bounded (look again when a
  check fails).
- **Apple's on-device transcriber** (SpeechAnalyzer) makes the transcripts on a Mac: 80× real
  time in one stream and about 200× with the audio cut into 8 pieces on the owner's M5.
- **SenseVoice** (through sherpa-onnx) makes them elsewhere for Chinese and other non-English
  speech: 4.8% character errors on the Mandarin TEDx talk; 11:35 in 10 s and 35 minutes in 25 s
  on a 12-thread Windows laptop (CPU).
- **Parakeet** (TDT 0.6B v2, through sherpa-onnx) makes English transcripts off the Mac: 10.5% word
  errors on the English TED talk (SenseVoice: 58.6%); 20 minutes in 27 s, an hour in 77 s.
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
| Faithful | Share of summary sentences that fail the check; the planted-error test (`scripts/planted_errors.py`) | 4 of 75 flagged on four videos (Apple transcripts), mostly real writer slips; 1 of 12 on `slFa9Vx3crw` (SenseVoice). Planted-error fixture, 28 cases on SenseVoice transcripts, mostly English claims (2026-10-04): Jev accepts 14 of 14 true and catches 13 of 14 planted (misses an entity swap, "Customer B" for A); code alone catches all 6 number and date errors and judges nothing else. The summary harness (2026-10-09, Mercury, six videos): 1 of 164 sentences failed, against 11 of 138 before |
| Complete | Chapter starts, "most replayed" peaks and points from human summaries that the page covers | Not measured (`slFa9Vx3crw`'s summary skipped its first 3½ minutes) |
| Names and numbers right | Errors in names, tickers and figures | Names fixed by the writer from the video's own name list and, since 2026-10-06, from the text on screen (`f4zGqjYWS_Q`: 因系智能, Pandomic and a garbled section title before; after, PandaOmics and Insilico Medicine right, one sentence still writes 因矽 for 英矽; not yet scored as a rate); numbers checked in code, including Chinese numerals as SenseVoice writes them |
| Fast | Time to first view, time to full read view; sharp work against K, not against runtime | 1.4 s and 14.4 s (Mac, 25 min, audio cached); about 2 s and 50 s (Windows, 35 min, audio cached). Cost against K is not measured yet |
| Findable | Ask lands within 10 s of the right moment | 7 of 7 spot checks right, including "not in this video" |
| Answered without watching | Of real questions (the ones saved in `notes.json`), the share answered right with no playback; when watching was needed, whether the tool said so first; the same questions to a video model given the link, as the baseline | Not measured |
| Sees what changed | Visual states the scene map misses against a one-frame-per-second pass | Not measured (thumbnails every 10 s on long videos can miss anything shorter) |
| Sees the screen | Numbers and code read from full-resolution frames | Screen text in `timeline.json` at every new visual and build step: 19 of 20 Karpathy slides right, tables included (Chatbot Arena leaderboard read cell by cell); on-screen numbers like KL = 0.08 / 2.71 are searchable and checkable |
| Works without keys | What the plugin and page give with no `.env` | The plugin works fully (its AI writes); the page has scenes, words and search; checks fall back to numbers in code and say so |

## Research directions

1. **Cost follows K + S:** on the same questions, three ways of choosing frames: the scene-map
   states; the same number of evenly spaced frames (the control: does the map pick better
   frames, or only fewer?); and a one-frame-per-second pass. Accuracy is plotted against cost
   across several budgets, and against K and S, with runtime only as a label (Video-MME,
   LongVideoBench). A method that spends in proportion to the runtime on a video whose K is a
   few dozen has missed the structure.
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
- 2026-10-04: the owner handed all four follow-ups to Claude ("you should handle it all"),
  which covers the two downloads they needed: Parakeet for English (about 480 MB) and an OCR
  model for screen text.
- 2026-10-04: the plugin's shape: a briefing on open, then tools to drill down (chosen by
  Claude under the owner's hand-off; the owner can overturn it).
- 2026-10-05: **cost follows states.** The owner adopted the complexity claim: sharp work is
  on the order of K + S, not a frame per second. The moment is the next structural milestone,
  ahead of bring-your-own-model. A picture span is one of four codes: state, delta,
  trajectory, seek. The library and other verticals stay later, after one lecture can be
  retrieved as moments and a visual fact that was never spoken still comes back with its frame.
- 2026-10-06: **two products, one document.** The website is a product in its own right:
  anyone pastes a video link and reads it. The plugin is the same document for any AI or agent
  that connects. The website runs on the user's computer (`boson-video serve`) because YouTube
  downloads stay on the user's side; a hosted website waits for the Chrome extension. The owner's
  stop point ("Where people stop", above) is the product's test.
- 2026-10-06: **product first.** An invite-only web version comes before milestone 5: invite
  codes, no accounts; videos come in as YouTube links or uploaded files (on a server, YouTube
  links come through the extension, milestone 9, as decided on 2026-10-04). It is built as
  `boson-video web`, beside the paste-a-link website `boson-video serve` above.
- 2026-10-09: **Mercury stays the writer** (it is the cheapest), and the harness must make any model
  write well, so a better model later makes the page better without code changes; nothing in the
  code is tied to one vendor. Summaries are judged by measurement and by the owner, blind.
- 2026-10-08: **publish the plugin; the repo goes public, MIT licensed.** "Just connect" means
  the installed plugin first (`uvx boson-video mcp`, listed in the MCP Registry as
  `io.github.linboxin/boson-video`): it runs on the user's computer, so YouTube works and it costs
  the owner nothing. The connect-by-address plugin for web apps follows the extension and accounts.
- 2026-10-06: a new interface for it: simple, no product name on the page, not packed;
  chat-based, answering with good-looking output. Making the plugin show visuals inside
  ChatGPT and Grok comes later.

## Facts to build on (checked 2026-09-24 to 2026-10-08)

- A stranger's computer, tested 2026-10-08 with the built package in a fresh home, no Node, no
  ffmpeg on the PATH and no keys: yt-dlp needs a JavaScript runtime for YouTube, so the package
  brings Deno (`deno` on PyPI) and the challenge solver (`yt-dlp[default]`), and ffmpeg comes from
  `imageio-ffmpeg`. On the Mac, Apple's transcriber was built from scratch and had the words of a
  3:33 video 9.9 s after the start. On the local-model path (forced), SenseVoice's 166 MB downloaded
  in 17 s on first use and an 11:35 Chinese video had its words in 24.1 s; the plugin told the AI
  it was a one-time wait. The test found one first-run bug (the home folder didn't exist yet) and
  it is fixed.
- The static ffmpeg build on the owner's Mac finds no certificates of its own, so reading
  YouTube's stream failed ("certificate verify failed") and every frame quietly fell back to a
  thumbnail: no screen text on the Mac until `frames.py` handed it certifi's bundle (2026-10-06).

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
- Asking Jev each question twice with the options reversed made no difference on the planted-error
  fixture (13 of 14 caught either way); it is kept because it costs no wait and TypeSafe
  recommends it. Numbers now match by the claim's precision: "468,532" exactly, "25.2" within
  0.05, a rounded "6,000" within a thousand (a flat 1% let a planted 468,532 pass for 486,532).
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
  6,000"), 58.6% word errors on a TED talk. Parakeet TDT 0.6B v2 int8 (482 MB) gets 10.5% on the
  same talk, so English goes to Parakeet. It writes punctuation and digits, but glues some names
  ("Lama 270D" for Llama 2 70B).
- Full-resolution frames from YouTube: yt-dlp gives the video-only stream address and ffmpeg
  reads one frame per needed second from it: 3 frames in 3.5–8 s including the address, about
  20–125 KB each at 1280 px.
- Since 2026-10-07 YouTube can refuse that stream: on `YkhmBOctzWE` it served only about the first
  5.8 MB of a 117 MB 1080p stream (roughly the first minute) and answered 403 to every byte range
  past it, with or without a browser User-Agent, while `f4zGqjYWS_Q` had read fine the day before.
  This looks like YouTube's bot check (what yt-dlp calls a PO token), which we don't get around, so
  such a video gets thumbnails and no screen text, and the command line now says why. Frames read
  in the user's browser (the extension) are the way through.
- Claude Code with only the plugin (2026-10-04, `qbReD1cGykQ`): 8 turns in 51 s; it read the
  section, looked at the scene map's frames, then at exact moments, and checked two of its own
  claims before answering.
- Screen reading (RapidOCR, PP-OCR models, CPU): about 0.45 s a frame in one worker; more
  workers were slower on this laptop (94 frames: 42 s with one, 53 with three, 75 with six).
  Reading overlaps fetching: 88 moments of `qbReD1cGykQ` in 54 s from scratch, 74 of
  `zjkBMFhNj_g` in 87 s, where seeking in an hour-long stream is the slow part (76 s). OCR runs
  in a worker process so its onnxruntime never meets sherpa-onnx's.
- The local qwen3.5 (9.7B, vision) took 64 s to describe one chart thumbnail on the RTX 4050
  (6 GB) and misread the chart; too slow and too vague to be the vision step here.
