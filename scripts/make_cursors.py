#!/usr/bin/env python3
"""Draw the cursor bitmaps the edit uses (arrow, pointing hand, I-beam) into assets/cursors/.

  python3 make_cursors.py            # writes arrow.png, hand.png, ibeam.png and cursors.json

Original artwork drawn with Pillow (no OS cursor images are shipped), in the familiar desktop style: a dark arrow with a
white edge, a white hand with a dark edge, a dark I-beam with a light edge, all with a soft shadow. Each bitmap is drawn at 10 px per pt;
cursors.json gives its size in pt, its hotspot in pt and its size in px (cursor_overlay.py scales it to the video).
Re-run after changing a shape; tweak STROKE / SHADOW to taste.
"""
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "assets" / "cursors"
S = 10                       # px per pt
STROKE = 0.8                 # outline width, pt
SHADOW = (0.5, 1.0, 1.1, 90)  # dx, dy, blur (pt), alpha


def canvas(w, h):
    return Image.new("L", (round(w * S), round(h * S)), 0)


def grow(mask, pt):
    """round, anti-aliased dilation by `pt`"""
    return mask.filter(ImageFilter.GaussianBlur(pt * S * 0.55)).point(lambda v: min(255, v * 10))


def finish(mask, fill, edge, size_pt, hot_pt, name, stroke=STROKE):
    """mask = the shape; edge = the shape grown by `stroke`; shadow under everything"""
    dil = ImageChops.lighter(grow(mask, stroke), mask)
    w, h = mask.size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dx, dy, blur, alpha = SHADOW
    sh = Image.new("L", (w, h), 0)
    sh.paste(dil, (round(dx * S), round(dy * S)))
    sh = sh.filter(ImageFilter.GaussianBlur(blur * S)).point(lambda v: v * alpha // 255)
    img.alpha_composite(Image.merge("RGBA", (*(Image.new("L", (w, h), 0),) * 3, sh)))
    img.alpha_composite(Image.merge("RGBA", (*(Image.new("L", (w, h), c) for c in edge), dil)))
    img.alpha_composite(Image.merge("RGBA", (*(Image.new("L", (w, h), c) for c in fill), mask)))
    img.save(OUT / f"{name}.png")
    return {"pt": list(size_pt), "hot_pt": list(hot_pt), "px": [w, h]}


def poly(d, pts, ox, oy):
    d.polygon([((x + ox) * S, (y + oy) * S) for x, y in pts], fill=255)


def rrect(d, x0, y0, x1, y1, r):
    d.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=r * S, fill=255)


def arrow():
    m = canvas(28, 40)
    d = ImageDraw.Draw(m)
    # tip at the hotspot (5, 5)
    poly(d, [(0, 0), (0, 16.6), (3.9, 13.1), (6.5, 19.3), (9.1, 18.2), (6.6, 12.2), (11.7, 12.2)], 5, 5)
    return finish(m, (16, 16, 18), (255, 255, 255), (28, 40), (5, 5), "arrow", stroke=1.0)


def hand():
    m = canvas(32, 34)
    d = ImageDraw.Draw(m)
    rrect(d, 11.3, 6.6, 15.1, 19.0, 1.9)          # index finger (its tip is the hotspot, 13 / 8)
    rrect(d, 14.8, 13.6, 18.2, 21.0, 1.7)         # middle
    rrect(d, 17.9, 14.4, 21.2, 21.4, 1.6)         # ring
    rrect(d, 20.9, 15.6, 23.9, 21.8, 1.5)         # little
    rrect(d, 10.8, 18.2, 23.9, 28.6, 3.4)         # palm
    d.ellipse([6.0 * S, 17.2 * S, 12.6 * S, 23.6 * S], fill=255)   # thumb
    img_mask = m
    meta = finish(img_mask, (255, 255, 255), (20, 20, 22), (32, 34), (13, 8), "hand")
    # finger creases
    img = Image.open(OUT / "hand.png")
    dd = ImageDraw.Draw(img)
    for x in (15.0, 18.05, 21.05):
        dd.line([(x * S, 16.2 * S), (x * S, 20.2 * S)], fill=(20, 20, 22, 255), width=max(1, int(0.45 * S)))
    img.save(OUT / "hand.png")
    return meta


def ibeam():
    m = canvas(23, 24)
    d = ImageDraw.Draw(m)
    cx = 12
    rrect(d, cx - 0.55, 3.0, cx + 0.55, 19.0, 0.3)       # stem
    for y in (2.3, 18.6):                                # serifs
        rrect(d, cx - 3.2, y, cx - 0.2, y + 1.1, 0.5)
        rrect(d, cx + 0.2, y, cx + 3.2, y + 1.1, 0.5)
    rrect(d, cx - 1.6, 10.5, cx + 1.6, 11.5, 0.3)        # cross bar
    return finish(m, (20, 20, 22), (250, 250, 250), (23, 24), (12, 11), "ibeam", stroke=0.6)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"arrow": arrow(), "hand": hand(), "ibeam": ibeam()}
    (OUT / "cursors.json").write_text(json.dumps(meta, indent=1))
    print(f"wrote {', '.join(meta)} → {OUT}")


if __name__ == "__main__":
    main()
