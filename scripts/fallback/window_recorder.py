#!/usr/bin/env python3
"""FALLBACK recorder (macOS): record the user's own Chrome window while an agent drives it through a browser extension
(e.g. Claude in Chrome, or any agent that controls the user's Chrome). Use it only when the Playwright recorder
(../pw_record.py) can't be used: a site that refuses automated browsers, a login that won't work in a separate profile.

  python3 window_recorder.py fit                          # size + park the Chrome window so the page area is 16:9
  python3 window_recorder.py start screen/S03_ADD.mp4     # records in the background (crop = Chrome viewport)
  python3 window_recorder.py stop                         # finalises the file
  python3 window_recorder.py probe                        # print the detected screen device, scale and crop
  python3 window_recorder.py overlays screen/S03_ADD.mp4 [--preset claude-in-chrome]   # QA: agent overlays leaked,
                                                          #   shrunk page, window-title timeline
Then tighten as usual (../tighten.py; the agent's think time between steps is cut there).
Window mode keeps the native Retina crop (--res native, e.g. 2410x1356) so zooms in the edit stay sharp, and writes
<out>.frames.json (capture time of every frame, crop geometry, window titles); `tighten` writes <dst>.map.json. Keep both:
cursor_overlay.py and the assembler's "cursor" step map the page's pointer log through them.

How the crop is found: the front Chrome window's bounds (AppleScript) minus the browser chrome height
(--ui, default 143 pt = tabs + toolbar), then scaled by the Retina factor, then inset by --margin px (a safety net
for an agent extension's activity glow; recording_mode.js is what actually hides it), then trimmed to 16:9. Size the window first so the viewport is ~16:9
— run `window_recorder.py fit` first: it sizes the window so the cropped area is exactly 16:9 with nothing
cut on the right (on a 1512x982 display → 1218x851 window, 1218x708 viewport).
Default --mode window: frames are grabbed from the Chrome WINDOW itself (Quartz CGWindowListCreateImage), so other
apps on top of Chrome (e.g. the agent's own app the user is watching) do NOT end up in the recording. --mode screen uses
ffmpeg/avfoundation on the whole display instead (only if window mode is unavailable; then Chrome must stay in front).
IMPORTANT: Chrome must not be COMPLETELY covered by another window, or it stops painting (frozen frames, hanging
screenshots). `fit` parks Chrome flush with the screen bottom so it peeks out below a maximised agent window.
The real macOS cursor is never in window mode. Agent extensions often draw their own on-page pointer, edge glow and stop
button (Claude in Chrome: orange). Inject recording_mode.js (the extension's run-JavaScript tool) before `start` and after
every page load, with the PRESET for your extension: it hides those overlays, the pointer included, and logs the pointer
so the edit can draw a human cursor.
The terminal/app needs macOS Screen Recording permission. The user grants it; never change system settings yourself.
"""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

STATE = Path(os.environ.get("TMPDIR", "/tmp")) / "tv_window_recorder.json"


def osa(script):
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True).stdout.strip()


