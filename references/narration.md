# Writing the narration

## Footage first, then words
Record and tighten the takes first, look at the contact sheet and the click list (`pointer_events.py`), then write each
segment's words to match what's on screen, in the order it happens. One segment per take.

## Write it to be spoken
- Second person, present tense, short sentences: "Click New contact… and give them a first name."
- **Name each action just before it happens**: the assembler lands each click ~0.25 s after its phrase.
- Name things the way the screen does ("click **Save action**", "open **Booking behavior**"), so viewers can find them.
- Ellipses (`...`) for a beat between two steps; commas for a short breath. Avoid long lists in one breath.
- Say *why* once in a while ("so callers get a confirmation") — it's what turns a click-path into training.
- Close each video the same way (a recap line, where to get help, what's next). Open by saying what we'll do.
- Read numbers the way you want them said ("sixty minutes", "five five five"), spell out URLs/emails you say aloud
  ("support at example dot com"), and keep a `pronunciations.json` next to the script for product/brand names.

## Pacing: add words, not silence
Viewers follow along slowly; the footage plays at real speed and the audio is never edited. Where the screen needs more
time than the voice gives (a page loading, typing, a dialog opening), **add a few natural words** at that spot:
"give it a second to load…", "over on the right…", "there it is…", "nice and simple". `voice_gaps.py` and the
assembler's pacing report tell you where and roughly how many words. Re-voice only that segment.

Dense pause tags (`[short pause]` everywhere) make a voice sound robotic; a stretch of padding words sounds human.

## Audio tags (ElevenLabs v3/v4 only — stripped for other providers)
Use few, and only where a person would:
- `[inhales]` — a soft breath before a new thought or section (~one every 20–30 s). Prefer it to `[exhales]`, which
  can come out as a loud sigh.
- `[pause]` — only where words don't fit.
- `[warmly]` on the sign-off, `[excited]` before a "and that's it!" moment.
Check with a local transcript (Whisper) that no tag was read aloud.

## Template
`templates/script_template.md`: a header comment (app, account, what the takes change), then one block per segment:
```
## [S03_ADD | vo | screen/tight/S03_ADD.mp4: Contacts → New → name → Save]
> SCREEN: take S03_ADD.
Now let's add our first contact. Click New contact, up in the top right... and give them a first name. I'll type Jamie.
```
Lines starting with `>` are direction (not spoken). `<!-- -->` comments are ignored.
