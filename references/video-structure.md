# Structure of a training video (and of a course)

## 1. Anatomy of a how-to video
```
OPEN      10–25 s   what we'll do and why it matters ("In this video we'll connect your calendar, so callers can book")
STEPS     the body  one segment per task step / take, each: where → what → (why) → result
RECAP     10–20 s   "So, we did 1, 2 and 3." (optional for videos under ~3 min)
CLOSE     8–20 s    what's next + where to get help + sign-off, over the last frame
```
Every **step segment** follows the same beat, which is what makes a course feel consistent:
1. **Where** — "Over in Settings, open Calendars." (navigation, named just before each click)
2. **What** — the action, with the exact label: "Click **New calendar**… and choose **Event calendar**."
3. **Why** (one line, when useful) — "This one doesn't need a team member; it books into the business's own hours."
4. **Result** — show and name it: "And there it is: our calendar's ready, with a booking link."

Rules:
- **One job per video.** If the outcome needs "and", consider two videos.
- **Show the start state** at the top of the first step (where the viewer should be), and the **end state** at the end.
- **Name, then click**: the click lands just after its words (the assembler does this from the sync anchors).
- **No dead air, no fast-forward**: slow steps are covered by narration; very long waits are cut and said ("I've sped
  this up"). The footage itself plays at real speed.
- **Zoom** for small details (a field being typed, a toggle, a value); don't zoom on whole-page moments.
- **End on the result**, not on a menu. The closing line plays over the last frame (a still made from it).
- **Consistent language**: the same intro/close lines, the same terms, the same demo data across a course.

## 2. Formats
| Format | Use for | EDL shape |
|---|---|---|
| Screen walkthrough (voice-over) | most how-tos | `screen` segments + `image` close |
| Presenter + screen | courses with a face; a presenter open/close, PiP during steps | `full` open/close + `screen` with `"pip"` |
| Slides + screen | concepts first, then the how-to | `slides` segments, then `screen` |
| Clip-only (joined to someone else's intro) | when a human presenter records the open separately | starts straight on the screen, ends with the close |
| Short (≤ 60 s) | release notes, a single tip | one `screen` segment, no recap |

## 3. Course structure
```
Welcome (≤ 3 min: who it's for, what they'll be able to do, how the course is organised)
Module 1  Getting started      1.1 Navigating the app · 1.2 Setting up your account …
Module 2  <core job>           2.1 … 2.2 … 2.3 …
Module 3  <variations>         …
Module 4  Testing & results    …
Module 5  Going live / advanced (label optional content as optional)
Resources (templates, downloads, glossary, support)
```
- Order by need, not by menu. Each module ends with something working.
- Short videos are cheap to re-shoot when the UI changes: keep UI-volatile steps in their own short videos.
- Keep numbering identical everywhere: file names, titles, the tracker, the LMS page.

## 4. Project folder
```
<course>/
  PLAN.md  CHANGELOG.md  pronunciations.json  .env (never committed)
  brand/  intro.mp4  outro.mp4  wipe_in.mov  wipe_out.mov
  videos/<num>_<slug>/
    brief.md  script.md  edl.json
    screen/steps/<SEG>.js      ← the takes (re-shoot = one command)
    screen/raw/<SEG>.webm + .webm.frames.json + .pointer.json
    screen/tight/<SEG>.mp4 + .mp4.map.json
    vo/<SEG>.mp3 + .words.json + manifest.json
    stills/  out/<num>_<slug>.mp4  .build/ (intermediates, disposable)
```
Segment ids: `S01_FIELD`, `S02_ACTION`, … in order; the take, the voice files and the EDL segment share the id.
Hand-off file name: `<num> - <Title>.mp4` (or the team's convention), 1920×1080, 30 fps, −16 LUFS.
