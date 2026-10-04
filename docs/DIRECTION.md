# Boson-Video direction

Agreed with the owner on 2026-10-02. Read this before building anything. Keep the
milestone table current as work lands; change the direction itself only with the owner.

## What we are building

**Read any video like a document.** Within seconds, one page shows what is in a video,
where, and why it matters, and every line links to the second it came from.

- **For:** people who learn from long videos in Chinese or English: tech talks,
  lectures, finance commentary. The first user is the owner.
- **The page is the product.** Scene detection, transcripts and models exist to feed it.

## The core screen

Target design: [read-view.html](read-view.html). Open it in a browser. It is also
published at https://claude.ai/artifact/4KTYhto8fKhLPptrokXyUn (owner-only). Its ribbon
uses real data from Karpathy's talk; the section text and the search are illustrative.

Top to bottom:

1. **Ribbon:** the whole video on one strip, with the most-replayed curve, scene or slide
   changes, and chapters (later also importance). Hover, drag or use the arrow keys to
   see the frame and the words at that second.
2. **Read view:** sections (chapters, or detected topic changes) of a few sentences each.
   Every sentence carries its timestamp and is checked against the transcript before it
   is shown. A key frame appears only where the picture adds information.
3. **Ask box:** a question returns the exact moments; a click opens the video there.

The layout follows the kind of video (`scenes.profile` decides):

| Kind | Layout | Reference video |
| --- | --- | --- |
| Talking head | Reads like an article | `9JKT5rBbrwM`: one shot fills 97%, no captions |
| Slide talk | Slide deck with speaker notes | `zjkBMFhNj_g`: 59 slides, 21 chapters |
| Tutorial | Numbered steps and code | none yet |
| Fast cuts | Contact sheet of shots | `dQw4w9WgXcQ`: 87 shots in 3:33 |

## Principles

1. **Speed.** The map in about 1 s, the full read view in about 15 s for a 25-minute
   video (both measured: 1.4 s and 14.4 s with the audio cached). Time every stage, and
   say which numbers are measured and which are estimates.
2. **Evidence.** No sentence on the page without the timestamp it came from.
3. **Local first.** It runs on the owner's Mac. Every model sits behind a small interface
   so it can be swapped.
4. **Quality is measured, not assumed:** transcript accuracy against human captions,
   missed visuals against a one-frame-per-second pass, numbers on screen against
   full-resolution frames.

## Milestones

| # | Milestone | Status | Done when |
| --- | --- | --- | --- |
| 1 | Map: link or file → scene timeline page | Done, 2026-09-24 | About 1 s; the 3 reference videos come out right |
| 2 | Words: Chinese and English transcripts on the Mac, lined up with the scenes | Done, 2026-10-02 | Measured: 25 min of Chinese in 13.8 s end to end; 5.3% character errors (Mandarin TEDx), 10.0% word errors (English TED, about half fillers the captions omit) |
| 3 | Read view: sections written and checked, ask box, ribbon | Done, 2026-10-02 | Works on all four test videos: live ribbon, summary in the video's language with an English switch, every sentence checked, in-page search, `boson-video ask` (asking inside the page needs a server, so it comes with the extension) |
| 3b | Learn from it: the video beside the page, transcript line by line in English, terms glossed and explained, asking inside the page (`boson-video serve`), questions saved | In progress, 2026-10-04 | Works on `qbReD1cGykQ` (Chinese, 11:35) on Windows: words in 10 s with SenseVoice |
| 4 | Layouts by kind of video | After 3b | Each kind renders its own layout |
| 5 | A library of many videos, then the Chrome extension | | |

## Who does what

- **Code** owns the order of steps. This is a workflow, not an agent: the steps are known
  in advance, so they can run in parallel.
- **Apple's on-device transcriber** (SpeechAnalyzer) makes the transcripts. On the
  owner's M5 it ran at 80× real time in one stream and 196× with the audio split into 8
  pieces (clean synthetic English; real speech not yet tested). It supports Mandarin and
  Cantonese once macOS has downloaded the model.
- **Mercury** (Inception, text) writes the sections, streamed.
- **Jev** (TypeSafe, text only, typed answers) checks each sentence against the
  transcript and finds the moments for the ask box. It is not a gate in front of the writer.
- **Backups only:** SenseVoice and Gemini, if Apple's transcriber disappoints on real
  speech. A vision model for charts and diagrams comes later.
