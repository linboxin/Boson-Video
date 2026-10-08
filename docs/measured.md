# Measured

Every number here was measured on the run it names; estimates are labelled as such.

MacBook on a home connection, 2026-09-24, one run each (the YouTube page time
varies between runs, 0.4 to 1.2 s so far):

| Video | Length | Frames | Result | Page | Thumbnails | Decode | Scenes | Total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Money or Life 美股频道, "Muse 是否能让 Meta 在 AI 上咸鱼翻身？" | 24:53 | 151 | 3 scenes, one shot fills 97% | 0.93 s | 0.15 s | 0.12 s | 0.05 s | **1.26 s** |
| Andrej Karpathy, "Intro to Large Language Models" | 59:48 | 360 | 59 distinct slides, 21 chapters | 1.14 s | 0.15 s | 0.11 s | 0.16 s | **1.56 s** |
| Rick Astley, "Never Gonna Give You Up" | 3:33 | 108 | 87 shots, fast cutting | 0.48 s | 0.13 s | 0.07 s | 0.04 s | **0.73 s** |

Most of the time is YouTube building the watch page. In a browser extension that
page is already loaded, so the same result would take about 0.3 s.

## Words (2026-10-02, M5 MacBook)

| Video | Length | Language | Words ready | Download · prep · speech | Error rate against human captions |
| --- | --- | --- | --- | --- | --- |
| Money or Life 美股频道 (talking head) | 24:53 | Chinese | **13.8 s** (6.9 s with audio cached) | 4.6 · 1.5 · 6.0 s | no captions exist; Chinese is good, English names come out garbled |
| Andrej Karpathy, "Intro to Large Language Models" | 59:48 | English | **30.5 s** | 7.3 · 3.5 · 18.5 s | only automatic captions exist |
| Ken Robinson, "Do schools kill creativity?" (TED) | 20:06 | English | **9.9 s** | 2.8 · 1.1 · 5.1 s | **10.0% of words**; about half are filler words ("you know" alone: 38) that the human captions leave out |
| 陳永儀, TEDxTaipei | 14:29 | Chinese | **7.1 s** | 2.9 · 0.8 · 2.3 s | **5.3% of characters**; mostly look-alikes (裡/裏, 制/製) and sound-alikes (地/的) |

Speech runs at about 200× real time when the audio is cut into 8 pieces transcribed at
once (80× in one stream). "Words ready" counts from the start of the run. Scores come
from `scripts/accuracy.py`.

## Read view (2026-10-02)

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

## Learning from it (2026-10-04, Windows laptop, 12 threads, no GPU used)

`boson-video serve --open <video>` shows the page with the video playing beside it. The
transcript reads line by line with its English beneath; technical terms carry their English
above the characters and open a plain explanation; the ask box answers in the language you
ask in, citing the second, with general background kept apart. Questions are saved with the video.

| Video | Words (SenseVoice, audio cached) | Summary, English transcript, glossary, checks | Cost | Asking |
| --- | --- | --- | --- | --- |
| 程序员老王, "llm abliteration是什么？" (Chinese, 11:35) | **10.0 s** for 88 passages | **18–22 s** from start; 13–16 terms; 21–22 of 22–23 summary sentences checked ✓ | $0.0015 | 2.3–2.8 s per question; 3 of 3 spot checks right, including "not in this video" |

## The screen (2026-10-04, Windows laptop, CPU)

After the words, the frames at every new visual and build step are fetched at full resolution
and read by OCR (RapidOCR, local). Burned-in subtitles are kept apart; a build step keeps only
the lines it adds. The text goes into `timeline.json` (`screens`), the page's transcript, and the
plugin's reading, search and checks.

| Video | Moments read | Time | Result |
| --- | --- | --- | --- |
| 程序员老王, abliteration (Chinese, 11:35) | 88 | 54 s from scratch | Diagram labels and on-screen values (KL = 0.08, KL = 2.71); subtitles apart at 85 moments |
| Andrej Karpathy (English, 59:48) | 74 | 87 s (76 s of it seeking frames in the stream) | 19 of 20 hand-checked slides right, tables cell by cell; small text loses its spaces |

## Transcription off the Mac (2026-10-04, Windows laptop, 12 threads, CPU, audio cached)

Scored with `scripts/accuracy.py` against human captions (Chinese compared in simplified
characters on both sides).

| Video | Length | Model | Error rate | Words ready |
| --- | --- | --- | --- | --- |
| 陳永儀, TEDxTaipei (Chinese) | 14:29 | SenseVoice | **4.8% of characters** | 11.0 s |
| Ken Robinson, TED (English) | 20:06 | Parakeet | **10.5% of words** (fillers the captions omit included) | 26.9 s |
| Ken Robinson, TED (English) | 20:06 | SenseVoice | 58.6% of words | |
| Andrej Karpathy (English) | 59:48 | Parakeet | only automatic captions exist | 77 s |

## The product page's first videos (2026-10-06 and 2026-10-07, M5 MacBook)

| Video | Length | Scenes | Words (download · prep · speech) | Screen text | Summary (write · study · check) | Checked |
| --- | --- | --- | --- | --- | --- | --- |
| Money or Life 美股频道, "AI 加速药物研发" (Chinese, slides) | 28:24 | 1.13 s, 31 new visuals | 18.5 s (8.9 · 1.7 · 6.8 s) | 36 moments in 14.7 s of reading, after the Mac's ffmpeg was given certificates (0 before) | 69.0 s from start (7.6 · 40.3 · 0.6 s), $0.0034 with the English and terms | 15 of 16; rewritten with names from the screen: 15 of 15 |
| Sean's AI Stories, "AI Agent Observability & Eval" (English, screen recording) | 20:48 | 1.50 s, 18 new visuals | 13.2 s (3.5 · 1.2 · 7.0 s) | none: YouTube served only the first 5.8 MB of the 1080p stream, then 403 | 25.9 s from start (4.9 · 3.3 · 1.3 s), about $0.0014 | 23 of 26; one flag a real writer slip ("Sonnet 3.5" for what was said as "son 5.5"), one a false alarm |

A question in the product page ("What does Insilico Medicine use AI for, and how much time did it
save?") was answered in 2.9 s, both sentences checked, with three slides; on the English video,
"Which model was the slowest step using, and what did it cost?" in 6.0 s, 1 of 1 checked.
