# Planning and generating the content

Plan before you record. A video planned from the real screens, for a named audience, with one clear outcome, is easy to
record and short to edit; one improvised at the keyboard needs re-shoots. The order is always:

```
intake ──► course plan ──► (approval) ──► per video: explore ──► brief ──► record ──► write script to the footage
        ──► voice ──► edit ──► QA ──► (review) ──► next video
```
Produce a **pilot video** end to end first (the simplest how-to), get it approved (structure, voice, pacing, look),
then produce the rest the same way.

## 1. Intake — answer from the material first, ask only what's missing and blocking
| Question | Why it matters |
|---|---|
| **App + account**: which product, which workspace/sub-account, which plan/role | what features exist on screen; the demo account must have them |
| **Audience**: role, skill level (default: non-technical beginners), language/locale | vocabulary, pace, how much "why" |
| **Outcome**: what can the viewer do after the course / each video? | the success test for every script |
| **Scope + source material**: outline, docs, help-center articles, support tickets, a feature list, an old course | the content backbone; support tickets show where people get stuck |
| **Format**: screen-only, presenter + screen, slides + screen; captions; intro/outro branding | the EDL shape and assets needed |
| **Voice**: presenter clone, stock voice, human recording (see `voices.md`) | audition before production |
| **Demo data**: fictional company, people, prices, phone/email conventions | consistent, safe screens across all videos |
| **Constraints**: deadline, paid steps (never on camera), things not to show | what to film up to and narrate around |
| **Hand-off**: where finished files go (folder, LMS, video host), naming, status tracking | the last step of each video |

## 2. Course plan (`templates/course_plan.md`)
- **Structure**: course → modules (a module = one goal, 2–6 videos) → videos (one job each). Order by what a user needs
  first: get set up → navigate → do the core job → handle the common variations → check results → advanced/optional.
- **Number** videos `<module>.<video>` (2.3) and keep that number in file names, titles and trackers.
- **Each video gets**: number, title (verb-first: "Booking appointments"), one-sentence outcome, prerequisites (what must
  already exist in the account), the screens involved, what the takes will create/change in the account, and length.
- **Lengths**: screen how-to 2–6 min (one task, ~5–12 clicks per minute of footage); concept/overview 3–8 min; course
  welcome ≤ 3 min. If a task needs more than ~8 min, split it.
- **Budget**: narration ≈ 160–175 wpm, so words ≈ minutes × 165. ElevenLabs bills characters ≈ words × 5.7.
- **Continuity**: what one video creates, the next may rely on (video 2 creates the calendar video 3 books into). Plan
  the account state across the course and record in order; note "state at start" per video.
- Flag decisions for the user explicitly (⚠): paid steps, real vs demo data, features the demo account lacks, naming of
  the product on screen (white-label names, old vs new UI).

## 3. Explore, then brief each video (`templates/video_brief.md`)
Do a **task analysis on the real app** before writing anything: open the recording browser, walk the task once with
screenshots and snapshots (`references/recording.md` §2), cancel without saving, and write down:
- the click path, with every label exactly as the UI shows it;
- waits (page loads, AI generation, uploads) and popups that appear;
- defaults worth mentioning and settings to leave alone;
- where it differs by plan, role or region; anything that costs money or needs identity checks;
- what the viewer needs to understand *why* (one line per step at most).
Turn that into the brief: the outcome, the start state, the segments (one per take, 20–90 s each), what each shows, and
the closing line. Get the brief approved for the pilot; afterwards approve per module.

## 4. Generate the script (footage first)
1. Record and tighten the takes from the brief; read the click list (`pointer_events.py`) and a contact sheet.
2. Draft each segment's narration **to the footage**, in the order things happen (`references/video-structure.md` for
   the beats, `references/narration.md` for wording, `references/human-voiceover.md` for TTS-ready text).
3. Check every claim against the screen (labels, defaults, numbers). Don't invent features, prices or results.
4. Voice it, run `voice_gaps.py`, add words where the screen needs time, re-voice only those segments.
5. Keep the script, brief and EDL in the video folder: they make the next re-shoot or re-voice a small job.

Generating with an LLM: give it the brief, the click list, the exact labels and the audience, and ask for narration in
segment blocks (`## [SEG | vo | …]`). Then edit for the rules in `narration.md` — models over-explain, add filler
("seamlessly", "powerful", "in today's video"), and drift from the real labels.

## 5. Reviews (what to show the user, when)
| Gate | Show | Approve |
|---|---|---|
| Course plan | module/video list with outcomes and lengths | scope, order, naming |
| Voice | 2–4 auditions of a real segment | voice, settings, breathing/pausing style |
| Pilot video | the full draft | structure, pace, cursor/zoom look, intro/outro |
| Each video | the draft + notes on what it changed in the account | content accuracy |

Keep a `CHANGELOG.md` per course: what each take created or changed in the account, decisions made, and what could need
a re-shoot later (UI likely to change, placeholder data, features not tested live).
