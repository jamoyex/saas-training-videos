#!/usr/bin/env python3
"""Before assembling: compare, between consecutive sync anchors, how long the FOOTAGE takes vs how long the VOICE takes.

  python3 voice_gaps.py edl.json            # every screen segment with "sync"

"NEED +1.3s (~3 words)" = the screen needs more time than the narration gives between those two phrases: add a few
natural words there in script.md ("give it a second to load", "over on the right") and re-voice that segment. Fix
these before rendering; the assembler's own pacing report is the final check. Anchors that aren't found are flagged.
"""
import json
import re
import subprocess
import sys
from pathlib import Path


def norm(t):
    return re.sub(r"[^0-9a-z]", "", t.lower())


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    edl_path = Path(sys.argv[1] if len(sys.argv) > 1 else "edl.json")
    root = edl_path.parent
    edl = json.loads(edl_path.read_text())
    for s in edl["segments"]:
        if s["type"] != "screen" or "sync" not in s:
            continue
        wf = root / (s["audio"][:-4] + ".words.json")
        d = json.loads(wf.read_text())
        ws = d["words"] if isinstance(d, dict) else d
        toks = [norm(w["word"]) for w in ws]
        pos, rows = 0, []
        for an in s["sync"]:
            ph = [norm(x) for x in an["say"].split() if norm(x)]
            for i in range(pos, len(toks)):
                if toks[i:i + len(ph)] == ph:
                    rows.append((an["t"], ws[i]["start"], an["say"]))
                    pos = i + 1
                    break
            else:
                rows.append((an["t"], None, an["say"] + "  ?? NOT FOUND (in order)"))
        vid = root / s["video"]
        vdur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                     str(vid)], capture_output=True, text=True).stdout)
        end = min(vdur, s.get("end", vdur))
        adur = ws[-1]["end"]
        print(f"== {s['id']}  footage {end:.1f}s  speech {adur:.1f}s")
        for (t0, a0, n0), (t1, a1, n1) in zip(rows, rows[1:] + [(end, adur, "<end>")]):
            if a0 is None or a1 is None:
                print(f"   {n0} -> {n1}  (anchor missing)")
                continue
            need = (t1 - t0) - (a1 - a0)
            flag = f"NEED +{need:.1f}s (~{max(2, round(need * 2.6))} words)" if need > 0.6 else ""
            print(f"   {n0[:28]:28s} -> {n1[:28]:28s} footage {t1 - t0:5.1f}  speech {a1 - a0:5.1f}  {flag}")


if __name__ == "__main__":
    main()
