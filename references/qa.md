# QA checklist (every video, before hand-off)

| Check | How |
|---|---|
| Every take printed `QA: clean` (no grey bands, no early stop) | the `take` output |
| The footage shows what the narration says, in order | `contact_sheet.py out/<video>.mp4 --every 8 --cols 6 --out qa.jpg` |
| No private data on screen (real names/emails/phones, other tabs, notifications, API keys) | contact sheets of each take; blur or re-shoot |
| Clicks land on their words | `sync_tools.py check edl.json out/<video>.mp4 .build/full` — flags on hovers/zoom starts are normal; a click well before its word is not |
| Pacing: no "needs +Xs" over ~1 s left | the assembler's report; add words, re-voice that segment |
| Zooms frame the detail (labels not cropped) | grab frames mid-zoom: `ffmpeg -ss <t> -i out/<video>.mp4 -frames:v 1 z.png` |
| Cursor visible, right shape, no jumps at cuts | contact sheet + a few frames around `tighten` cuts |
| Voice: no tag read aloud, nothing skipped, names right | local Whisper transcript of each `vo/*.mp3` vs the script |
| Loudness −16 LUFS (±0.5), true peak below −1 dBTP | `ffmpeg -nostats -i out/<video>.mp4 -af ebur128 -f null - 2>&1 \| grep "I:"` |
| 1920×1080, 30 fps, H.264 + AAC | `ffprobe -v error -show_entries stream=width,height,r_frame_rate,codec_name out/<video>.mp4` |
| Account changes recorded | the project's CHANGELOG lists what each take created/changed (and anything to clean up) |

Hand-off: upload the final MP4 where the team expects it, name it consistently (`<number> - <Title>.mp4`), and note
what could need a re-shoot later (UI likely to change, steps that used placeholder data, features not tested live).
