# Example: TodoMVC (public demo app, no login)

Re-create the video (media isn't committed):
```bash
S=../../scripts
python3 $S/pw_record.py open todomvc https://demo.playwright.dev/todomvc
python3 $S/pw_record.py take todomvc screen/steps/S01_ADD.js screen/raw/S01_ADD.webm
python3 $S/screen_capture.py tighten screen/raw/S01_ADD.webm screen/tight/S01_ADD.mp4 --fps 30 --keep 60 --log screen/raw/S01_ADD.pointer.json
python3 $S/pointer_events.py . S01_ADD          # compare with the "t" values in edl.json; adjust if your take differs
python3 $S/voiceover.py speak script.md --provider say --voice Samantha --speed 0.9 --out vo     # or any provider/voice
python3 $S/voice_gaps.py edl.json
python3 $S/assemble_video.py edl.json           # → out/todomvc_add-and-complete.mp4
python3 $S/pw_record.py close todomvc
```