- **An agent loop** only for open-ended follow-up questions, using the timeline as its tools.

## Quality bars

Each needs a number we track; "today" is as of 2026-10-02.

| Bar | Measured as | Today |
| --- | --- | --- |
| Faithful | Share of summary sentences that fail the check | 4 of 75 flagged on four videos, mostly real writer slips (a son's age given to his girlfriend); planted errors caught 10 of 10, true sentences accepted 13 of 13 |
| Complete | Chapter starts, "most replayed" peaks and points from human summaries that the page covers | Not measured |
| Names and numbers right | Errors in names, tickers and figures | Names fixed by the writer from the video's own name list; numbers checked in code |
| Fast | Time to first view, time to full read view | 1.4 s and 14.4 s (25-minute video, audio cached) |
| Findable | Ask lands within 10 s of the right moment | 4 of 4 spot checks right, including "not in this video" |
| Sees the screen | Numbers and code read from full-resolution frames | Slide titles only |

## Research directions

1. **How few frames are enough:** our scene-map frames against evenly spaced frames at the
   same token budget, on public long-video question benchmarks (Video-MME, LongVideoBench).
2. **A small judge deciding where to look:** Jev picking the moments worth a vision model,
   against a large model doing the same, by cost and accuracy.
3. **Verified summaries:** how often summaries invent things, with and without checks.
4. **Names in mixed-language speech:** fixing names from the video's own text, scored by name
   error rate before and after.
5. **Claims over time:** predictions pulled from videos with timestamps, checked later
   against what happened: a channel's track record.

## Not now

Accounts, a mobile app, live streams, sites other than YouTube.

## Decisions (owner)

- 2026-10-02: downloads for milestone 2 approved: yt-dlp (from PyPI) and Apple's Chinese
  speech model. Test-video audio stays in `out/`, which git ignores.
- 2026-10-02: summaries are written in the video's language, with a one-click switch to
  English.
- 2026-10-04: product first. The owner learns from Chinese technical videos and needs the
  terms explained and questions answered, so milestone 3b (learning) comes before layouts.
  The bigger aim: a format any LLM can take a video in through (timeline.json today).
- 2026-10-04: downloads approved for the Windows PC: ffmpeg (scoop), SenseVoice int8 and the
  Silero voice detector (sherpa-onnx, about 165 MB in ~/.cache/boson-video/models).

## Facts to build on (checked 2026-09-24 to 2026-09-30)

- YouTube from a script: the watch page works; caption downloads come back empty; the
  internal player API refuses scripted clients. Don't try to get around these checks.
- Storyboard thumbnails are 320×180, one every 2 s on short videos and 10 s on long ones.
  Slide titles are readable after 3× enlargement; body text and numbers are not, so
  numbers need full-resolution frames.
- Anything on screen for less than the thumbnail interval can be missed entirely.
- Apple's transcriber on the owner's M5: about 200× real time with the audio cut at
  pauses into 8 pieces. Mandarin is good; English names inside Chinese speech come out
  garbled ("Money or Life" → "Monelife"). Hint words (`AnalysisContext.contextualStrings`)
  changed nothing, so milestone 3's writer gets the names from the title and description
  (`speech.names`) and spells them right.
- Audio downloads vary from 4 s to 18 s for the same 9 MB, and YouTube sometimes refuses
  a request. Starting speech-to-text while the audio is still arriving is the fix to try.
- Mercury writes a 25-minute video's summary in about 5 s and a 1-hour one in about 9 s,
  for well under a cent; about one reply in ten has the wrong shape (a list, or empty), so
  the writer retries once. Jev checks a summary in under a second.
- YouTube auto-dubs some videos: `qbReD1cGykQ` (Chinese) also offers an English dub, and
  yt-dlp's `worstaudio` picked it. The audio format now asks for the track marked "original".
- SenseVoice on a 12-thread Windows laptop (CPU): 11:35 of Mandarin in 10.0 s from cached
  audio (model load 1.2 s, voice detection 6.7 s with decoding overlapped). Decoding one
  stretch per thread beat batching (2.4 s against 4.1 s for 200 s of speech).
- Jev is weak at numbers (it let "3.21" become "5.21"), so numbers are compared in code by
  value ("2 million" = 2000000, 1亿 = 一亿) against the cited passages and their neighbours.
