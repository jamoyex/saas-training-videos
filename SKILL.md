---
name: saas-training-videos
description: >-
  Make narrated screen-recorded training videos (tutorials, how-tos, onboarding walkthroughs) for any web app or SaaS
  product. Records scripted, repeatable takes with the Playwright CLI (real Chrome, saved login, pointer log), draws a
  human-looking cursor with click rings and zooms in the edit, generates narration with any voice (ElevenLabs incl. your
  own clones and the voice library, OpenAI TTS, macOS say, or a human recording aligned with Whisper), syncs each click
  to the word that names it, and assembles a 1080p, −16 LUFS MP4. Use when asked to record a walkthrough, demo, tutorial
  or training video of a web app, to re-shoot a step after a UI change, to pick or audition a narration voice, or to
  sync narration with screen footage.
---

# SaaS Training Videos

A method and toolkit for training videos of **any** web app: the agent drives a real browser through scripted takes, the
footage is cut and paced to a natural narration, and the edit adds the cursor, zooms and polish a human editor would.
App-agnostic: nothing here assumes a particular product, brand, presenter or voice.

```
script ──► takes (Playwright) ──► tighten ──► voice (any provider) ──► EDL (sync + cursor + zooms) ──► assemble ──► QA
```

## When to read what

| Task | Read |
|---|---|
| Set up a new machine / app | §Setup below, then `references/recording.md` §1 |
| Record or re-shoot a take | `references/recording.md` (profiles, steps files, helpers, iframes, pitfalls) |
| Write the narration | `references/narration.md` (writing to be spoken, pacing with words, tags) |
| Choose or audition a voice | `references/voices.md` (providers, auditions, settings, human narration) |
| Sync, cursor, zooms, assemble | `references/editing.md` (EDL, anchors, zoom coordinates, transitions, presenter PiP) |
| Check the result | `references/qa.md` (checklist + the tools that check each item) |
| See it end to end | `examples/todomvc/` (public demo app: steps, script, EDL) |

## Setup (once per machine)

```
brew install ffmpeg whisper-cpp            # whisper only needed to align voices without timings / human narration
npm i -g @playwright/cli                   # + Google Chrome installed
pip3 install numpy pillow                  # used by the cursor overlay and QA tools
python3 scripts/make_cursors.py            # (re)draws assets/cursors/ — already included
```
Keys go in a `.env` (project) or `~/.training-video.env`, never in files you commit: see `templates/config.example.env`.

## The workflow (one video)

1. **Plan** the video as segments (one per screen task, 20–90 s each) in `script.md` (`templates/script_template.md`).
   Decide the demo data first: fake names, `example.com` emails, `555-01xx` phone numbers. Never real customer data.
2. **Profile + login**: `python3 scripts/pw_record.py login <app> <login-url>`. The USER signs in (2FA too). The agent
   never types passwords. One profile per app account; it persists.
3. **Explore** the screens before scripting a take: `pw_record.py cli <app> snapshot | screenshot --filename=… | eval …`.
   Cancel anything you open while exploring; don't save.
4. **Write a take** per segment: `screen/steps/<SEG>.js` from `templates/take_example.js`. `setup()` = start state
   (not recorded); `take()` = one helper call per action the narration will name, each waiting for the page, not a clock.
5. **Record**: `python3 scripts/pw_record.py take <app> screen/steps/S01.js screen/raw/S01.webm` → footage + timing
   sidecars + pointer log; it prints every click and a QA line. Look at a contact sheet before moving on.
6. **Tighten**: `python3 scripts/screen_capture.py tighten screen/raw/S01.webm screen/tight/S01.mp4 --fps 30 --keep 60
   --log screen/raw/S01.pointer.json` (add `--cut A-B` for blank page loads). List clicks on the tight timeline with
   `python3 scripts/pointer_events.py . S01`.
7. **Narrate**: write the segment's words to match the footage (`references/narration.md`), pick a voice
   (`references/voices.md`), then `python3 scripts/voiceover.py speak script.md --provider … --voice … --out vo`.
8. **EDL**: one screen segment per take, `sync` anchors (footage time → phrase), `cursor` with zooms
   (`references/editing.md`). Check gaps first: `python3 scripts/voice_gaps.py edl.json`; fix "NEED +Xs" by adding a
   few words to the script and re-voicing that segment only.
9. **Assemble**: `python3 scripts/assemble_video.py edl.json` (`--preview` for a fast 540p draft, `--only S03` after
   editing one segment). The pacing report tells you where the voice still leaves the screen short.
10. **QA** (`references/qa.md`): contact sheet, cursor/zoom spot-checks, Whisper transcript (no tag read aloud),
    loudness −16 LUFS, no private data on screen. Then hand off.

## Rules that keep videos good

- **Footage at real speed; the audio is never edited.** Slow steps get room from the narration (a few more natural
  words), never from fast-forwarding the screen or cutting silence into the voice.
- **Say it, then do it**: each click lands ~0.25 s after the phrase that names it (the assembler does this).
- **One glide per step**: the drawn cursor turns each logged move into one human movement.
- **Wait on the page** (a locator that proves it's ready), never on fixed seconds alone.
- **Takes that change data**: get the user's OK for what will be created/changed in the account; never buy, pay,
  delete or send to real people on camera; stop at the confirm button and narrate it instead.
- **Privacy**: only the recorded page is captured (no other tabs/apps); blur names/emails that the app shows about the
  signed-in user; keep login profiles out of projects and repos.
- **Re-shoots are cheap**: a take is a script. After a UI change, fix the locator and re-run one command.

## Files

| Path | Purpose |
|---|---|
| `scripts/pw_record.py` | Playwright recorder: profiles/login, open (viewport, scale, fake mic), take, cli passthrough |
| `scripts/screen_capture.py` | `tighten` (idle cuts + timing map) for every take; browser-extension fallback recorder (macOS) |
| `scripts/recording_mode.js` | fallback only: hides an extension's overlays and logs the pointer |
| `scripts/pointer_events.py` | a take's clicks/hovers on the tight-clip timeline (for sync anchors) |
| `scripts/voiceover.py` | voices / audition / speak / align / say — ElevenLabs, OpenAI, macOS say, human audio |
| `scripts/voice_gaps.py` | footage-vs-voice time between anchors, before assembling |
| `scripts/assemble_video.py` | EDL → final MP4 (sync, pacing, cursor, zooms, PiP, transitions, intro/outro, loudnorm) |
| `scripts/cursor_overlay.py` | draws the cursor, click rings, gestures and zooms (called by the assembler) |
| `scripts/sync_tools.py` | QA: did each click land on its phrase? |
| `scripts/contact_sheet.py` | timestamped frame grid of any clip |
| `scripts/make_cursors.py` | draws `assets/cursors/` (original artwork) |
| `templates/` | take_example.js, script_template.md, edl_example.json, config.example.env |
| `examples/todomvc/` | worked example on a public demo app |
