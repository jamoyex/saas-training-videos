# Using this skill with any agent

The skill follows the open **Agent Skills** format (a folder with `SKILL.md` + `scripts/`, `references/`, `assets/`),
and the repo also has an **`AGENTS.md`** for agents that read that convention. The tools are plain CLI programs
(Python 3, Node, ffmpeg): any agent that can run shell commands on a machine with Chrome can do the whole pipeline.
Agents without a shell can still follow the method, write the files, and hand you the commands.

| Agent | How to install | Can it run everything? |
|---|---|---|
| **OpenAI Codex CLI / IDE** | `git clone https://github.com/jamoyex/saas-training-videos ~/.codex/skills/saas-training-videos` | Yes (local shell) |
| **ChatGPT** (Skills in Business/Enterprise/Edu workspaces) | Upload `saas-training-videos.zip` from the Releases page as a skill | Planning, scripts, steps files, EDLs, voice choice; recording needs a local machine (see below) |
| **ChatGPT** (any plan, no Skills) | A Project or custom GPT with `SKILL.md` + `references/*.md` as files, and the prompt below | Same as above |
| **Claude Code** | `git clone … ~/.claude/skills/saas-training-videos` | Yes |
| **Claude.ai / Claude desktop** | Upload the release zip under Settings → Capabilities → Skills | Planning + files (code execution sandbox has no Chrome login) |
| **Gemini CLI** | Clone anywhere; in your project add `GEMINI.md` with `@/path/to/saas-training-videos/AGENTS.md` | Yes |
| **Cursor / GitHub Copilot / Windsurf / Aider / Goose / Jules** | Clone into the project (or reference it); they read `AGENTS.md` | Yes when they can run terminal commands |
| **Any other agent or framework** | Give it `SKILL.md` as instructions and access to a shell in the repo folder | Yes |
| **No agent** | Follow `SKILL.md` yourself; every step is a command | Yes |

## What the machine needs (for recording and rendering)
- macOS or Linux, Python 3.10+ with `numpy` and `pillow`, `ffmpeg`, Node.js, `npm i -g @playwright/cli`, Google Chrome.
- A display for the visible browser (recording headless gives 1× footage). On a Linux server/container, run a virtual
  display first — e.g. `Xvfb :99 -screen 0 2560x1600x24 & export DISPLAY=:99` — and keep it running for the session.
  (Tested by the author on macOS; Linux + Xvfb is the standard approach but not yet tested here.)
- Optional: `ELEVENLABS_API_KEY` / `OPENAI_API_KEY`, and whisper.cpp + a ggml model for alignment.
- The person signs in to the app in the recording browser themselves (`pw_record.py login`). Agents never type passwords.

## Cloud agents (ChatGPT, Claude.ai, Codex cloud)
Their sandboxes usually can't reach a browser you're logged into, play audio for you, or keep a login between runs.
Use them for what they're good at here: planning the video, writing `script.md`, the steps files, the EDL, choosing a
voice, reviewing contact sheets you upload. Run the commands locally (or with a local agent), then upload results
(`pointer_events.py` output, contact sheets, the voice-gap report) for the next round.

## Prompt for assistants without skill support
Paste this as the project/custom-GPT instructions, with `SKILL.md` and the `references/` files attached:

```
You produce narrated screen-recorded training videos of web apps using the "saas-training-videos" method in the
attached SKILL.md and references. Follow SKILL.md's workflow and rules exactly. You can't run commands yourself unless
you have a shell tool: write the files (script.md, screen/steps/*.js, edl.json) and give the user the exact commands to
run, one step at a time, then continue from the output they paste back. Never ask for or type passwords; the user signs
in to the app in the recording browser. Never buy, delete, or message real people on camera. Use demo data only.
Narration: written to be spoken, each click named just before it happens; slow steps get a few more words, not silence.
```

## Packaging the skill for upload
```
python3 scripts/package_skill.py            # → dist/saas-training-videos.zip (top folder named like the skill)
```
