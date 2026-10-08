# How it works

1. **One page request.** The watch page holds the title, duration, caption tracks,
   chapters, the most-replayed heatmap and the *storyboard spec*.
2. **Storyboards.** These are the thumbnails YouTube shows when you hover over the
   seek bar, already rendered for every video: 320×180, one every 2 s (short
   videos) to 10 s (long ones), nine to a JPEG sheet. A one-hour video is 40
   sheets (~1 MB), fetched in parallel over one HTTP/2 connection that was opened
   while the page was still loading.
3. **Scenes, without a model** ([scenes.py](../src/boson_video/scenes.py)). The frames are
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
   a small Swift tool, [bv_speech.swift](../src/boson_video/bv_speech.swift)) transcribes
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
