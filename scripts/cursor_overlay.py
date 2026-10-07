#!/usr/bin/env python3
"""Draw a human-looking macOS cursor onto a screen clip that was recorded with the pointer hidden.

  python3 cursor_overlay.py screen/tight/S03_ADD.mp4 --log screen/raw/S03_ADD.pointer.json --out screen/cursor/S03_ADD.mp4

Record with scripts/pw_record.py (the default: it writes <name>.pointer.json and <clip>.frames.json itself) or, with the
browser-extension fallback, with scripts/fallback/recording_mode.js set to CURSOR = "hidden" (save its sessionStorage "tv-pointer-log"
next to the raw clip as <name>.pointer.json). Either way the footage has no pointer at all.
The clip can be the raw recording or a `tighten.py` output. The timing sidecars the recorder writes
place every logged event on the right frame: <raw>.frames.json (wall-clock time of every raw frame + crop geometry)
and, for a tightened clip, <tight>.map.json (the raw time shown in every tight frame).

Choreography: every logged move is a spot the cursor must reach by the time the page reacted there, and every press is
a click. In between, the cursor moves like a hand: Fitts-law durations, curved minimum-jerk paths, a small overshoot
and correction on long moves, slow drift while resting, hand / I-beam shapes where the page asked for them (real macOS
bitmaps from assets/cursors/, drawn by make_cursors.py), a press plus a soft ring on each click. Motion is computed in the clip's own time, so
the cuts `tighten` makes don't make the cursor jump. Writes <out>.cursor.json (the path, per frame) for QA.

Presenter gestures (--gestures gestures.json) add movements the recording never had, to point things out while the
narrator talks. Clip time in seconds, positions in video px (1920×1080, read them off a frame):
  {"at": 18.9, "type": "trace",  "from": [740, 663], "to": [1600, 663], "dur": 1.0, "shape": "hand"}   scan / underline
  {"at": 24.4, "type": "circle", "center": [1596, 663], "rx": 95, "ry": 38, "dur": 1.5, "loops": 1.2}  circle a value
  {"at": 12.0, "type": "point",  "pos": [900, 400], "dur": 1.2}                                           rest on a spot
  {"at": 20.9, "type": "wiggle", "dur": 0.6, "r": 6}                     small "right here" loops wherever it rests
The cursor still reaches every logged click on time; the script prints "late" if a gesture leaves too little time.
Only gesture over things that don't react to hover (text, prices, rows without hover styling): the page itself never
saw these movements, so a button the cursor crosses won't light up.

Zooms (--zooms zooms.json) push in on small details (a field being typed in, a date picker, a price). Like gestures,
`center` is in VIDEO px (1920×1080) = page CSS px × 1.5, NOT the 2560×1440 capture px:
  {"from": 1.0, "to": 5.6, "center": [1000, 860], "zoom": 1.7}         optional "ramp" (s, default 0.6)
The camera eases in over the ramp, holds, and eases out. Two zooms less than 0.8 s apart are joined by a direct pan
(with a slight pull-back on long pans) instead of out-and-in. The view never leaves the frame, and it pans to keep the
cursor inside it. The cursor and click rings are drawn after the zoom, so they stay sharp; the footage itself is
upscaled, so keep zooms ≤ ~1.8× on 1080p recordings.
"""
import argparse
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

CURSORS = Path(__file__).resolve().parent.parent / "assets/cursors"
DW, DH = 1920, 1080   # layout space: all positions, gestures and zooms are in 1080p px, whatever the footage/output size


def timing(clip):
    """wall-clock time shown in every clip frame, the clip fps, and the raw recording's geometry"""
    mp = Path(clip + ".map.json")
    if mp.exists():
        m = json.loads(mp.read_text())
        fr = json.loads(Path(m["src"] + ".frames.json").read_text())
        idx = np.clip(np.round(np.array(m["t"]) * fr["fps"]).astype(int), 0, len(fr["t"]) - 1)
        return np.array(fr["t"])[idx], m["fps"], fr
    fr = json.loads(Path(clip + ".frames.json").read_text())
    return np.array(fr["t"]), fr["fps"], fr


