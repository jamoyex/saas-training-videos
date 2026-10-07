# Choosing and producing the voice

`scripts/voiceover.py` produces one audio file and one word-timing file per script segment, with any of these:

| Provider | Voices | Timings | Tags | Best for |
|---|---|---|---|---|
| `elevenlabs` | your clones, voices added to your account, the shared library | from the API | `[inhales]` etc. on eleven_v3/v4 | publishing; a presenter's cloned voice |
| `openai` | alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer, verse | Whisper alignment | stripped; tone via `--instructions` | good, cheap, no clone needed |
| `say` (macOS) | system voices (`voices --provider say`) | Whisper alignment | stripped | drafts and timing passes, offline |
| human | anyone with a mic | `align` (Whisper) | n/a | the presenter recording themselves |

Keys: `ELEVENLABS_API_KEY`, `OPENAI_API_KEY` in `.env` or `~/.training-video.env`. Alignment uses whisper.cpp
(`WHISPER_MODEL=/path/ggml-base.en.bin`), else faster-whisper, else the OpenAI transcription API.

## 1. Find candidates
```
python3 scripts/voiceover.py voices                                          # ElevenLabs voices in your account
python3 scripts/voiceover.py voices --library --use-case narration --gender female --accent american
python3 scripts/voiceover.py voices --library --search "friendly tutorial"
python3 scripts/voiceover.py voices --provider openai
python3 scripts/voiceover.py voices --provider say
```
What fits training videos: clear, warm, mid-paced, "explainer"/"narration"/"conversational" voices. Avoid heavy
character voices and very slow "audiobook" reads. Match the audience (accent, formality) and the brand.
If the presenter should sound like a real person, use **their own clone** (with their consent) or their recording.

## 2. Audition by ear — same words, side by side
```
python3 scripts/voiceover.py audition --voices VOICE_A VOICE_B VOICE_C --script script.md --seg S02 --out auditions
python3 scripts/voiceover.py audition --voices VOICE_A --stability-list 0.3 0.45 0.6 --text "Click Save, and you're done." --out auditions
python3 scripts/voiceover.py audition --provider openai --voices coral sage --instructions "friendly software trainer" --text "…"
```
Use a real segment with clicks in it (not a pangram). Give the user the files to compare, and record the choice
(voice id, model, settings) in the project's notes. For style choices (breathing, pauses), audition variants of the
same passage too: e.g. no tags / `[exhales]` / soft `[inhales]` — let the listener decide.

## 3. Settings that matter
- **ElevenLabs**: model `eleven_v4` (default; `--model eleven_v3` / `eleven_multilingual_v2`), `--stability 0.3–0.4` for a
  natural, expressive read (higher = flatter, steadier), `--speed 0.9–1.0` (slower than 0.9 sounds artificial),
  similarity 0.8, style 0.2. The script passes the previous/next segment text so the delivery flows across segments.
- **OpenAI**: `gpt-4o-mini-tts` with `--instructions` ("upbeat, clear, patient software trainer"); `--speed 1.0`.
- **say**: `--speed 0.9` ≈ 160 wpm.
- Target **150–175 wpm** for screen walkthroughs; the manifest records each segment's wpm.

## 4. Produce
```
python3 scripts/voiceover.py speak script.md --provider elevenlabs --voice VOICE_ID --stability 0.35 --speed 0.95 --out vo
python3 scripts/voiceover.py speak script.md --provider elevenlabs --voice VOICE_ID --only S03_ADD --out vo   # after an edit
python3 scripts/voiceover.py speak script.md --dry-run                                                       # word counts, est. time
```
APIs drop connections now and then; `speak` retries each segment. Regenerate only the segments you changed.

## 5. Human narration
Record one file per segment (`vo/S03_ADD.wav`, quiet room, ~20 cm from the mic, read the script as written), then:
```
python3 scripts/voiceover.py align script.md --out vo            # → vo/<SEG>.words.json, mapped onto the script's words
```
Small ad-libs are fine; if under ~60% of words are recognised the tool warns (wrong file or very different reading).

## 6. Check every voiced segment
- Transcribe locally and compare with the script: no tag spoken aloud ("inhales", "pause"), no skipped sentence.
  (Whisper sometimes drops a sentence in long files; re-transcribe just that stretch before re-voicing.)
- Names said correctly (add to `pronunciations.json` next to the script: `{"Acme": "Ack-mee"}`; respelled for the voice,
  mapped back in the timings).
- Loudness is normalised in the final assembly (−16 LUFS), so don't adjust levels per segment.

## Consent
Only clone or imitate a real person's voice with their permission. Don't make a voice say things about real people or
products that they wouldn't say. Label synthetic narration if the platform or audience expects it.
