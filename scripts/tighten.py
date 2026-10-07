#!/usr/bin/env python3
"""Tighten a raw take: cut idle time, keep a timing map so the pointer log still lines up.

  python3 tighten.py screen/raw/S03_ADD.webm screen/tight/S03_ADD.mp4 --log screen/raw/S03_ADD.pointer.json
  python3 tighten.py screen/raw/S03_ADD.webm screen/tight/S03_ADD.mp4 --log … --cut 12.4-27.9 31.0-33.5

- With --log (the take's pointer log): drops the idle lead-in (before the first pointer event − --lead s) and the tail
  (after the last one + --tail s).
- --keep N: any stretch where the picture doesn't change for longer than N s is shortened to N s. Default 60 keeps
  every reading/hover pause (walkthroughs need them); use ~1.5 only for takes where nothing should linger.
- --cut A-B …: remove ranges by hand (blank page loads, spinners, AI thinking). Only where no pointer event falls inside.
Writes <dst> (silent H.264, real-time speed) and <dst>.map.json (the source time of every output frame), which the
cursor overlay and the assembler use to place every logged event on the right frame. Keep both.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def freeze_intervals(src, min_still, noise):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-vf", f"freezedetect=n={noise}:d={min_still}", "-map", "0:v",
                        "-f", "null", "-"], capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", r.stderr)]
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                               capture_output=True, text=True).stdout.strip() or 0)
    while len(ends) < len(starts):
        ends.append(dur)
    return list(zip(starts, ends)), dur


def cmd_tighten(a):
    """Cut every still stretch longer than --keep down to --keep seconds (half before, half after the cut).
    Also accepts --cut A-B ranges (seconds) to remove mistakes. With --log (the take's pointer log) it also cuts the
    idle lead-in and tail: everything before the first pointer event − --lead s and after the last one + --tail s.
    Output is silent (narration comes later)."""
    src, dst = a.src, a.dst
    iv, dur = freeze_intervals(src, a.keep, a.noise)
    cuts = []
    if a.log:
        fr = json.loads(Path(src + ".frames.json").read_text())
        wall = fr["t"]
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from cursor_overlay import load_log
        evs = [e["t"] / 1000 for e in load_log(a.log) if wall[0] <= e["t"] / 1000 <= wall[-1]]
        if evs:
            first = next(i for i, w in enumerate(wall) if w >= min(evs)) / fr["fps"]
            last = next(i for i, w in enumerate(wall) if w >= max(evs)) / fr["fps"]
            if first - a.lead > 0.05:
                cuts.append((0.0, first - a.lead))
            if dur - (last + a.tail) > 0.05:
                cuts.append((last + a.tail, dur))
    for s0, e0 in iv:
        if e0 - s0 > a.keep:
            cuts.append((s0 + a.keep / 2, e0 - a.keep / 2))
    for c in a.cut or []:
        x, y = [float(v) for v in c.split("-")]
        cuts.append((x, y))
    cuts.sort()
    merged = []
    for c in cuts:
        if merged and c[0] <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], c[1]))
        else:
            merged.append(c)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                            "stream=r_frame_rate,nb_read_frames", "-of", "csv=p=0", src], capture_output=True, text=True)
    rate, nframes = probe.stdout.strip().split(",")[:2]
    num, den = (int(v) for v in rate.split("/"))
    src_fps = num / den
    if merged:
        expr = "+".join(f"between(t,{x:.3f},{y:.3f})" for x, y in merged)
        # restamp the kept frames at the SOURCE rate (real-time speed); -r then resamples to the output rate.
        # (Before 2026-09-30 this used the output rate, so 20 fps recordings played 1.5× fast once anything was cut.)
        vf = f"select='not({expr})',setpts=N/({src_fps:g}*TB)"
    else:
        vf = "null"
    script = Path(dst).with_suffix(".vf.txt")
    script.write_text(vf)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-filter_script:v", str(script),
                    "-an", "-r", str(a.fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", dst],
                   check=True)
    script.unlink()
    d1 = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", dst],
                        capture_output=True, text=True).stdout.strip()
    # <dst>.map.json: the source time shown in every output frame (cursor_overlay.py maps pointer events through it)
    kept = [k / src_fps for k in range(int(nframes)) if not any(x <= k / src_fps <= y for x, y in merged)]
    n_out = int(round(float(d1) * a.fps))
    Path(dst + ".map.json").write_text(json.dumps({"src": str(Path(src).resolve()), "fps": a.fps, "t": [
        round(kept[min(len(kept) - 1, int(round(i / a.fps * src_fps)))], 4) for i in range(n_out)]}))
    removed = sum(y - x for x, y in merged)
    print(f"{src} {dur:.1f}s → {dst} {d1}s  (removed {removed:.1f}s in {len(merged)} cuts)")


def main():
    t = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    t.add_argument("src")
    t.add_argument("dst")
    t.add_argument("--keep", type=float, default=60, help="max seconds of any still stretch to keep (default 60)")
    t.add_argument("--noise", type=float, default=0.001, help="freezedetect noise tolerance")
    t.add_argument("--cut", nargs="*", help="extra ranges to remove, e.g. 12.5-18.0")
    t.add_argument("--fps", type=int, default=30)
    t.add_argument("--log", help="pointer log of the take: also cut the idle lead-in and tail")
    t.add_argument("--lead", type=float, default=1.5, help="(--log) seconds kept before the first pointer event")
    t.add_argument("--tail", type=float, default=2.5, help="(--log) seconds kept after the last pointer event")
    cmd_tighten(t.parse_args())


if __name__ == "__main__":
    main()