def load_log(path):
    """pointer log → [{t, e, x, y, c}]: the full form, or the compact {"t0", "ev": [[dt, "m|d|u", x, y, "a|h|i"], …]}"""
    d = json.loads(Path(path).read_text())
    if isinstance(d, dict):
        E, C = {"m": "move", "d": "down", "u": "up"}, {"a": "arrow", "h": "hand", "i": "ibeam"}
        return [{"t": d["t0"] + dt, "e": E[e], "x": x, "y": y, "c": C[c]} for dt, e, x, y, c in d["ev"]]
    return d


def fitts(d):
    return float(np.clip(0.16 + 0.115 * math.log2(d / 26 + 1), 0.26, 0.85))


def minjerk(u):
    u = np.clip(u, 0, 1)
    return u ** 3 * (10 - 15 * u + 6 * u * u)


def bezier(A, B, bow, s):
    d = B - A
    C = (A + B) / 2 + np.array([-d[1], d[0]]) * bow
    return (1 - s) ** 2 * A + 2 * (1 - s) * s * C + s * s * B


def drift(t, amp, seed):
    """slow, smooth hand drift (px)"""
    fr = [0.17, 0.29, 0.47]
    ph = [(seed * 1.7 + k * 2.1) % (2 * math.pi) for k in range(3)]
    x = sum(math.sin(2 * math.pi * f * t + p) / (k + 1) for k, (f, p) in enumerate(zip(fr, ph)))
    y = sum(math.cos(2 * math.pi * f * 0.83 * t + p * 1.3) / (k + 1) for k, (f, p) in enumerate(zip(fr, ph)))
    return amp * 0.55 * x, amp * 0.55 * y


def gesture_ends(g):
    if g["type"] == "trace":
        return g["from"], g["to"]
    if g["type"] == "circle":
        (cx, cy), phi = g["center"], math.pi + 2 * math.pi * g.get("loops", 1.0)
        return [cx - g["rx"], cy], [cx + g["rx"] * math.cos(phi), cy + g["ry"] * math.sin(phi)]
    return g["pos"], g["pos"]                                                  # point


def gesture_path(g, u):
    """cursor position at progress u (0–1) through a trace or circle gesture"""
    if g["type"] == "trace":
        A, B = np.array(g["from"], float), np.array(g["to"], float)
        d = B - A
        nrm = np.array([-d[1], d[0]]) / (np.hypot(*d) or 1)
        wob = 1.5 * math.sin(2 * math.pi * 1.5 * u) * math.sin(math.pi * u) - 0.02 * np.hypot(*d) * math.sin(math.pi * u)
        return A + d * float(minjerk(u)) + nrm * wob                        # hand-drawn: slight arc and waver
    if g["type"] == "circle":
        e = 0.55 * u + 0.45 * float(minjerk(u))                             # eases in and out, never stalls
        phi = math.pi + 2 * math.pi * g.get("loops", 1.0) * e             # starts on the left, goes clockwise
        k = 1 + 0.05 * math.sin(2 * phi + 0.7)                             # not a perfect ellipse
        return np.array([g["center"][0] + g["rx"] * k * math.cos(phi), g["center"][1] + g["ry"] * k * math.sin(phi)])
    return np.array(g["pos"], float)


