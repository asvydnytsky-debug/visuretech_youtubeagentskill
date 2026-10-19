---
name: yt-voice
description: >-
  Turn a finished script into recorded voiceover with ElevenLabs - the
  spoken words only, cut at beat boundaries, one audio file per beat. Use
  when the user wants a voiceover, narration, a scratch read, a temp track,
  "read this out", "record this for me", or is editing and needs audio for a
  script they are not going to read on camera themselves. Needs an
  ElevenLabs API key; every other skill in this pack does not.
---

# yt-voice

A script into audio you can actually cut against.

One tool lives in this folder and it runs. Use it rather than writing your own request.

```bash
python3 narrate.py script.md --dry-run            # the plan, no key, no network, no spend
python3 narrate.py --voices                       # the voices on the account
python3 narrate.py script.md --voice <voice_id>   # synthesize
```

## This one costs money

Every other skill here is free and offline. This one bills characters to the user's ElevenLabs
account, so it has one rule the others do not need:

**Run `--dry-run` first and show the user the character count before you send anything.** The dry
run needs no key and makes no request. It prints the exact number of characters that would be
billed, the per-beat split, and the runtime estimate. Nothing goes to the API until the user has
seen that number and said go.

The key comes from `ELEVENLABS_API_KEY`, `XI_API_KEY` or `KEY`. Never ask the user to paste a key
into the chat, and never write one into a file in the repo.

## Before you synthesize

1. **Read `~/.claude/youtube/voice.md`.** It says how this person talks. A read in the wrong
   register is worse than no read, because they will hear it and not know why it is wrong. If the
   file says they appear on camera and swear, a clean corporate voice is the wrong pick and you
   should say so rather than quietly shipping it.
2. **Pick the voice with the user, not for them.** Run `--voices` and show the list. Without
   `--voice` the tool prints the plan and stops instead of guessing an id - leave it that way.
3. **Check the script is final.** Synthesizing a draft means paying twice.

## What the tool strips, and why it matters

`[ON SCREEN: ...]`, beat headers, timestamps, bullets, markdown and `**Hook**`-style labels all come
out before anything is billed. They are direction for the person holding the script. Left in, they
are characters you pay to hear read aloud - and `**Hook** (0:00-0:15)` comes back as a voice saying
"Hook".

`[PAUSE]` and `[PAUSE: 1.2]` survive as real pauses - they become `<break>` tags. A beat that is
nothing but a pause folds into the beat above it instead of becoming a separate file of silence.

## One file per beat

The split is at beat boundaries, never mid-sentence. That is deliberate:

- a line the user dislikes is one beat to redo, not the whole script
- the cuts already line up with the beats the script marked, so the editor's timeline matches
- prosody does not reset at the seams: each request carries the tail of the previous beat, the head
  of the next, and the previous request ids

## What to hand back

- the character count and what it cost, stated plainly
- the file list, with the per-beat runtime
- the `ffmpeg -f concat` line for one joined file, if they want one
- which voice and model were used, so the next run matches

## The limits, said out loud

**It is a scratch read until the user says otherwise.** A synthetic voice on a talking-head channel
reads as synthetic. It is good for temp tracks, b-roll narration, Shorts, and videos where nobody is
on camera. For a face-to-camera video, the user's own voice is the product.

**Disclosure is theirs to handle, not yours to skip.** If a published video uses a synthetic voice,
say in the handback that YouTube's altered-content disclosure may apply and let them decide.

**It never clones a voice.** It uses voices already on the account. If the user wants their own
voice, they set that up in ElevenLabs themselves, with their own consent, under their own account.

**It does not stitch or edit.** It writes mp3s and a `concat.txt`. The user runs ffmpeg, or drops
the files into their editor.

## The gate

Nothing here publishes. This skill records audio and the user publishes. Every run ends in the
character count, the file list, and the question: **ship it, or change it?**
