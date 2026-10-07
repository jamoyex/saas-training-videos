#!/usr/bin/env python3
"""Voice ↔ action sync helpers for screen walkthroughs.

  python3 sync_tools.py bursts screen/tight/S03_ADD.mp4            # list on-screen activity bursts [start-end|peak]
  python3 sync_tools.py check edl.json out/final.mp4 .build/full    # QA every sync anchor in the rendered video

`bursts`: every visual change (clicks, page loads, typing, dropdowns, hovers) as time ranges. Match them IN ORDER to
the actions you performed while recording (the take's steps file / the event list `pw_record.py take` printed), and use each burst's START as the anchor's "t".
Big peaks (>5) are page/dialog changes; small ones (0.3–2) are typing, hovers, checkboxes, dropdowns.
Don't read event times off thumbnails — they were 0.5–2 s off in practice.

`check`: for each anchor, measures motion in the window after the previous cue up to the word (should be ~0) and just
after the word (should be large). Flags "EARLY" (the action happens before it is said) and "quiet" (nothing visibly
happens). Benign flags: a page still loading or text still being typed while the phrase starts.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assemble_video as al  # noqa: E402
from _common import ffprobe_duration  # noqa: E402


def gray_frames(video, t0=None, t1=None, w=320, fps=30):
    h = w * 9 // 16
    cmd = ["ffmpeg", "-loglevel", "error"]
    if t0 is not None:
        cmd += ["-ss", f"{max(0, t0):.3f}", "-t", f"{t1 - max(0, t0):.3f}"]
    cmd += ["-i", str(video), "-vf", f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.int16)


def cmd_bursts(a):
    for v in a.videos:
        f = gray_frames(v, fps=a.fps)
        d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
        out, cur = [], None
        for i, val in enumerate(d):
            t = (i + 1) / a.fps
            if val > a.threshold:
                if cur and t - cur[1] <= a.gap:
                    cur[1] = t
                    cur[2] = max(cur[2], val)
                else:
                    if cur:
                        out.append(cur)
                    cur = [t, t, val]
        if cur:
            out.append(cur)
        print(f"== {Path(v).name}  ({len(out)} bursts)")
        print("  " + " ".join(f"[{s:.2f}-{e:.2f}|{p:.1f}]" for s, e, p in out))


def cmd_check(a):
    edl_path = Path(a.edl).resolve()
    root = edl_path.parent
    edl = json.loads(edl_path.read_text())
    build = Path(a.build)
    # only the finished parts that were concatenated (bumper + one file per segment), not the intermediates
    # next to them (<NN>_<SEG>_screen.mp4, _cursor.mp4, …), or every cue after a cursor segment lands late
    parts = {"bumper"} | {s["id"] for s in edl["segments"]}
    starts, t = {}, 0.0
    for f in sorted(build.glob("[0-9][0-9]_*.mp4")):
        name = f.stem.split("_", 1)[1]
        if name not in parts:
            continue
        starts[name] = t
        t += ffprobe_duration(f) or 0

    def motion(t0, t1):
        fr = gray_frames(a.video, t0, t1)
        return float(np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2)).sum()) if len(fr) > 1 else 0.0

    flagged = 0
    for seg in edl["segments"]:
        if not seg.get("sync"):
            continue
        audio = root / seg["audio"] if seg.get("audio") else None
        tj = root / "vo" / f"{seg['id']}.timing.json"      # written by the assembler's pacing
        if al.pace_settings(edl, seg) and tj.exists():
            pairs = [tuple(x) for x in json.loads(tj.read_text())["pairs"]]
        else:
            pairs = al.resolve_sync(seg, root, audio, seg["id"])
        prev = None
        for an, (_f, o) in zip(seg["sync"], pairs):
            T = starts.get(seg["id"], 0) + o
            lo = T - 1.0 if prev is None else max(T - 1.0, prev + 0.35)
            pre = motion(lo, T - 0.15) if T - 0.15 - lo > 0.1 else 0.0
            post = motion(T - 0.15, T + 0.6)
            prev = T
            flag = "  <-- EARLY" if pre > max(1.0, post * 0.6) else ("  (quiet)" if post < 0.5 else "")
            flagged += bool(flag)
            if flag or a.all:
                label = an["say"] if isinstance(an, dict) else an
                print(f"{seg['id']:14} {str(label)!r:30} @{T:7.2f}s  before={pre:6.2f}  after={post:6.2f}{flag}")
    print(f"flagged cues: {flagged}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bursts")
    b.add_argument("videos", nargs="+")
    b.add_argument("--threshold", type=float, default=0.25)
    b.add_argument("--gap", type=float, default=0.2)
    b.add_argument("--fps", type=int, default=30)
    c = sub.add_parser("check")
    c.add_argument("edl")
    c.add_argument("video")
    c.add_argument("build", help=".build/full or .build/preview of that render")
    c.add_argument("--all", action="store_true", help="print every cue, not just flagged ones")
    a = ap.parse_args()
    {"bursts": cmd_bursts, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    main()
