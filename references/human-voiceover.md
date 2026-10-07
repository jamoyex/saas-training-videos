# Human-like voiceovers (ElevenLabs v4 and text-to-speech in general)

The goal: listeners should forget it's synthetic. That comes far more from **how the script is written** than from
settings. Everything here was learned by A/B-testing real course videos with real listeners.

## 1. What makes TTS sound robotic (and the fix)
| Symptom | Cause | Fix |
|---|---|---|
| Stiff, metronomic, "reading a list" | many identical pause tags (`[short pause]` after every click) | write the gaps as words ("…and then, over on the right, open Settings"); keep tags rare |
| Flat, same energy everywhere | stability too high; sentences all the same shape | stability 0.30–0.40; vary sentence length; a question now and then ("right?") |
| A loud sigh mid-sentence | `[exhales]` (renders as a strong, ~0.5 s, near-voice-level breath) | use a soft `[inhales]` before new thoughts instead |
| Pause tags don't land | v4 often makes `[long pause]` ~0.5 s instead of ~1.8 s | add words for time; never rely on tags for timing |
| Tag read aloud ("pause") | typo/unknown tag, or a non-v3/v4 model | only use known tags; `voiceover.py` strips tags for other providers; check with Whisper |
| Brand names mangled | the model guesses | `pronunciations.json` respelling (v4 ignores ElevenLabs dictionaries) |
| Each segment sounds like a new take | segments generated in isolation | `voiceover.py` sends `previous_text`/`next_text`; keep the same voice + settings for a whole course |
| Rushed | fast voice + dense script | speed 0.95; fewer words per step; the edit holds the screen, never speeds up audio |

## 2. ElevenLabs v4 — settings that work for tutorials
| Setting | Value | Notes |
|---|---|---|
| model | `eleven_v4` | expressive; supports audio tags. No SSML `<break>` (that's `eleven_multilingual_v2`). `eleven_v3` behaves similarly. |
| stability | **0.35** (0.30–0.40) | lower = more natural variation; above ~0.5 it flattens, below ~0.25 it can wander |
| similarity_boost | 0.80 | keeps a cloned voice's timbre |
| style | 0.20 | a little energy; above ~0.4 it over-acts |
| speed | **0.95** | a touch slower than default for following along; below ~0.9 sounds artificial |
| use_speaker_boost | on | |
| context | previous_text / next_text | `voiceover.py` sends neighbouring segments so delivery flows across cuts |
| segment size | ≤ ~2,500 characters | one segment per take keeps re-voicing cheap and sync simple |

```
python3 scripts/voiceover.py speak script.md --provider elevenlabs --model eleven_v4 --voice VOICE_ID \
        --stability 0.35 --speed 0.95 --out vo                     # or set TTS_* in .env
```
Timing quirk: v4 puts a pause's duration on the word *before* it (that word's end time runs through the pause). Start
times are exact; the assembler only uses start times, so sync isn't affected.

## 3. Human sounds and audio tags (v3/v4)
Use them like a person would — rarely, and where they'd naturally happen.

| Tag | Use | Frequency |
|---|---|---|
| `[inhales]` | a **soft breath before a new thought** or section ("[inhales] Now let's connect it to the calendar.") | ~1 per 20–30 s, at topic shifts |
| `[pause]` | a beat where words don't fit (after a reveal, before a punchline) | a few per video |
| `[warmly]` | the sign-off / thank-you | once, at the end |
| `[excited]` | the payoff moment ("[excited] And that's it — it's live!") | 0–2 per video |
| `[laughs softly]`, `[chuckles]` | only after something genuinely light | rare |
| `[exhales]` | avoid in tutorials (comes out as a sigh) | — |
| `[short pause]` / `[long pause]` | avoid in runs; unreliable lengths; robotic when stacked | rare |

Breaths from punctuation: a comma gives a short breath, a full stop a longer one, `...` a thoughtful beat. Most of the
"human" rhythm should come from punctuation and sentence shape, with tags as seasoning.

Before committing a style for a course, **A/B it**: the same 20-second passage with (A) no tags, (B) `[exhales]`, (C) soft
`[inhales]` — `voiceover.py audition --voices VOICE --text "…"` once per variant — and let the listener choose.

## 4. Writing text the voice will read
- **Conversational, second person, contractions**: "you'll", "let's", "it's". Read it aloud: if you wouldn't say it, rewrite it.
- **Sentence length 6–20 words**, varied. One idea per sentence. Avoid parentheses and semicolons.
- **Name the click right before it**; give slow screens a few extra natural words instead of silence
  ("give it a second to load…", "there it is…", "nice and simple"). `voice_gaps.py` tells you where.
- **Light conversational markers** keep it human: "Now,", "So,", "Alright,", "And there it is.", an occasional "right?".
  At most one filler ("you know", "basically") per ~150 words. No "um/uh".
- **Numbers and symbols as spoken**: "sixty minutes", "nine A.M.", "twenty-four seven", "ninety-nine dollars a month".
  Acronyms with dots when spelled out: "A.I.", "S.M.S.", "C.R.M."; read-as-words ones plain ("SaaS", "NASA").
- **URLs and emails as spoken**: "support at example dot com"; avoid reading long URLs at all ("the link below").
- **Product names**: keep the real spelling in the script; put the spoken form in `pronunciations.json`
  (`{"Acme": "Ack-mee"}`). It's swapped only in what's sent to the voice, so captions stay correct.
- **Quotes of UI text**: say them as labels ("click Save action"), not with "quote … unquote".

## 5. Cloning a presenter's voice (ElevenLabs)
- **Consent first**, in writing. Use the clone only for content the person approved.
- **Instant clone**: 1–3 min of clean speech; good for drafts. **Professional clone**: 30 min+ of varied, clean,
  conversational speech (ideally the presenter teaching), quiet room, consistent mic distance; best results.
- Record the training audio in the style you want back (teaching, warm, mid-paced), not reading a news script.
- After cloning, audition it on a real segment at stability 0.30 / 0.40 / 0.50 and speed 0.95 / 1.0, and pick by ear.

## 6. Checking every voiced segment
```
ffmpeg -i vo/S03_ADD.mp3 -ar 16000 -ac 1 /tmp/s.wav && whisper-cli -m "$WHISPER_MODEL" -f /tmp/s.wav -nt -np
```
- No tag spoken aloud; no skipped or doubled sentence (Whisper sometimes drops a sentence in a long file — re-check just
  that stretch with `-ss/-t` before re-voicing); names right; numbers read the way you wanted.
- Listen to one full video at normal speed before hand-off. Re-voice single segments, never the whole video for one fix.
- Cost/time: about 1 s of generation per 1–2 s of audio; characters ≈ words × 5.7.

## 7. Other providers
OpenAI `gpt-4o-mini-tts`: put delivery in `--instructions` ("warm, patient software trainer; light smile; steady pace")
and write the same way (tags are stripped). macOS `say`: drafts only. Human narration: same script rules; record one file
per segment, then `voiceover.py align`.
