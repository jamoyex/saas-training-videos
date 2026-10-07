# AGENTS.md — saas-training-videos

Instructions for any AI agent (Codex, Cursor, Copilot, Gemini, Claude, Goose, Aider, …) working with this repository.

## What this is
An agent skill + toolkit for producing narrated, screen-recorded training videos of any web app. `SKILL.md` is the
entry point: read it first when asked to make, re-shoot, voice, sync or check a training video. It links to
`references/` (recording, narration, voices, editing, QA), `templates/`, and the worked example in `examples/todomvc/`.

## Commands
```
pip3 install numpy pillow && npm i -g @playwright/cli          # + ffmpeg, Google Chrome
python3 scripts/pw_record.py login|open|take|cli|close …         # record takes (see references/recording.md)
python3 scripts/tighten.py raw.webm tight.mp4 --log raw.pointer.json
python3 scripts/pointer_events.py <video-folder> <take ids>      # click times for EDL anchors
python3 scripts/voiceover.py voices|audition|speak|align|say …   # any voice provider (references/voices.md)
python3 scripts/voice_gaps.py edl.json                           # footage vs voice timing, before rendering
python3 scripts/assemble_video.py edl.json [--preview] [--only ID]
python3 scripts/sync_tools.py check edl.json out.mp4 .build/full # QA
python3 scripts/contact_sheet.py clip.mp4 --every 2 --out sheet.jpg
```
Every script has `--help`. Quick self-test (no login, no API key, macOS): the steps in `examples/todomvc/README.md`.

## Rules (safety and quality)
- Never type, request or store passwords, 2FA codes or API keys in files; the user signs in via `pw_record.py login`.
  Browser logins live in `~/.training-video/` and must never be copied into a project or committed.
- Never buy, pay, delete data, or send messages/emails to real people on camera. Stop at the confirm button and narrate.
- Get the user's OK before takes that create or change data in their account; log what changed.
- Demo data only on screen; blur anything personal the app shows about the signed-in user.
- Clone or imitate a real person's voice only with their consent.
- Footage at real speed; the audio is never edited. Give slow steps room with a few more narration words.

## Contributing to the toolkit
- Keep it agent-agnostic: plain CLIs, no dependency on a particular agent's tools or APIs. Agent-specific code (e.g.
  a browser extension's overlay selectors) goes behind a preset in `scripts/fallback/`.
- Keep dependencies light: Python stdlib + numpy/pillow, ffmpeg, Playwright CLI. Optional engines are detected at runtime.
- Don't commit media, logins or keys (`.gitignore` covers them). Update `SKILL.md`/`references/` when behaviour changes,
  and bump `metadata.version` in `SKILL.md`.
- Test changes on `examples/todomvc` (record → tighten → voice with `--provider say` → assemble) before pushing.