def screen_device():
    out = subprocess.run(["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                         capture_output=True, text=True).stderr
    m = re.search(r"\[(\d+)\] Capture screen 0", out)
    if not m:
        raise SystemExit("No 'Capture screen 0' device found (Screen Recording permission?)")
    return m.group(1)


def geometry(a):
    b = [int(x) for x in osa('tell application "Google Chrome" to get bounds of front window').split(", ")]
    desk = [int(x) for x in osa('tell application "Finder" to get bounds of window of desktop').split(", ")]
    scale = a.scale or 2
    x0, y0 = b[0] * scale, (b[1] + a.ui) * scale
    w, h = (b[2] - b[0]) * scale, (b[3] - b[1] - a.ui) * scale
    m, mt, mb = a.margin, a.margin_top, a.margin_bottom
    x0, y0, w, h = x0 + m, y0 + mt, w - 2 * m, h - mt - mb
    if w / h > 16 / 9:  # too wide → trim from the right (keeps the app's left nav/logo intact)
        nw = int(h * 16 / 9) // 2 * 2
        w = nw
    else:
        nh = int(w * 9 / 16) // 2 * 2
        y0 += (h - nh) // 2
        h = nh
    return {"window": b, "desktop": desk, "scale": scale, "crop": [w // 2 * 2, h // 2 * 2, x0, y0]}


def cmd_fit(a):
    """Size the front Chrome window so the cropped page area is exactly 16:9, and park it flush with the BOTTOM of
    the screen. Other apps (e.g. a maximised agent window) usually stop above the Dock area, so a strip of Chrome
    stays visible. That matters: macOS marks a fully covered window as occluded and Chrome then STOPS PAINTING
    (window capture freezes and CDP screenshots hang). Keep at least a few points of Chrome uncovered while recording."""
    desk = [int(x) for x in osa('tell application "Finder" to get bounds of window of desktop').split(", ")]
    menubar = 33
    height = desk[3] - menubar - a.bottom_gap           # tallest window that fits under the menu bar
    vh_px = (height - a.ui) * a.scale
    ch = vh_px - a.margin_top - a.margin_bottom
    cw = ch * 16 / 9
    w_pt = int(round((cw + 2 * a.margin) / a.scale)) + 1
    top = desk[3] - height                              # flush with the screen bottom
    osa(f'tell application "Google Chrome" to set bounds of front window to {{0, {top}, {w_pt}, {desk[3]}}}')
    time.sleep(0.8)
    print(json.dumps({"window_pt": [0, top, w_pt, desk[3]], **geometry(a)}))


def cmd_probe(a):
    g = geometry(a)
    print(json.dumps({"device": screen_device(), **g}))


def chrome_window_id(title_hint=""):
    import Quartz
    wl = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID)
    wins = [w for w in wl if w.get("kCGWindowOwnerName") == "Google Chrome" and w.get("kCGWindowLayer") == 0
            and w.get("kCGWindowBounds", {}).get("Height", 0) > 300]
    if title_hint:
        wins = [w for w in wins if title_hint.lower() in (w.get("kCGWindowName") or "").lower()] or wins
    if not wins:
        raise SystemExit("No Chrome window found")
    b = [int(x) for x in osa('tell application "Google Chrome" to get bounds of front window').split(", ")]
    wins.sort(key=lambda w: abs(w["kCGWindowBounds"]["Width"] - (b[2] - b[0])) + abs(w["kCGWindowBounds"]["Y"] - b[1]))
    return wins[0]["kCGWindowNumber"]


def cmd_run_window(a):
    """Internal: capture one window at a fixed frame rate and pipe BGRA frames into ffmpeg."""
    import Quartz
    w, h, x, y = a.crop
    wid = a.wid
    opts = Quartz.kCGWindowImageBoundsIgnoreFraming | Quartz.kCGWindowImageBestResolution
    first = Quartz.CGWindowListCreateImage(Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow, wid, opts)
    iw, ih = Quartz.CGImageGetWidth(first), Quartz.CGImageGetHeight(first)
    stride = Quartz.CGImageGetBytesPerRow(first)
    ff = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra",
                           "-s", f"{stride // 4}x{ih}", "-r", str(a.fps), "-i", "-",
                           "-vf", f"crop={w}:{h}:{x}:{y}" + ("" if a.native else ",scale=1920:1080:flags=lanczos"),
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", a.out],
                          stdin=subprocess.PIPE)
    stop = {"now": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(now=True))
    signal.signal(signal.SIGTERM, lambda *_: stop.update(now=True))
    # Chrome shows a '"<extension>" started debugging this browser' info bar only while the agent's commands run; it pushes the
    # page down ~56 pt. Frames WITHOUT the bar are idle time AND have a different layout, so they are skipped
    # (the clock is paused), keeping every recorded frame's layout identical. --keep-idle disables this.
    probe_y = a.bar_probe_y
    def bar_present(buf):
        row = probe_y * stride
        px = [buf[row + x * 4: row + x * 4 + 3] for x in range(20, min(iw, 900), 40)]
        lum = sum(0.3 * p[2] + 0.59 * p[1] + 0.11 * p[0] for p in px) / len(px)
        return lum < 110
    t0, n, last, paused_at, skipped = time.time(), 0, None, None, 0
    times, last_t = [], 0.0  # wall-clock capture time of every written frame (→ <out>.frames.json, for cursor_overlay.py)
    titles, title_t = [], 0.0  # the window's title (= its visible tab) over time, so a tab switch can be spotted in QA
    while not stop["now"]:
        cap_t = time.time()
        if cap_t - title_t >= 1.0:
            title_t = cap_t
            info = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionIncludingWindow, wid) or [{}]
            name = info[0].get("kCGWindowName") or ""
            if not titles or titles[-1][1] != name:
                titles.append([round(cap_t, 3), name])
        img = Quartz.CGWindowListCreateImage(Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow, wid, opts)
        if img is not None and Quartz.CGImageGetWidth(img) == iw and Quartz.CGImageGetHeight(img) == ih:
            buf = bytes(Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(img)))
            if a.keep_idle or bar_present(buf):
                if paused_at is not None:  # resume: shift the clock so the pause leaves no gap
                    t0 += time.time() - paused_at
                    paused_at = None
                last, last_t = buf, cap_t
            else:
                if paused_at is None:
                    paused_at = time.time()
                skipped += 1
                time.sleep(1 / a.fps)
                continue
        if last is None:
            time.sleep(0.01)
            continue
        due = int((time.time() - t0) * a.fps) + 1  # frames that should exist by now (keeps real-time duration)
        if due - n > a.max_catchup:  # encoder/pipe fell behind: drop the backlog instead of piling up duplicates
            t0 = time.time() - (n + 1) / a.fps
            due = n + 1
        while n < due:
            ff.stdin.write(last)
            times.append(round(last_t, 3))
            n += 1
        nxt = t0 + n / a.fps
        time.sleep(max(0, nxt - time.time()))
    print(f"frames written {n}, idle frames skipped {skipped}", file=sys.stderr)
    ff.stdin.close()
    ff.wait()
    # page CSS px → video px: ((css * scale + viewport_origin) - crop_xy) * 1920 / crop_w
    Path(a.out + ".frames.json").write_text(json.dumps({"fps": a.fps, "crop": a.crop, "scale": a.scale,
                                                        "viewport_origin": [0, a.vp_y],
                                                        "out": [w, h] if a.native else [1920, 1080],
                                                        "titles": titles, "t": times}))


