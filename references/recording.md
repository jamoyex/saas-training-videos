# Recording takes with Playwright

Every take is a small JavaScript steps file run by `scripts/pw_record.py` inside a real, visible Chrome with a saved
login. The recorder captures only the page (no other tabs or apps), at a 1280×720 page × 2 = 2560×1440, 30 fps,
without a pointer. Every pointer move and press is logged so the edit can draw a human cursor later.

## 1. Profiles and login

```
python3 scripts/pw_record.py login acme https://app.acme.com/login     # visible Chrome; the USER signs in
python3 scripts/pw_record.py open  acme https://app.acme.com/dashboard # each session (reuses the saved login)
python3 scripts/pw_record.py close acme
```
- One **profile per app account** (`acme`, `acme-admin`, `billing-sandbox`). The login lives in
  `$TRAINING_VIDEO_HOME/pw-<profile>/` (default `~/.training-video/`). That folder *is* the session: never copy it into
  a project, never commit it. `pw_record.py cli <profile> delete-data` (or deleting the folder) logs out.
- **The agent never types passwords or 2FA codes.** `login` opens the page and waits; the user signs in, switches to
  the demo workspace, and says when done. If a take lands on a sign-in page later, the session expired: `login` again.
- `open` options: `--viewport 1440x900` (default 1280x720), `--scale 2` (footage = viewport × scale), and
  `--fake-mic caller.wav` (the page hears that WAV as microphone input: test calls to voice agents, dictation, meeting
  apps). Changing options means re-opening (the recorder closes and reopens the session).
- Use a **demo account with fake data**. Decide the data before recording (names, `example.com` emails,
  `555-01xx` numbers, a fictional company) and keep it consistent across videos.

## 2. Explore before you script

