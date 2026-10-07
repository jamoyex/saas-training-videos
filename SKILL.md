---
name: saas-training-videos
description: >-
  Plan and produce narrated, screen-recorded training videos (courses, tutorials, how-tos, onboarding walkthroughs) for
  any web app or SaaS product, with any AI agent. Covers course and video planning from the real screens, a human
  operator signing in for authenticated recording sessions, scripted repeatable takes with the Playwright CLI (real
  Chrome, saved login, pointer log), narration written to the footage, human-sounding voiceovers (ElevenLabs v4 with
  soft breaths, OpenAI TTS, or a human recording aligned with Whisper), click-to-word sync, a drawn cursor with zooms,
  and a 1080p −16 LUFS MP4. Use when asked to plan or make a training course or video of a web app, record a
  walkthrough or demo, re-shoot after a UI change, pick or audition a narration voice, or sync narration with footage.
license: MIT
compatibility: >-
  Agent-agnostic (any agent that can run shell commands: Codex, Claude Code, Gemini CLI, Cursor, Copilot, Goose, Aider…).
  Needs macOS or Linux with Python 3.10+, ffmpeg, Node.js + @playwright/cli and Google Chrome with a display (Xvfb on
  servers). Optional: ElevenLabs/OpenAI API keys, whisper.cpp. Chat-only assistants can use the method and write the files.
metadata:
  version: "1.1.0"
  repository: https://github.com/jamoyex/saas-training-videos
---

# SaaS Training Videos

A method and toolkit for training videos of **any** web app: plan the course from the real screens, let a human operator
sign in once, record scripted takes in a real browser, write the narration to the footage, voice it with a natural
TTS or human voice, and edit with a human-looking cursor, zooms and pacing that beginners can follow.
App-agnostic and agent-agnostic: nothing here assumes a particular product, brand, presenter, voice, or AI agent. The
scripts are plain command-line tools; any agent with a shell (or a person) can run them. Per-agent setup:
`docs/agents.md`.

```
PLAN            intake → course plan → (approve) → per video: explore → brief
SIGN IN         human operator logs in once per account (pw_record.py login); the agent never handles credentials
RECORD          takes (Playwright steps files) → tighten → click list + contact sheet
WRITE           narration to the footage (structure + human-sounding TTS text)
VOICE           audition → choose → speak (ElevenLabs v4 / OpenAI / human) → gap check → fix words
EDIT            EDL (sync anchors, cursor, zooms, close still) → assemble
QA + HAND-OFF   checklist → deliver → log account changes
```

## Read the right guide

| Stage | Guide |
|---|---|
| Plan a course / a video, generate the content | `references/planning.md` · `templates/course_plan.md` · `templates/video_brief.md` |
| How a video and a course are structured; project folders | `references/video-structure.md` |
| Human operator login, SSO/2FA, sessions, account prep | `references/authentication.md` |
| Record or re-shoot takes (steps files, helpers, iframes, pitfalls) | `references/recording.md` · `templates/take_example.js` |
| Write the narration | `references/narration.md` · `templates/script_template.md` |
| Make the voice sound human (ElevenLabs v4, `[inhales]`, settings, TTS text) | `references/human-voiceover.md` |
| Choose / audition / produce a voice (any provider, human narration) | `references/voices.md` |
| Sync, cursor, zooms, assembly | `references/editing.md` · `templates/edl_example.json` |
| Check before hand-off | `references/qa.md` |
| See it end to end | `examples/todomvc/` (public demo app, no login) |

## Setup (once per machine)

```
brew install ffmpeg whisper-cpp            # (Linux: apt install ffmpeg; whisper.cpp from source) — whisper is optional
npm i -g @playwright/cli                   # + Google Chrome installed
pip3 install numpy pillow                  # cursor overlay and QA tools
```
Keys go in a `.env` (project) or `~/.training-video.env`, never in committed files: `templates/config.example.env`.

## The workflow (one course, one video at a time)

1. **Intake + course plan** (`planning.md`): audience, outcome, app/account, demo data, voice, never-on-camera list →
   modules and videos with one-sentence outcomes → user approves. Pick a **pilot** video.
2. **Operator sign-in** (`authentication.md`): `python3 scripts/pw_record.py login <profile> <login-url> --until "/dashboard"`,
   tell the operator what to do, confirm with `pw_record.py status <profile>`. One profile per account; it persists.