def cmd_start(a):
    if a.mode == "window":
        return cmd_start_window(a)
    return cmd_start_screen(a)


def cmd_start_window(a):
    if STATE.exists():
        raise SystemExit(f"A capture seems active ({STATE}); run stop first")
    g = geometry(a)
    b = g["window"]
    w, h, x, y = g["crop"]
    x, y = x - b[0] * g["scale"], y - b[1] * g["scale"]  # screen → window-image coordinates
    wid = chrome_window_id(a.title)
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    log = open(str(out) + ".log", "w")
    p = subprocess.Popen([sys.executable, __file__, "_run_window", str(out), "--wid", str(wid), "--fps", str(a.fps),
                          "--crop", str(w), str(h), str(x), str(y), "--bar-probe-y", str(int((a.ui - 28) * g["scale"])),
                          "--scale", str(g["scale"]), "--vp-y", str(a.ui * g["scale"])]
                         + (["--native"] if a.res == "native" else [])
                         + (["--keep-idle"] if a.keep_idle else []), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         start_new_session=True)
    STATE.write_text(json.dumps({"pid": p.pid, "out": str(out), "t0": time.time(), "crop": [w, h, x, y], "wid": wid}))
    time.sleep(1.0)
    print(f"recording window {wid} → {out}  (pid {p.pid}, crop {w}x{h}+{x}+{y})")


def cmd_start_screen(a):
    if STATE.exists():
        raise SystemExit(f"A capture seems active ({STATE}); run stop first")
    g = geometry(a)
    w, h, x, y = g["crop"]
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    osa('tell application "Google Chrome" to activate')
    time.sleep(0.5)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "avfoundation", "-pixel_format", "uyvy422",
           "-capture_cursor", "1" if a.cursor else "0", "-framerate", str(a.fps), "-i", f"{screen_device()}:none",
           "-vf", f"crop={w}:{h}:{x}:{y},scale=1920:1080:flags=lanczos,fps={a.fps}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(out)]
    log = open(str(out) + ".log", "w")
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    STATE.write_text(json.dumps({"pid": p.pid, "out": str(out), "t0": time.time(), "crop": g["crop"]}))
    time.sleep(1.0)
    print(f"recording → {out}  (pid {p.pid}, crop {w}x{h}+{x}+{y})")


def cmd_stop(a):
    if not STATE.exists():
        raise SystemExit("no active capture")
    st = json.loads(STATE.read_text())
    time.sleep(a.hold)  # keep the final state on screen a moment
    try:
        os.kill(st["pid"], signal.SIGINT)
    except ProcessLookupError:
        pass
    for _ in range(60):
        try:
            os.kill(st["pid"], 0)
            time.sleep(0.25)
        except ProcessLookupError:
            break
    STATE.unlink()
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", st["out"]],
                         capture_output=True, text=True).stdout.strip()
    print(f"saved {st['out']} ({dur}s)")


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tighten import cmd_tighten  # noqa: E402  (kept as a subcommand for convenience)