def build(log, wall, fps, fr, gestures=()):
    """pointer log (+ presenter gestures) → rests (where the cursor must be, when, which shape, clicks) and the moves"""
    cw, ch, cx, cy = fr["crop"]
    s, (ox, oy) = fr["scale"], fr["viewport_origin"]
    to_px = lambda x, y: np.array([((x * s + ox) - cx) * DW / cw, ((y * s + oy) - cy) * DH / ch])   # page → layout px
    n = len(wall)
    rests = []
    for ev in sorted(log, key=lambda e: e["t"]):
        i = int(np.searchsorted(wall, ev["t"] / 1000, side="left"))
        if i >= n:
            break                                              # after the clip's last frame
        t, pos = i / fps, to_px(ev["x"], ev["y"])
        same = rests and np.hypot(*(pos - rests[-1]["pos"])) < 3
        if i == 0:                                             # before the clip starts: only sets the start position
            rests = [dict(pos=pos, ready=0.0, click=None, shape=ev["c"], after=ev["c"])]
        elif ev["e"] == "move" and not same:
            rests.append(dict(pos=pos, ready=t, click=None, shape=ev["c"], after=ev["c"]))
        elif ev["e"] == "down":
            if not same:
                rests.append(dict(pos=pos, ready=t - 0.13, click=None, shape=ev["c"], after=ev["c"]))
            rests[-1].update(click=t, shape=ev["c"], after=ev["c"])
        elif ev["e"] == "up" and same:
            rests[-1]["after"] = ev["c"]
    if not rests:
        rests = [dict(pos=np.array([DW / 2, DH / 2]), ready=0.0, click=None, shape="arrow", after="arrow")]
    for g in gestures:
        if g["type"] != "wiggle":
            a, b = gesture_ends(g)
            sh = g.get("shape", "arrow")
            rests.append(dict(pos=np.array(a, float), end=np.array(b, float), ready=g["at"], busy=g["at"] + g["dur"],
                              click=None, shape=sh, after=sh, gesture=g))
    rests = rests[:1] + sorted(rests[1:], key=lambda r: r["ready"])
    rests[0]["arrive"] = 0.0
    moves = []
    for k in range(1, len(rests)):
        p, r = rests[k - 1], rests[k]
        A, B = p.get("end", p["pos"]), r["pos"]
        D = float(np.hypot(*(B - A)))
        ready = r["ready"] if r["click"] is None else min(r["ready"], r["click"] - 0.13)   # land, settle, then press
        lo = max(max(p["arrive"], p.get("busy", 0.0)) + 0.15, (p["click"] + 0.12) if p["click"] is not None else 0.0)
        T = fitts(D)
        if ready - T < lo:                                      # not enough time: move faster rather than arrive late
            T = max(0.2, ready - lo)
        t0 = max(lo, ready - T)
        bow = (0.07 + 0.05 * ((k * 7919) % 5) / 4) * (1 if k % 3 else -1)   # deterministic, varied arcs
        moves.append(dict(t0=t0, t1=t0 + T, A=A, B=B, bow=bow, overshoot=D > 260, k=k, late=t0 + T - ready))
        r["arrive"] = t0 + T
    return rests, moves


def state(t, rests, moves, total, wiggles=()):
    """(x, y, shape) of the cursor hotspot at clip time t"""
    for mv in moves:
        if mv["t0"] <= t < mv["t1"]:
            u = (t - mv["t0"]) / (mv["t1"] - mv["t0"])
            A, B = mv["A"], mv["B"]
            if mv["overshoot"]:
                D = np.hypot(*(B - A))
                Bo = B + (B - A) / D * min(9.0, 0.013 * D)
                p = bezier(A, Bo, mv["bow"], minjerk(u / 0.86)) if u < 0.86 else Bo + (B - Bo) * minjerk((u - 0.86) / 0.14)
            else:
                p = bezier(A, B, mv["bow"], minjerk(u))
            prev, nxt = rests[mv["k"] - 1], rests[mv["k"]]
            shape = prev["after"] if u < 0.12 else (nxt["shape"] if u > 0.8 else "arrow")
            return p[0], p[1], shape
    k = max(i for i, r in enumerate(rests) if r.get("arrive", 1e9) <= t)
    r = rests[k]
    g = r.get("gesture")
    if g and g["at"] <= t < g["at"] + g["dur"]:
        x, y = gesture_path(g, (t - g["at"]) / g["dur"])
        return x, y, r["shape"]
    done = g is not None and t >= g["at"] + g["dur"]
    base, since = (r["end"], r["busy"]) if done else (r["pos"], r["arrive"])
    leave = next((mv["t0"] for mv in moves if mv["t0"] > t), total)
    env = min(1.0, (t - since) / 0.6, (leave - t) / 0.35)
    if r["click"] is not None:
        env = min(env, max(0.0, (abs(t - r["click"]) - 0.12) / 0.4))
    dx, dy = drift(t, 1.6 if leave - since > 1.5 else 0.6, k)
    env = max(0.0, env)
    dx, dy = dx * env, dy * env
    for w in wiggles:                                                       # small "right here" loops
        if w["at"] <= t < w["at"] + w["dur"]:
            u, loops, rr = (t - w["at"]) / w["dur"], w.get("loops", 2), w.get("r", 6)
            e = math.sin(math.pi * u)
            dx += rr * e * math.sin(2 * math.pi * loops * u)
            dy += rr * 0.6 * e * (1 - math.cos(2 * math.pi * loops * u)) / 2
    shape = r["after"] if r["click"] is not None and t >= r["click"] + 0.08 else r["shape"]
    return base[0] + dx, base[1] + dy, shape


