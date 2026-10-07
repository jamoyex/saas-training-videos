# Editing: EDL, sync, cursor, zooms, assembly

`scripts/assemble_video.py edl.json` builds the video from an edit decision list. Paths are relative to the EDL.

## 1. EDL shape
```json
{
 "output": "out/03_add-a-contact.mp4",
 "intro": "brand/intro.mp4",
 "outro": "brand/outro.mp4",
 "transition": {"in": "brand/wipe_in.mov", "out": "brand/wipe_out.mov"},
 "cursor_ring": "#3B82F6",
 "loudnorm": true,
 "segments": [
  {"id": "S01_OPEN", "type": "full", "video": "presenter/S01_OPEN.mp4"},
  {"id": "S02_ADD", "type": "screen", "video": "screen/tight/S02_ADD.mp4", "audio": "vo/S02_ADD.mp3", "wipe_in": true,
   "sync": [{"t": 2.07, "say": "Click New contact"}, {"t": 4.73, "say": "first name"}],
   "cursor": {"zooms": [{"say": "first name", "offset": -0.4, "until_say": "Save", "center": [1100, 520], "zoom": 1.5}]}},
  {"id": "S03_RECAP", "type": "image", "image": "stills/s02_last_frame.png", "audio": "vo/S03_RECAP.mp3"}
 ]
}
```
All top-level keys except `output` and `segments` are optional. Segment types:
- `screen` — a tight take, synced to its narration (the workhorse).
- `image` — a still (e.g. the last frame of the previous segment) under narration: closings, recaps.
- `slides` — images that change on phrases (`"until_say"`), for intros/recaps made as slides.
- `full` — a full-frame clip with its own audio (a presenter on camera, an intro).
- Any segment can take `"pip"` (a presenter/webcam clip bottom-right) and `"start"/"end"` (use part of a clip).

## 2. Sync anchors — land every click on its word
`"sync": [{"t": <tight-clip seconds>, "say": "<phrase from the script>", "offset": 0}]`, in order.
- `t` comes from `pointer_events.py` (a click = the `down` time; a hover = the `move` time; typing = when it starts).
- `say` is matched case/punctuation-insensitively in the segment's `words.json`, searched in order, so the same anchors
  survive a re-voice. A phrase that no longer exists stops the build with "phrase not found": update the anchor.
- **Pacing** (default on): footage plays at real speed; each event lands 0.25 s after its phrase starts; where the voice
  is too fast for the footage the screen holds the frame before the next click and the build prints
  `S02: the screen needs +1.3s after "Contact," → add ~3 words`. Fix in the script, re-voice that segment, rebuild with
  `--only S02_ADD`. Check before building with `voice_gaps.py edl.json`.
- `"end": 33.6` trims a take's tail (e.g. a dialog that misbehaved at the end).

## 3. Cursor, click rings, zooms, gestures
`"cursor": true` draws the cursor from the take's pointer log (shapes: arrow, hand, I-beam; a soft ring on each press).
`"cursor": {...}` adds:
- `"zooms": [{"say": "first name", "offset": -0.4, "until_say": "Save", "center": [x, y], "zoom": 1.5}]` (or `"hold": 3`
  instead of `until_say`). Eases in/out, pans to keep the cursor in view, joins close zooms with a pan.
- `"gestures": [{"say": "the total", "type": "circle", "center": [x, y], "rx": 90, "ry": 36, "dur": 1.4}]`
  (`point`, `trace`, `circle`, `wiggle`) to point at things the take didn't hover — only over non-hover-reactive content.
- `"size": 1.5` cursor scale, `"ring": "#hex"` click ring color (or the EDL's `cursor_ring`).

**Coordinates are video px (1920×1080) = page CSS px × 1.5** — not the 2560×1440 capture px. Read a point off a page
screenshot (1280×720) and multiply by 1.5. For a dialog, center on the dialog, not the cursor; keep zooms ≤ 1.8×.
Zoom when the detail is small (a field being typed, a toggle, a price); not for whole-page moments.

## 4. Closings and stills
Make the closing still from the **rendered** last frame of the previous segment (cursor included), so nothing jumps:
```
ffmpeg -sseof -0.05 -i .build/full/03_S03_SAVE.mp4 -frames:v 1 -update 1 stills/s04_last_frame.png
python3 scripts/assemble_video.py edl.json --only S04_CLOSE
```

## 5. Build commands
```
python3 scripts/assemble_video.py edl.json --preview     # 540p ultrafast draft (no loudnorm): check timing first
python3 scripts/assemble_video.py edl.json               # 1080p30, x264 CRF 18, AAC 192k, two-pass loudnorm −16 LUFS
python3 scripts/assemble_video.py edl.json --only S03    # rebuild one segment, re-use the rest from .build/
```
Intermediates live in `.build/` next to the EDL (safe to delete). Intro/outro/transition overlays are optional brand
assets you provide (an alpha `.mov` for wipes).

## 6. Multi-video consistency
Same voice + settings, same cursor ring, same intro/outro, same closing line, same demo data across a course. Keep a
small `PROJECT.md` with these decisions and a `CHANGELOG.md` of what each take changed in the app account.