def cmd_overlays(a):
    """QA: a shrunk page (a mid-take screenshot left the tab in a bigger emulated viewport), the window-title timeline
    (another tab or app on screen), and with --preset claude-in-chrome the extension's overlays leaking in (recording mode
    off, or a page load dropped it): the orange pointer (an arrow-sized orange blob; orange UI that never moves, e.g.
    icons, is ignored) and the orange edge glow (a warm tint along 2+ frame edges). Exits 1 if anything is found."""
    import numpy as np
    from scipy import ndimage
    dims = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0", a.src], capture_output=True, text=True).stdout.strip().split(",")
    W, H = int(dims[0]), int(dims[1])
    k = W / 1920  # size limits below are for 1080p
    ff = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", a.src, "-vf", f"fps={a.fps}",
                           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    masks, blues, glow, shrunk = [], [], [], []
    while True:
        buf = ff.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        f = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        R, G, B = (f[..., i].astype(np.int16) for i in range(3))
        orange = ((R - B) > 55) & (R > 140) & ((R - G) > 30) & (G >= B) & (G < 205)
        masks.append(np.packbits(orange))
        blues.append(f[..., 2][orange])  # blue of the orange pixels only (keeps memory small)
        rb = R - B  # the glow tints the outer ~30 px warm: compare a line near each edge with one further in
        e, d = 3, int(56 * k)
        pairs = [(rb[e, :], rb[d, :]), (rb[-1 - e, :], rb[-1 - d, :]), (rb[:, e], rb[:, d]), (rb[:, -1 - e], rb[:, -1 - d])]
        mid = lambda v: np.median(v[len(v) // 10: -len(v) // 10])
        glow.append(sum(mid(o) - mid(i) > 12 for o, i in pairs) >= 2)
        # shrunk page: an agent screenshot left the tab in a bigger emulated viewport, so the window shows the page
        # scaled down into the top-left corner with an empty band down the right side and along the bottom
        g = f[::8, ::8].mean(axis=2)
        gh, gw = g.shape
        shrunk.append(g[:, int(gw * 0.55):].std() < 2 and g[int(gh * 0.55):, :].std() < 2 and g.std() > 5)
    ff.wait()
    if not masks:
        raise SystemExit(f"could not decode {a.src}")
    unpack = lambda m: np.unpackbits(m)[: W * H].reshape(H, W).astype(bool)
    count = np.zeros((H, W), np.uint16)
    for m in masks:
        count += unpack(m)
    static = count > 0.9 * len(masks)
    # Claude in Chrome's pointer at 1080p: ~28×40 px, its #D97757 outline blended with the cream fill → median blue ≈ 110.
    # App oranges (icons, badges, avatars) are far less blue (< 70), so they don't count even when they aren't static.
    pointer = []
    for m, vals in zip(masks, blues):
        orange = unpack(m)
        blue = np.zeros((H, W), np.uint8)
        blue[orange] = vals
        lab, _ = ndimage.label(orange & ~static, structure=np.ones((3, 3)))
        pointer.append(any(16 * k <= sl[1].stop - sl[1].start <= 48 * k and 24 * k <= sl[0].stop - sl[0].start <= 64 * k
                           and np.median(blue[sl][lab[sl] == j]) > 85
                           for j, sl in enumerate(ndimage.find_objects(lab), 1)))

    def ranges(flags):
        out = []
        for i, on in enumerate(flags):
            t = i / a.fps
            if on and out and t - out[-1][1] <= 1.5 / a.fps:
                out[-1][1] = t
            elif on:
                out.append([t, t])
        return ", ".join(f"{s:.1f}-{e + 1 / a.fps:.1f}s" for s, e in out)

    if a.preset != "claude-in-chrome":          # orange checks only make sense for that extension's overlays
        pointer, glow = [False] * len(pointer), [False] * len(glow)
    n_p, n_g, n_s = sum(pointer), sum(glow), sum(shrunk)
    print(f"{a.src}: {len(masks)} frames checked at {a.fps:g} fps")
    print(f"  orange pointer: {n_p} frames" + (f"  ({ranges(pointer)})" if n_p else ""))
    print(f"  edge glow:      {n_g} frames" + (f"  ({ranges(glow)})" if n_g else ""))
    print(f"  shrunk page:    {n_s} frames" + (f"  ({ranges(shrunk)})" if n_s else ""))
    titles = window_titles(a.src)
    if titles:
        print("  window title:   " + "  →  ".join(f"{t:.1f}s {name[:60]!r}" for t, name in titles)
              + ("   ← check: every title should be the page you recorded" if len({n for _, n in titles}) > 1 else ""))
    if n_p or n_g:
        print("  → recording mode was off there: re-shoot those steps with recording_mode.js injected")
    if n_s:
        print("  → a screenshot during the take shrank the page: cut those ranges or re-shoot without mid-take screenshots")
    if n_p or n_g or n_s:
        sys.exit(1)
    print("  clean")


def window_titles(src):
    """[(clip s, title)] from the recorder's title log, mapped through a tighten map when src is a tightened clip"""
    mp, fp = Path(src + ".map.json"), Path(src + ".frames.json")
    if mp.exists():
        m = json.loads(mp.read_text())
        fr = json.loads(Path(m["src"] + ".frames.json").read_text())
        wall, fps = [fr["t"][min(len(fr["t"]) - 1, int(round(r * fr["fps"])))] for r in m["t"]], m["fps"]
    elif fp.exists():
        fr = json.loads(fp.read_text())
        wall, fps = fr["t"], fr["fps"]
    else:
        return []
    out = []
    for t, name in fr.get("titles", []):
        i = next((k for k, w in enumerate(wall) if w >= t), None)
        if i is not None and (not out or out[-1][1] != name):
            out.append((i / fps, name))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("probe", "start", "fit"):
        s = sub.add_parser(n)
        if n == "start":
            s.add_argument("out")
        s.add_argument("--ui", type=int, default=143, help="Chrome UI height in points above the page")
        s.add_argument("--margin", type=int, default=12, help="left/right inset (px), backup for the activity glow")
        s.add_argument("--margin-top", type=int, default=16, help="top inset (px), backup for the glow")
        s.add_argument("--margin-bottom", type=int, default=44, help="bottom inset (px), backup for an agent's glow / stop button")
        s.add_argument("--scale", type=int, default=2, help="Retina factor")
        s.add_argument("--fps", type=int, default=20)
        s.add_argument("--cursor", action="store_true", help="show the real macOS cursor")
        s.add_argument("--bottom-gap", type=int, default=98, help="(fit) points left free at the screen bottom (Dock)")
        s.add_argument("--mode", choices=["window", "screen"], default="window")
        s.add_argument("--title", default="", help="(window mode) part of the Chrome window title to pick")
        s.add_argument("--keep-idle", action="store_true", help="(window mode) keep frames while the agent is idle")
        s.add_argument("--res", choices=["native", "1080"], default="native",
                       help="(window mode) native = keep the Retina crop (e.g. 2410x1356) so zooms stay sharp")
    r = sub.add_parser("_run_window")
    r.add_argument("out")
    r.add_argument("--wid", type=int, required=True)
    r.add_argument("--fps", type=int, default=20)
    r.add_argument("--crop", type=int, nargs=4, required=True)
    r.add_argument("--bar-probe-y", type=int, default=230, help="pixel row inside Chrome's debugging info bar")
    r.add_argument("--keep-idle", action="store_true")
    r.add_argument("--max-catchup", type=int, default=6, help="max duplicate frames written to catch up")
    r.add_argument("--scale", type=int, default=2)
    r.add_argument("--vp-y", type=int, default=286, help="page viewport top inside the window image (px)")
    r.add_argument("--native", action="store_true")
    s = sub.add_parser("stop")
    s.add_argument("--hold", type=float, default=1.5)
    t = sub.add_parser("tighten")
    t.add_argument("src")
    t.add_argument("dst")
    t.add_argument("--keep", type=float, default=60, help="max seconds of any still stretch to keep")
    t.add_argument("--noise", type=float, default=0.001, help="freezedetect noise tolerance")
    t.add_argument("--cut", nargs="*", help="extra ranges to remove, e.g. 12.5-18.0")
    t.add_argument("--fps", type=int, default=30)
    t.add_argument("--log", help="pointer log of the take: also cut the idle lead-in and tail")
    t.add_argument("--lead", type=float, default=1.5, help="(--log) seconds kept before the first pointer event")
    t.add_argument("--tail", type=float, default=2.5, help="(--log) seconds kept after the last pointer event")
    o = sub.add_parser("overlays")
    o.add_argument("src")
    o.add_argument("--fps", type=float, default=2, help="frames per second to check")
    o.add_argument("--preset", default="none", help="agent extension whose overlays to look for: claude-in-chrome | none")
    a = ap.parse_args()
    {"probe": cmd_probe, "fit": cmd_fit, "start": cmd_start, "_run_window": cmd_run_window, "stop": cmd_stop,
     "tighten": cmd_tighten, "overlays": cmd_overlays}[a.cmd](a)


if __name__ == "__main__":
    main()