Look at the real screen first; never guess locators.
```
python3 scripts/pw_record.py cli acme screenshot --filename=/abs/path/shot.png     # what the page looks like now
python3 scripts/pw_record.py cli acme snapshot                                     # accessibility tree (roles, names, refs)
python3 scripts/pw_record.py cli acme eval "() => document.title"
python3 scripts/pw_record.py cli acme generate-locator e62                         # a stable locator for a snapshot ref
python3 scripts/pw_record.py cli acme mousemove 640 300 / mousedown / mouseup / press Escape / reload / goto <url>
```
Snapshots and console logs go to `$TRAINING_VIDEO_HOME/pw-<profile>.out/.playwright-cli/`, not the project.
While exploring, **cancel** forms you open (don't save), and note every label, dialog and loading delay you'll need.

## 3. The steps file

```js
const START = [760, 420];                      // where the (hidden) pointer rests when recording starts
async function setup() {                       // NOT recorded: get to the start state, let late UI settle
  await go('/app/contacts');
  await settle(page.getByRole('button', { name: 'Add contact' }), 2000);
}
async function take() {                        // recorded: one call per action the narration will name
  await click(page.getByRole('button', { name: 'Add contact' }), { ready: page.getByRole('dialog'), after: 1200 });
  await type(page.getByLabel('First name'), 'Jamie', { delay: 90 });
  await hover(page.getByText('Lifecycle stage'), { settle: 1500 });
  await click(page.getByRole('dialog').getByRole('button', { name: 'Save', exact: true }), { after: 2000 });
}
```

Helpers in scope (target = a Playwright locator, or `[x, y]` in page CSS px):

| Helper | What it does |
|---|---|
| `go(url)` | navigate (a path is resolved against the current origin) |
| `settle(locator, ms)` | wait until visible, then `ms` more (late menus, banners, counters) |
| `hover(target, {settle})` | one glide onto the target, rest `settle` ms (default 850) — for pointing things out |
| `click(target, {ready, after, settle})` | glide, settle, press; then wait for `ready` (a locator) and `after` ms |
| `clickAt(target, dx, dy, opts)` | click a point inside the target's box (e.g. the free half of a button a chat widget covers) |
| `type(target, text, {delay, after})` | click the field (or `null` = keep focus) and type at a human pace |
| `press(key, {after})` | `Enter`, `Escape`, `Meta+a`, `End` … |
| `scroll(dy, {at})` / `smooth(dy, [x, y])` | wheel scroll; `smooth` = several small steps (readable on video) |
| `dismiss(target)` | click only if present (cookie banners, "what's new" popups, tours) |
| `rest(x, y, ms)` | park the pointer (the recorder rests at the end of every take) |
| `wait(ms)`, `page` | raw Playwright when you need it |

Run it: `python3 scripts/pw_record.py take acme screen/steps/S03_ADD.js screen/raw/S03_ADD.webm`. It writes
`S03_ADD.webm`, `S03_ADD.webm.frames.json` (time of every frame), `S03_ADD.pointer.json` (moves/presses with cursor
shape), prints every press with its time, and a QA line. Keep the sidecars next to the clip; don't rename or re-encode
the raw `.webm`.

## 4. Iframes (embedded builders, calendars, payment widgets, help widgets)

Use frame locators as usual — `const F = page.frameLocator('iframe[src*="calendar"]'); await click(F.getByText('New'))`.
The page's own pointer logger can't see inside a cross-origin iframe, so `hover`/`click`/`clickAt`/`type` detect a
target inside a frame and write the log entry themselves (page coordinates, cursor shape from the element's CSS). Raw
`page.mouse` calls inside an iframe are NOT logged: use the helpers.

## 5. After a take

```
python3 scripts/contact_sheet.py screen/raw/S03_ADD.webm --every 2 --out sheet.jpg        # look before moving on
python3 scripts/screen_capture.py tighten screen/raw/S03_ADD.webm screen/tight/S03_ADD.mp4 --fps 30 --keep 60 \
        --log screen/raw/S03_ADD.pointer.json [--cut 12.4-27.9]
python3 scripts/pointer_events.py . S03_ADD                                                 # click times, tight timeline
```
`--keep 60` keeps every pause (hovers and reading time matter); only the idle lead-in/tail go. Use `--cut A-B` for blank
page loads and long spinners — only where no pointer event falls inside the range. `tighten` writes `<tight>.map.json`
(the raw time of each tight frame); keep it.

## 6. Pitfalls (each one cost a re-shoot)

1. **Visible window only.** Headless screencasts come out at 1× (small page in a big grey frame). The recorder always
   opens Chrome visibly; it may sit behind other windows, but nobody should click inside it during a take.
2. **No automation bar.** Chrome's "controlled by automated test software" bar squeezes the page; the recorder turns it
   off. A QA warning about a grey band means re-open with `pw_record.py open` and re-shoot.
3. **Stray real-mouse events.** If a person's mouse crosses the window during a take, its moves enter the log. The
   recorder drops move-bursts automatically (scripted moves are single jumps) and keeps the unfiltered log as
   `<clip>.pointer.raw.json`. Still: ask the user not to touch that window.
4. **Wait for the page, not the clock.** Loads vary 1–5 s between takes. Every click that loads something gets a `ready`
   locator (the new heading, a count like `/^\d+ contacts$/`, the dialog). Late UI settles in `setup()`.
5. **Locator traps.** `getByText('Save')` is a substring match: use `{ exact: true }`, scope to the dialog
   (`page.getByRole('dialog').getByRole('button', { name: 'Save', exact: true })`), or `.first()`/`.last()` knowingly.
   A label that also appears in a description, a tooltip, a menu AND the card you just created will match several
   elements — the take stops with "strict mode violation": scope it and re-run.
6. **Hover spots inside scrolling boxes**: a locator's center can be outside the visible part of a long editor or panel;
   hover an `[x, y]` inside the visible area instead.
7. **Unsaved-changes dialogs**: a take can't answer the browser's leave-page prompt. Before re-running a take on a page
   with unsaved edits: `cli <profile> reload`, then `cli <profile> dialog-accept`.
8. **Rich text editors** (ProseMirror, Tiptap, Quill): paste with a synthetic `ClipboardEvent('paste')` carrying
   `text/html` (one `<p>` per line) instead of typing paragraphs; typing a few words is fine.
9. **Takes that change data**: record settings changes so that Save is the last step of the run. If a take stops halfway
   *after* it created something, don't re-shoot from the start (you'd create a duplicate): keep the footage and record a
   continuation take from the current page state (`S02a`, `S02b`, …); the cut between them is invisible after tighten.
10. **Popups that appear sometimes** (what's-new modals, auto-save intros, cookie banners): handle them in `setup()`, or
    with `dismiss()` in the take so the take works whether or not they show.
11. **AI features with variable latency** (assistants, generators): give each request its own take that ends when the
    page has stopped changing for ~8 s; cut the wait with `--cut` and have the narration say it was sped up. Never
    re-send a request that creates data.
12. **Personal data on screen** (the signed-in user's name or email in a greeting/avatar): blur it in the tight clip with
    ffmpeg (`crop` + `boxblur` + `overlay=…:enable='between(t,a,b)'`), keeping the frame count identical.
13. **A wrong hover spot** can be fixed without re-shooting: edit that event's `x, y` in `<clip>.pointer.json` (page px)
    and rebuild the segment. Keep the original log next to it.
14. **Paid steps** (buying a number, upgrading a plan, sending to real recipients): film up to the confirm button and
    narrate the rest. Some purchases also trigger identity checks the agent must never complete.
15. **The fallback recorder** (`screen_capture.py start/stop` + `recording_mode.js`, macOS, for apps that refuse automated
    browsers) records the user's real Chrome window via a browser extension; see its docstring. Prefer Playwright.
