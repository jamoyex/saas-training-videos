# saas-training-videos

An agent skill for producing **narrated, screen-recorded training videos of any web app**: tutorials, how-tos,
onboarding walkthroughs, feature demos. The agent drives a real browser through scripted takes, records only the page,
narrates with the voice you choose, lands every click on the word that names it, draws a human-looking cursor with
click rings and zooms, and renders a 1080p MP4 at broadcast loudness.

![demo](docs/demo.gif)

*From `examples/todomvc/`: scripted take, drawn cursor (arrow / I-beam / hand), zoom on the field being typed.*

## What's in it

| Part | What it does |
|---|---|
| **Recorder** (`scripts/pw_record.py`) | Playwright CLI + real Chrome with a saved login per app. Takes are small JS files (`setup()` / `take()`) using human-paced helpers: `hover`, `click`, `type`, `press`, `smooth` scroll, `dismiss` popups, `clickAt`. 2560×1440 footage, a pointer log for the edit, automatic logging inside iframes, stray-mouse filtering, a fake microphone for voice/dictation features. Re-shooting after a UI change is one command. |
| **Voices** (`scripts/voiceover.py`) | ElevenLabs (your clones, account voices, or the shared library, with expressive tags), OpenAI TTS, macOS `say`, or a human recording. `voices` to search, `audition` to compare candidates on the same words, `speak` per segment, `align` for audio without timings (local Whisper). |
| **Editor** (`scripts/assemble_video.py` + `cursor_overlay.py`) | EDL-driven: phrase-anchored sync, real-speed footage with holds where the voice needs time, drawn cursor + click rings, phrase-timed zooms and gestures, stills, slides, presenter picture-in-picture, intro/outro and transition overlays, two-pass loudnorm to −16 LUFS. |
| **QA tools** | `voice_gaps.py` (footage vs voice timing before rendering), `sync_tools.py` (did clicks land on their words), `contact_sheet.py`, `pointer_events.py`. |
| **Method** (`SKILL.md`, `references/`) | The workflow and the rules learned the hard way: recording pitfalls, writing narration to be spoken, pacing with words instead of silence, voice selection, zoom coordinates, QA checklist. |

## Install

**Claude Code** (personal skill):
```bash
git clone https://github.com/jamoyex/saas-training-videos ~/.claude/skills/saas-training-videos
```
Other agents: point them at `SKILL.md` (it links to everything else); the scripts are plain Python 3 / Node CLI tools.

Requirements: macOS or Linux, Python 3.10+ (`pip install numpy pillow`), ffmpeg, Google Chrome,
`npm i -g @playwright/cli`. Optional: `whisper-cpp` + a ggml model (alignment), API keys for ElevenLabs/OpenAI
(`templates/config.example.env`).

## Quick start

```bash
S=~/.claude/skills/saas-training-videos/scripts
python3 $S/pw_record.py login myapp https://app.example.com/login       # you sign in, once
python3 $S/pw_record.py take  myapp screen/steps/S01.js screen/raw/S01.webm
python3 $S/screen_capture.py tighten screen/raw/S01.webm screen/tight/S01.mp4 --fps 30 --keep 60 --log screen/raw/S01.pointer.json
python3 $S/pointer_events.py . S01                                       # click times → EDL anchors
python3 $S/voiceover.py audition --voices VOICE_A VOICE_B --script script.md --seg S01
python3 $S/voiceover.py speak script.md --voice VOICE_A --out vo
python3 $S/voice_gaps.py edl.json
python3 $S/assemble_video.py edl.json
```
A complete worked example (public demo app, no login): `examples/todomvc/`.

## Principles

- Footage plays at real speed and the audio is never cut: slow steps get room from a few more natural words.
- Say it, then do it: each click lands just after its phrase.
- The agent never types passwords, never buys, deletes or messages real people on camera, and records only the page.
- Demo data only on screen; blur anything personal the app shows about the signed-in user.
- Only clone or imitate a real person's voice with their consent.

## License

No license file yet — add one (e.g. MIT) if you want others to reuse it.