def camera(zooms, n, fps, W, H, cursor_xy, sigma=0.25):
    """per-frame view rectangle [x0, y0, w] (h = w·H/W) from zoom segments, following the cursor"""
    def rect(center, z):
        w = W / z
        h = w * H / W
        return np.array([min(max(center[0] - w / 2, 0), W - w), min(max(center[1] - h / 2, 0), H - h), w])
    full = np.array([0.0, 0.0, float(W)])
    kf = [(0.0, full)]
    segs = sorted(zooms, key=lambda s: s["from"])
    for i, s in enumerate(segs):
        r = min(s.get("ramp", 0.6), (s["to"] - s["from"]) / 3)
        target = rect(s["center"], s["zoom"])
        if i and s["from"] - segs[i - 1]["to"] < 0.8:            # join with a direct pan, not out-and-in
            kf.pop()
            a, b = kf[-1], (s["from"] + r, target)
            if abs((a[1][0] + a[1][2] / 2) - (b[1][0] + b[1][2] / 2)) > W / 4:   # long pan: pull back a little mid-way
                zmid = 1 + (min(W / a[1][2], s["zoom"]) - 1) * 0.55
                mid = ((a[1][:2] + a[1][2] / 2) + (b[1][:2] + b[1][2] / 2)) / 2
                kf.append(((a[0] + b[0]) / 2, rect(mid, zmid)))
        elif s["from"] > kf[-1][0]:
            kf.append((s["from"], full))
        kf += [(s["from"] + r, target), (s["to"] - r, target), (s["to"], full)]
    ts = np.arange(n) / fps
    view = np.empty((n, 3))
    for j, t in enumerate(ts):
        i = max(k for k in range(len(kf)) if kf[k][0] <= t) if t >= kf[0][0] else 0
        if i + 1 < len(kf):
            (t0, r0), (t1, r1) = kf[i], kf[i + 1]
            view[j] = r0 + (r1 - r0) * float(minjerk((t - t0) / max(t1 - t0, 1e-6)))
        else:
            view[j] = kf[i][1]
    # follow: shift the view so the cursor stays inside (margin 8 %), smoothed so the camera glides
    shift = np.zeros((n, 2))
    for j, (x, y) in enumerate(cursor_xy):
        x0, y0, w = view[j]
        h, m = w * H / W, 0.08 * w
        if w < W - 1:
            shift[j, 0] = min(0, x - (x0 + m)) + max(0, x - (x0 + w - m))
            shift[j, 1] = min(0, y - (y0 + m)) + max(0, y - (y0 + h - m))
    k = np.exp(-0.5 * (np.arange(-int(3 * sigma * fps), int(3 * sigma * fps) + 1) / (sigma * fps)) ** 2)
    k /= k.sum()
    for c in range(2):
        view[:, c] += np.convolve(np.pad(shift[:, c], len(k) // 2, mode="edge"), k, mode="valid")
    view[:, 0] = np.clip(view[:, 0], 0, W - view[:, 2])
    view[:, 1] = np.clip(view[:, 1], 0, H - view[:, 2] * H / W)
    return view


def press(t, clicks):
    s = 1.0
    for c in clicks:
        d = t - c
        if -0.06 <= d < 0:
            s = min(s, 1 - 0.1 * (d + 0.06) / 0.06)
        elif 0 <= d < 0.16:
            s = min(s, 0.9 + 0.1 * minjerk(d / 0.16))
    return s


def load_cursors(px_per_pt, size):
    meta = json.loads((CURSORS / "cursors.json").read_text())
    out = {}
    for k, m in meta.items():
        img = Image.open(CURSORS / f"{k}.png").convert("RGBA")
        k_scale = px_per_pt * size / (m["px"][0] / m["pt"][0])           # source px → video px
        w, h = max(1, round(img.width * k_scale)), max(1, round(img.height * k_scale))
        a = np.asarray(img).astype(np.float32) / 255
        pm = np.dstack([a[..., :3] * a[..., 3:4], a[..., 3:4]])          # premultiplied resize: no dark fringes
        chans = [Image.fromarray((pm[..., c] * 255).astype(np.uint8)).resize((w * 4, h * 4), Image.LANCZOS) for c in range(4)]
        out[k] = dict(src=np.dstack([np.asarray(p, np.float32) / 255 for p in chans]),   # 4× oversampled
                      hot=(m["hot_pt"][0] * px_per_pt * size, m["hot_pt"][1] * px_per_pt * size), size=(w, h))
    return out


def sprite(c, fx, fy, scale):
    """premultiplied RGBA patch with the hotspot at subpixel (fx, fy), scaled about the hotspot"""
    src = c["src"]
    sh, sw = src.shape[:2]
    w, h = c["size"]
    pw, ph = int(math.ceil(w * scale)) + 3, int(math.ceil(h * scale)) + 3
    hx, hy = c["hot"]
    ys, xs = np.mgrid[0:ph, 0:pw].astype(np.float32)
    u = ((xs + 0.5 - fx) / scale + hx) * 4 - 0.5
    v = ((ys + 0.5 - fy) / scale + hy) * 4 - 0.5
    acc = np.zeros((ph, pw, 4), np.float32)
    for oy in (-1.5, -0.5, 0.5, 1.5):                                     # box-filter the 4× source, bilinear taps
        for ox in (-1.5, -0.5, 0.5, 1.5):
            uu, vv = u + ox, v + oy
            x0, y0 = np.floor(uu).astype(int), np.floor(vv).astype(int)
            ax, ay = (uu - x0)[..., None], (vv - y0)[..., None]

            def g(yy, xx):
                ok = (xx >= 0) & (xx < sw) & (yy >= 0) & (yy < sh)
                r = np.zeros((ph, pw, 4), np.float32)
                r[ok] = src[yy[ok], xx[ok]]
                return r
            acc += (g(y0, x0) * (1 - ax) * (1 - ay) + g(y0, x0 + 1) * ax * (1 - ay)
                    + g(y0 + 1, x0) * (1 - ax) * ay + g(y0 + 1, x0 + 1) * ax * ay)
    return acc / 16


def paste(frame, patch, ox, oy):
    H, W = frame.shape[:2]
    ph, pw = patch.shape[:2]
    X0, Y0, X1, Y1 = max(0, ox), max(0, oy), min(W, ox + pw), min(H, oy + ph)
    if X1 > X0 and Y1 > Y0:
        p = patch[Y0 - oy:Y1 - oy, X0 - ox:X1 - ox]
        frame[Y0:Y1, X0:X1] = p[..., :3] * 255 + frame[Y0:Y1, X0:X1] * (1 - p[..., 3:4])


def ring(frame, cx, cy, d, color, px):
    """soft click highlight: a disc that grows and fades over 0.45 s"""
    if not 0 <= d < 0.45:
        return
    u = d / 0.45
    r = (7 + 17 * float(minjerk(u))) * px
    alpha = 0.42 * (1 - u) ** 1.5
    R = int(r + 3)
    x0, y0 = int(cx) - R, int(cy) - R
    ys, xs = np.mgrid[0:2 * R + 1, 0:2 * R + 1].astype(np.float32)
    a = np.clip(r - np.hypot(xs + x0 + 0.5 - cx, ys + y0 + 0.5 - cy) + 0.5, 0, 1) * alpha
    patch = np.dstack([a * color[0] / 255, a * color[1] / 255, a * color[2] / 255, a])
    paste(frame, patch, x0, y0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip")
    ap.add_argument("--log", required=True, help="pointer log JSON saved from the page")
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=float, default=1.5, help="cursor size vs macOS default (tutorial style: 1.5)")
    ap.add_argument("--ring", default="#3B82F6", help="click highlight colour (hex), or 'none'")
    ap.add_argument("--gestures", help="presenter gestures JSON (see above)")
    ap.add_argument("--zooms", help="zoom segments JSON (see above)")
    ap.add_argument("--out-size", type=int, nargs=2, default=[1920, 1080], metavar=("W", "H"))
    ap.add_argument("--crf", type=int, default=17)
    a = ap.parse_args()

    wall, fps, fr = timing(a.clip)
    SW, SH = fr["out"]                                              # footage size (native capture or 1080p)
    OW, OH = a.out_size                                             # output size
    px_per_pt = fr["scale"] * DW / fr["crop"][0]                    # layout px per screen point
    total = len(wall) / fps
    gestures = json.loads(Path(a.gestures).read_text()) if a.gestures else []
    wiggles = [g for g in gestures if g["type"] == "wiggle"]
    rests, moves = build(load_log(a.log), wall, fps, fr, gestures)
    clicks = [(r["click"], r["pos"]) for r in rests if r["click"] is not None]
    for mv in moves:
        g = rests[mv["k"]].get("gesture")
        print(f"  move → rest {mv['k']:<2} {mv['t0']:6.2f}–{mv['t1']:6.2f}s ({mv['t1'] - mv['t0']:.2f}s)"
              + (f"  then {g['type']} {g['at']:.2f}–{g['at'] + g['dur']:.2f}s" if g else "")
              + (f"  late {mv['late']:+.2f}s" if mv["late"] > 0.02 else ""))
    print(f"  {len(clicks)} clicks, clip {total:.1f}s at {fps} fps, footage {SW}x{SH} → {OW}x{OH}")
    color = None if a.ring == "none" else tuple(int(a.ring.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    curs = load_cursors(px_per_pt, a.size)

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    dec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", a.clip, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OW}x{OH}",
                            "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", str(a.crf),
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", a.out], stdin=subprocess.PIPE)
    n = len(wall)
    states = [state(k / fps, rests, moves, total, wiggles) for k in range(n)]
    zooms = json.loads(Path(a.zooms).read_text()) if a.zooms else []
    view = camera(zooms, n, fps, DW, DH, [(x, y) for x, y, _ in states])
    fs = SW / DW                                                    # footage px per layout px
    path, k = [], 0
    while True:
        buf = dec.stdout.read(SW * SH * 3)
        if len(buf) < SW * SH * 3:
            break
        t = k / fps
        x0, y0, vw = view[min(k, n - 1)]
        q = OW / vw                                                 # output px per layout px (zoom × output scale)
        img = np.frombuffer(buf, np.uint8).reshape(SH, SW, 3)
        if (SW, SH) != (OW, OH) or vw < DW - 0.5:
            box = (x0 * fs, y0 * fs, (x0 + vw) * fs, (y0 + vw * DH / DW) * fs)
            img = np.asarray(Image.fromarray(img).resize((OW, OH), Image.LANCZOS, box=box))
        frame = img.astype(np.float32)
        if color:
            for c, pos in clicks:
                ring(frame, (pos[0] - x0) * q, (pos[1] - y0) * q, t - c, color, px_per_pt * q)
        x, y, shape = states[min(k, n - 1)]
        X, Y = (x - x0) * q, (y - y0) * q
        c, s = curs[shape], press(t, [c for c, _ in clicks]) * q    # the cursor grows with the zoom, like a camera
        hx, hy = c["hot"]
        ox, oy = int(math.floor(X)) - int(math.ceil(hx * s)) - 1, int(math.floor(Y)) - int(math.ceil(hy * s)) - 1
        paste(frame, sprite(c, X - ox, Y - oy, s), ox, oy)
        path.append([round(t, 3), round(float(x), 1), round(float(y), 1), shape, round(s, 3),
                     round(float(x0), 1), round(float(y0), 1), round(float(vw), 1)])
        enc.stdin.write(np.clip(frame + 0.5, 0, 255).astype(np.uint8).tobytes())
        k += 1
    enc.stdin.close()
    enc.wait()
    dec.wait()
    Path(a.out + ".cursor.json").write_text(json.dumps(path))
    print(f"wrote {a.out} ({k} frames)")


if __name__ == "__main__":
    main()
