#!/usr/bin/env python3
"""Timestamped contact sheet of a video, for finding cut points and checking footage.

  python3 contact_sheet.py screen/raw/S03_ADD.mp4 --every 2 --out sheet.jpg
  python3 contact_sheet.py clip.mp4 --from 20 --to 40 --every 1 --cols 5 --width 360 --out s.jpg

Each tile is labelled with its timestamp (s). Uses ffmpeg for frames and Pillow for layout (ffmpeg's
tile filter can mis-stride odd sizes, so frames are composed here instead).
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ffprobe_duration  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--every", type=float, default=2.0)
    ap.add_argument("--from", dest="start", type=float, default=0.0)
    ap.add_argument("--to", type=float)
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--width", type=int, default=320)
    a = ap.parse_args()
    end = a.to or ffprobe_duration(a.video) or 0
    times, t = [], a.start
    while t <= end - 0.05:
        times.append(round(t, 2))
        t += a.every
    w, h = a.width, a.width * 9 // 16
    tmp = Path(tempfile.mkdtemp())
    tiles = []
    for i, t in enumerate(times):
        f = tmp / f"{i:04d}.png"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(t), "-i", a.video, "-frames:v", "1",
                        "-vf", f"scale={w}:{h}", str(f)], check=True)
        if f.exists():
            tiles.append((t, Image.open(f).convert("RGB")))
    cols = min(a.cols, max(1, len(tiles)))
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", max(14, w // 14))
    except OSError:
        font = ImageFont.load_default()
    for i, (t, im) in enumerate(tiles):
        x, y = (i % cols) * w, (i // cols) * h
        sheet.paste(im, (x, y))
        label = f"{t:.1f}s"
        d.rectangle((x, y, x + len(label) * (w // 22) + 10, y + w // 12), fill=(224, 38, 43))
        d.text((x + 5, y + 2), label, fill="white", font=font)
    sheet.save(a.out, quality=88)
    print(a.out, f"{len(tiles)} frames")


if __name__ == "__main__":
    main()
