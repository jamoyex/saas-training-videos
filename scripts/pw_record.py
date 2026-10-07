#!/usr/bin/env python3
"""Record SaaS walkthrough takes with the Playwright CLI: scripted, repeatable, pointer-logged screen footage.

  python3 pw_record.py login  <profile> <url>                      # visible Chrome; the USER logs in (once per profile)
  python3 pw_record.py open   <profile> [<url>] [--viewport 1280x720] [--scale 2] [--fake-mic caller.wav]
  python3 pw_record.py take   <profile> steps/S03_ADD.js screen/raw/S03_ADD.webm   # one take → webm + timing sidecars
  python3 pw_record.py cli    <profile> snapshot | screenshot --filename=/abs/x.png | eval "() => document.title" | reload …
  python3 pw_record.py close  <profile>

Setup: `npm i -g @playwright/cli` and Google Chrome. One PROFILE per app login (e.g. "acme-crm", "billing-demo"). The
saved login lives in $TRAINING_VIDEO_HOME/pw-<profile>/ (default ~/.training-video/): that folder IS the logged-in session.
Never copy it into a project, never commit it. The agent never types passwords: `login` opens the page, the user signs
in (2FA included), picks the demo workspace, and says when they're done.

The browser is real Chrome, VISIBLE (headless screencasts come out at 1×), with a 1280×720 page at 2× → 2560×1440 footage
(sharp enough for ~1.8× zooms in the edit), and without the "controlled by automated test software" bar. Only the page is
recorded: never other tabs, apps, or anything the agent draws. Nobody should click in that window during a take.

A take is a steps file (templates/take_example.js) with two functions: setup() brings the page to its start state (not
recorded) and take() performs the take (recorded). In scope: page, wait, go, settle, hover, click, clickAt, type, press,
scroll, smooth, rest, dismiss. Each pointer step is ONE glide to the target, a settle (0.85 s), then the press, and waits
for the page to be ready (a locator) rather than for fixed seconds.

Pointer log: the page logs every pointer move/press/release. Targets inside an IFRAME (embedded apps, builders, payment
widgets) are invisible to that logger, so hover/click/type detect them and write the event themselves (page coordinates,
cursor shape from the element's CSS). Use frame locators as usual: page.frameLocator('iframe[src*="app"]').getByRole(...).

A take writes, next to the clip:
  <clip>.webm               the footage (viewport × scale, 30 fps, no pointer)
  <clip>.webm.frames.json   wall-clock time of every frame + geometry (tighten / cursor_overlay / assembler)
  <clip>.pointer.json       the pointer log (the edit draws the cursor from it)
Next: screen_capture.py tighten <clip>.webm tight/<id>.mp4 --fps 30 --keep 60 --log <clip>.pointer.json
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path(os.environ.get("TRAINING_VIDEO_HOME", Path.home() / ".training-video"))
VIEWPORT, DSF, FPS = (1280, 720), 2, 30

PRELUDE = r"""
async page => {
  const OUT = __OUT__, FPS = __FPS__, KEY = 'tv-pointer-log';
  const wait = (ms) => page.waitForTimeout(ms);
  const logger = () => {
    if (window.__tvPointerLog || window !== window.top) return;
    window.__tvPointerLog = true;
    const KEY = 'tv-pointer-log';
    const shape = (x, y) => {
      const el = document.elementFromPoint(x, y);
      const c = el ? getComputedStyle(el).cursor : 'auto';
      if (c === 'pointer') return 'hand';
      if (c === 'text' || (c === 'auto' && el && (el.isContentEditable || /^(INPUT|TEXTAREA)$/.test(el.tagName)))) return 'ibeam';
      return 'arrow';
    };
    const log = (e, ev) => {
      let a; try { a = JSON.parse(sessionStorage.getItem(KEY) || '[]'); } catch { a = []; }
      a.push({ t: Date.now(), e, x: Math.round(ev.clientX), y: Math.round(ev.clientY), c: shape(ev.clientX, ev.clientY) });
      try { sessionStorage.setItem(KEY, JSON.stringify(a)); } catch {}
    };
    addEventListener('pointermove', (ev) => log('move', ev), true);
    addEventListener('pointerdown', (ev) => log('down', ev), true);
    addEventListener('pointerup', (ev) => log('up', ev), true);
  };
  await page.addInitScript(logger);
  await page.evaluate(logger);

  // manual log entry (used for targets inside iframes, which the page logger can't see)
  const mlog = (e, x, y, c) => page.evaluate(({ e, x, y, c, K }) => {
    let a; try { a = JSON.parse(sessionStorage.getItem(K) || '[]'); } catch { a = []; }
    a.push({ t: Date.now(), e, x: Math.round(x), y: Math.round(y), c }); sessionStorage.setItem(K, JSON.stringify(a));
  }, { e, x, y, c, K: KEY });
  const framed = async (t) => { if (Array.isArray(t)) return null; try {
    return await t.first().evaluate((el) => {
      if (window === window.top) return null;
      const c = getComputedStyle(el).cursor;
      return c === 'pointer' ? 'hand' : (c === 'text' || el.isContentEditable || /^(INPUT|TEXTAREA)$/.test(el.tagName)) ? 'ibeam' : 'arrow';
    }); } catch { return null; } };

  // helpers for steps files. target = a locator (getByRole/getByText/getByLabel/getByPlaceholder…) or [x, y] in page px
  const at = async (target) => {
    if (Array.isArray(target)) return target;
    await target.first().waitFor({ state: 'visible', timeout: 20000 });
    await target.first().scrollIntoViewIfNeeded();
    const b = await target.first().boundingBox();
    return [b.x + b.width / 2, b.y + b.height / 2];
  };
  const go = async (url) => { await page.goto(url.startsWith('/') ? new URL(page.url()).origin + url : url); };
  const settle = async (ready, ms = 2500) => { if (ready) await ready.first().waitFor({ state: 'visible', timeout: 30000 }); await wait(ms); };
  const moveTo = async (x, y, shape, ms) => { await page.mouse.move(x, y); if (shape) await mlog('move', x, y, shape); await wait(ms); };
  const pressAt = async (x, y, shape) => {
    if (shape) await mlog('down', x, y, shape);
    await page.mouse.down(); await wait(90); await page.mouse.up();
    if (shape) await mlog('up', x, y, shape);
  };
  const hover = async (target, { settle = 850 } = {}) => { const [x, y] = await at(target); await moveTo(x, y, await framed(target), settle); };
  const click = async (target, { settle = 850, ready = null, after = 1500 } = {}) => {
    const [x, y] = await at(target); const shape = await framed(target);
    await moveTo(x, y, shape, settle); await pressAt(x, y, shape);
    if (ready) await ready.first().waitFor({ state: 'visible', timeout: 30000 });
    await wait(after);
  };
  // click a point inside the target's box (dx, dy from its top-left), e.g. the free half of a button a chat bubble covers
  const clickAt = async (target, dx, dy = null, { settle = 850, ready = null, after = 1500 } = {}) => {
    await at(target); const b = await target.first().boundingBox(); const shape = await framed(target);
    const x = b.x + dx, y = b.y + (dy === null ? b.height / 2 : dy);
    await moveTo(x, y, shape, settle); await pressAt(x, y, shape);
    if (ready) await ready.first().waitFor({ state: 'visible', timeout: 30000 });
    await wait(after);
  };
  const type = async (target, text, { delay = 80, after = 700 } = {}) => {
    if (target) await click(target, { after: 400 });
    await page.keyboard.type(text, { delay });
    await wait(after);
  };
  const press = async (key, { after = 600 } = {}) => { await page.keyboard.press(key); await wait(after); };
  const scroll = async (dy, { at: p = null, after = 900 } = {}) => {
    if (p) await page.mouse.move(p[0], p[1]);
    await page.mouse.wheel(0, dy); await wait(after);
  };
  // a readable scroll: several small wheel steps over the panel under [x, y]
  const smooth = async (dy, p, steps = 6) => { await page.mouse.move(p[0], p[1]); for (let i = 0; i < steps; i++) { await page.mouse.wheel(0, dy / steps); await wait(70); } await wait(700); };
  // close an optional popup (cookie banner, "what's new", onboarding tip) only if it is there
  const dismiss = async (target, o = {}) => { if (await target.first().isVisible().catch(() => false)) await click(target, { after: 800, ...o }); };
  const rest = async (x = 820, y = 420, ms = 1500) => { await page.mouse.move(x, y); await wait(ms); };

  // ---- steps file ----
__STEPS__
  // ---- end of steps file ----

  if (typeof setup === 'function') await setup();
  await page.evaluate((k) => sessionStorage.removeItem(k), KEY);
  await page.mouse.move(typeof START !== 'undefined' ? START[0] : 760, typeof START !== 'undefined' ? START[1] : 330);
  await wait(300);
  const vp = page.viewportSize(), dpr = await page.evaluate(() => devicePixelRatio);
  const size = { width: Math.round(vp.width * dpr), height: Math.round(vp.height * dpr) };
  const frames = [];
  await page.screencast.start({ path: OUT, size, fps: FPS, quality: 90,
    onFrame: ({ timestamp }) => { frames.push([timestamp, Date.now()]); } });
  let error = null;
  try {
    await wait(1200);
    await take();
    await rest();
  } catch (e) { error = String(e && e.message || e); }
  await page.screencast.stop();
  const log = await page.evaluate((k) => JSON.parse(sessionStorage.getItem(k) || '[]'), KEY);
  return JSON.stringify({ frames, log, error, url: page.url(), viewport: vp, dpr, size });
}
"""


def paths(profile):
    HOME.mkdir(mode=0o700, parents=True, exist_ok=True)
    out = HOME / f"pw-{profile}.out"          # the CLI's snapshots/console logs go here, never into a project folder
    out.mkdir(exist_ok=True)
    return HOME / f"pw-{profile}", HOME / f"pw-{profile}.config.json", out


def write_config(profile, viewport=VIEWPORT, scale=DSF, fake_mic=None):
    data, cfg, _ = paths(profile)
    launch = {"channel": "chrome", "headless": False, "ignoreDefaultArgs": ["--enable-automation"]}
    context = {"viewport": {"width": viewport[0], "height": viewport[1]}, "deviceScaleFactor": scale}
    if fake_mic:
        # the page "hears" this file as the microphone (test calls to voice agents, dictation features …)
        launch["args"] = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                          f"--use-file-for-fake-audio-capture={Path(fake_mic).resolve()}%noloop"]
        context["permissions"] = ["microphone"]
    cfg.write_text(json.dumps({"browser": {"browserName": "chromium", "userDataDir": str(data),
                                           "launchOptions": launch, "contextOptions": context}}, indent=2))
    return cfg


def cli(profile, *args, capture=False):
    _, _, out = paths(profile)
    cmd = ["playwright-cli", f"-s={profile}", *args]
    if capture:
        return subprocess.run(cmd, cwd=out, capture_output=True, text=True)
    return subprocess.run(cmd, cwd=out).returncode


def cmd_open(a, login=False):
    vw, vh = (int(v) for v in a.viewport.lower().split("x"))
    cfg = write_config(a.profile, (vw, vh), a.scale, a.fake_mic)
    cli(a.profile, "close", capture=True)                       # a session opened with other settings won't pick up the config
    args = ["open"] + ([a.url] if a.url else []) + ["--headed", f"--config={cfg}"]
    rc = cli(a.profile, *args)
    if login:
        print(f"\nA Chrome window is open at {a.url}. Ask the user to sign in there (and enter any security code),\n"
              f"switch to the demo workspace, and tell you when done. Never type the password yourself.")
    return rc


def cmd_take(a):
    steps = Path(a.steps).read_text()
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    js = PRELUDE.replace("__OUT__", json.dumps(str(out))).replace("__FPS__", str(a.fps)).replace("__STEPS__", steps)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
    r = cli(a.profile, "run-code", "--raw", f"--filename={f.name}", capture=True)
    Path(f.name).unlink()
    txt = r.stdout.strip()
    try:
        d = json.loads(txt)
        d = json.loads(d) if isinstance(d, str) else d
    except json.JSONDecodeError:
        sys.exit(f"take failed:\n{txt[:2000]}\n{r.stderr[:1000]}\n(if a screencast was left running: "
                 f"pw_record.py cli {a.profile} run-code \"async page => page.screencast.stop()\")")
    if not d["frames"]:
        sys.exit("no frames recorded")
    f0 = d["frames"][0][0]
    f0 = f0 * 1000 if f0 < 1e11 else f0                       # screencast timestamps: ms since epoch (s on older builds)
    W, H = d["size"]["width"], d["size"]["height"]
    n = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout)
    # Playwright writes constant-fps frames from the first screencast frame (checked against page reactions: ±1 frame)
    Path(str(out) + ".frames.json").write_text(json.dumps({
        "fps": a.fps, "crop": [W, H, 0, 0], "scale": d["dpr"], "viewport_origin": [0, 0], "out": [W, H], "titles": [],
        "t": [round(f0 / 1000 + k / a.fps, 4) for k in range(n)], "source": "playwright", "url_end": d["url"]}))
    raw_log, d["log"], stray = d["log"], *split_stray(d["log"])
    Path(out.with_suffix(".pointer.json")).write_text(json.dumps(d["log"]))
    if stray:
        Path(out.with_suffix(".pointer.raw.json")).write_text(json.dumps(raw_log))
        print(f"  removed {stray} stray pointer events (a real mouse crossed the window; unfiltered log: "
              f"{out.with_suffix('.pointer.raw.json').name})")

    print(f"{out.name}: {n / a.fps:.1f}s, {W}x{H} @ {a.fps} fps, {len(d['log'])} pointer events, ends on {d['url']}")
    for e in d["log"]:
        if e["e"] != "up":
            print(f"  {(e['t'] - f0) / 1000:6.2f}s  {e['e']:<4} {e['c']:<5} ({e['x']}, {e['y']})")
    problems = qa(out, W, H)
    if d["error"]:
        problems.insert(0, f"the take stopped early: {d['error'][:300]}")
    for p in problems:
        print("  ⚠ " + p)
    print("  QA: clean" if not problems else "  → fix and re-shoot this take (or record a continuation take, if it already changed data)")
    print(f"next: screen_capture.py tighten {a.out} <tight>.mp4 --fps 30 --keep 60 --log {out.with_suffix('.pointer.json')}")
    return 1 if problems else 0


def split_stray(log, gap_ms=60, min_burst=3):
    """Scripted moves are single jumps (one pointermove each); a person's mouse makes bursts of many moves a few ms
    apart. Drop move-bursts (≥ min_burst moves, < gap_ms apart, no press inside) and return (clean_log, n_dropped)."""
    keep, i, dropped = [], 0, 0
    while i < len(log):
        j = i
        while (j + 1 < len(log) and log[j]["e"] == "move" and log[j + 1]["e"] == "move"
               and log[j + 1]["t"] - log[j]["t"] < gap_ms):
            j += 1
        if log[i]["e"] == "move" and j - i + 1 >= min_burst:
            dropped += j - i + 1
        else:
            keep.extend(log[i:j + 1])
        i = j + 1
    return keep, dropped


def qa(out, W, H):
    """grey padding = frames smaller than the canvas (headless 1× capture, or a strip squeezed out of the viewport)"""
    import numpy as np
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                               capture_output=True, text=True).stdout)
    edges = set()
    for t in (dur * 0.3, dur * 0.8):
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(out), "-frames:v", "1",
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
        if len(raw) < W * H:
            continue
        a = np.frombuffer(raw[:W * H], np.uint8).reshape(H, W).astype(float)
        for name, band in (("bottom", a[-24:]), ("right", a[:, -24:])):
            if band.std() < 1.5 and 110 < band.mean() < 145:
                edges.add(name)
    return [f"flat grey band on the {' and '.join(sorted(edges))} edge: the page was captured smaller than the frame "
            f"(headless browser, or Chrome's automation bar). Reopen with pw_record.py open."] if edges else []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("login", "open"):
        s = sub.add_parser(name); s.add_argument("profile"); s.add_argument("url", nargs="?" if name == "open" else None)
        s.add_argument("--viewport", default=f"{VIEWPORT[0]}x{VIEWPORT[1]}", help="page size in CSS px (default 1280x720)")
        s.add_argument("--scale", type=float, default=DSF, help="device scale factor (default 2 → 2560x1440 footage)")
        s.add_argument("--fake-mic", help="WAV/Y4M the page receives as microphone input (test calls, dictation)")
    s = sub.add_parser("take"); s.add_argument("profile"); s.add_argument("steps"); s.add_argument("out")
    s.add_argument("--fps", type=int, default=FPS)
    s = sub.add_parser("close"); s.add_argument("profile")
    s = sub.add_parser("cli"); s.add_argument("profile"); s.add_argument("args", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    if a.cmd == "login":
        sys.exit(cmd_open(a, login=True))
    if a.cmd == "open":
        sys.exit(cmd_open(a))
    if a.cmd == "take":
        sys.exit(cmd_take(a))
    if a.cmd == "close":
        sys.exit(cli(a.profile, "close"))
    sys.exit(cli(a.profile, *a.args))


if __name__ == "__main__":
    main()