3. **Explore + brief** (`planning.md` §3): walk the task in the recording browser (screenshots/snapshots), cancel without
   saving, write `brief.md`: start state, click path with exact labels, segments (one take each, 20–90 s), account changes.
4. **Takes** (`recording.md`): `screen/steps/<SEG>.js` with `setup()` (start state, not recorded) and `take()` (one helper
   call per action the narration will name, each waiting on the page). Get the operator's OK for takes that change data.
   `python3 scripts/pw_record.py take <profile> screen/steps/S01.js screen/raw/S01.webm` → footage + pointer log + QA line.
5. **Tighten + read**: `python3 scripts/tighten.py screen/raw/S01.webm screen/tight/S01.mp4 --log screen/raw/S01.pointer.json`,
   `python3 scripts/pointer_events.py . S01` (click times), `python3 scripts/contact_sheet.py … --out sheet.jpg`.
6. **Script** (`video-structure.md`, `narration.md`, `human-voiceover.md`): open → steps (where → what → why → result) →
   recap → close, written to the footage, name each click just before it, TTS-ready text, soft `[inhales]` at topic shifts.
7. **Voice** (`voices.md`): audition 2–4 voices on a real segment, get the choice approved once per course, then
   `python3 scripts/voiceover.py speak script.md --provider elevenlabs --model eleven_v4 --voice <id> --stability 0.35 --speed 0.95 --out vo`.
8. **EDL + gaps** (`editing.md`): sync anchors (footage time → phrase), cursor + zooms (video px = page px × 1.5), a close
   still. `python3 scripts/voice_gaps.py edl.json` → add a few words where the screen needs time → re-voice that segment.
9. **Assemble**: `python3 scripts/assemble_video.py edl.json` (`--preview` first; `--only S03` after one fix).
10. **QA + hand-off** (`qa.md`): contact sheet, zoom frames, Whisper check (no tag spoken), −16 LUFS, no private data;
    deliver with the agreed name; log what the takes changed in the account in `CHANGELOG.md`.

## Rules that keep videos good

- **Plan from the real screens**; every label in the script must match the UI. Don't invent features, prices or results.
- **Footage at real speed; the audio is never edited.** Slow steps get room from a few more natural words.
- **Say it, then do it**: each click lands ~0.25 s after the phrase that names it (the assembler does this).
- **Human-sounding voice comes from the writing**: conversational sentences, punctuation as breath, rare tags
  (soft `[inhales]`, never stacked pause tags), stability ~0.35, speed ~0.95.
- **Wait on the page** (a locator that proves it's ready), never on fixed seconds alone. One glide per pointer step.
- **The human operator owns the account**: they sign in, approve data changes, and handle anything paid or identity-related.
  Never buy, pay, delete, or message real people on camera; stop at the confirm button and narrate.
- **Privacy**: only the recorded page is captured; demo data only; blur the signed-in user's personal details; keep login
  profiles and keys out of projects and repos.
- **Re-shoots are cheap**: a take is a script; after a UI change, fix the locator and re-run one command.

## Files

| Path | Purpose |
|---|---|
| `scripts/pw_record.py` | recorder: `login` (operator sign-in, `--until`), `status`, `open` (viewport, scale, fake mic), `take`, `cli`, `close` |
| `scripts/tighten.py` | idle cuts + timing map, for every take |
| `scripts/pointer_events.py` | a take's clicks/hovers on the tight-clip timeline (for sync anchors) |
| `scripts/voiceover.py` | `voices` / `audition` / `speak` / `align` / `say` — ElevenLabs (v4), OpenAI, macOS say, human audio |
| `scripts/voice_gaps.py` | footage-vs-voice time between anchors, before assembling |
| `scripts/assemble_video.py` | EDL → final MP4 (sync, pacing, cursor, zooms, PiP, transitions, intro/outro, loudnorm) |
| `scripts/cursor_overlay.py` | draws the cursor, click rings, gestures and zooms (called by the assembler) |
| `scripts/sync_tools.py` · `scripts/contact_sheet.py` | QA: clicks vs words; timestamped frame grids |
| `scripts/make_cursors.py` | draws `assets/cursors/` (original artwork) |
| `scripts/fallback/` | macOS window recorder + `recording_mode.js` presets, for agents driving the user's own Chrome via an extension |
| `scripts/package_skill.py` | builds `dist/saas-training-videos.zip` for skill uploads (ChatGPT, Claude.ai) |
| `templates/` | course_plan, video_brief, take_example.js, script_template, edl_example.json, config.example.env |
| `examples/todomvc/` | worked example on a public demo app |
