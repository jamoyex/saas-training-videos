#!/usr/bin/env python3
"""List a take's clicks/hovers on the TIGHT clip's timeline: the numbers you put in the EDL's "sync" anchors.

  python3 pointer_events.py <video-folder> S01_FIELD S02_ADD …     # reads screen/raw/<id>.* and screen/tight/<id>.mp4.map.json
  python3 pointer_events.py <video-folder> S01_FIELD --raw-dir rec --tight-dir cut

Each line: tight-clip time, raw time, event (move/down), cursor shape, page px. A "down" is a click; the "move" just
before it is the glide onto the target (anchor hovers on the move, clicks on the down).
"""
import argparse
import bisect
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("takes", nargs="+")
    ap.add_argument("--raw-dir", default="screen/raw")
    ap.add_argument("--tight-dir", default="screen/tight")
    ap.add_argument("--all", action="store_true", help="include pointer-up events")
    a = ap.parse_args()
    V = Path(a.folder)
    for seg in a.takes:
        fr = json.loads((V / a.raw_dir / f"{seg}.webm.frames.json").read_text())["t"]
        mpf = V / a.tight_dir / f"{seg}.mp4.map.json"
        mp = json.loads(mpf.read_text())["t"] if mpf.exists() else [round(t - fr[0], 4) for t in fr]
        log = json.loads((V / a.raw_dir / f"{seg}.pointer.json").read_text())
        print(f"== {seg}  tight {len(mp) / 30:.1f}s")
        for e in log:
            if e["e"] == "up" and not a.all:
                continue
            raw = e["t"] / 1000 - fr[0]
            k = bisect.bisect_left(mp, raw)
            print(f"  tight {k / 30:6.2f}  raw {raw:6.2f}  {e['e']:<4} {e['c']:<5} ({e['x']},{e['y']})")


if __name__ == "__main__":
    main()
