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

1. **Speed.** The map in about 1 s (measured). The full page in about 15 s for a
   25-minute video (a target, not yet measured). Time every stage, and say which numbers
   are measured and which are estimates.
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
| 2 | Words: Chinese and English transcripts on the Mac, lined up with the scenes | Next, waiting for the download OK | Accuracy and speed measured on real videos |
| 3 | Read view: sections written and checked, ask box, ribbon | | The target design works on the reference videos |
| 4 | Layouts by kind of video | | Each kind renders its own layout |
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

## Not now

Accounts, a mobile app, live streams, sites other than YouTube.

## Open decisions (owner)

- Downloads for milestone 2: yt-dlp (3.2 MB, from PyPI) and Apple's Chinese speech model
  (macOS downloads it and shows the size once asked).
- The language of the summary for Chinese videos: Chinese, English, or both.

## Facts to build on (checked 2026-09-24 to 2026-09-30)

- YouTube from a script: the watch page works; caption downloads come back empty; the
  internal player API refuses scripted clients. Don't try to get around these checks.
- Storyboard thumbnails are 320×180, one every 2 s on short videos and 10 s on long ones.
  Slide titles are readable after 3× enlargement; body text and numbers are not, so
  numbers need full-resolution frames.
- Anything on screen for less than the thumbnail interval can be missed entirely.
