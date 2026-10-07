// Recording mode: hide Claude in Chrome's orange overlays on the current page, and log every pointer move and click.
// Paste this file's contents into the Claude in Chrome javascript_tool on the tab you're recording, before
// `screen_capture.py start` and again after every navigate or reload (a full page load drops the style). Clicks
// inside one single-page app don't drop it. Leave recording mode on for the whole recording.
//
// The extension (content script agent-visual-indicator.js, checked on v1.0.94) injects these elements into the page:
//   #claude-agent-glow-border            orange pulsing inset glow around the viewport     → hidden
//   #claude-agent-stop-container         "Stop Claude" button at the bottom centre           → hidden
//   #claude-static-indicator-container   "Claude is active in this tab group" pill           → hidden
//   #claude-phantom-cursor               the pointer, following every hover/click; it holds two stacked arrows:
//     #claude-phantom-cursor-styled      cream arrow, orange outline + glow (on top)         → hidden
//     #claude-phantom-cursor-plain       black arrow with a white rim (underneath)           → CURSOR decides
// The extension only sets inline styles without !important, so these !important rules win.
//
// CURSOR = "hidden" (default): no pointer in the footage. cursor_overlay.py draws a human-moving Mac cursor in the edit, from
//   the pointer log this snippet keeps (sessionStorage "tv-pointer-log": wall-clock ms, CSS px, move/down/up, and the
//   cursor shape the page asks for there). The log survives reloads of this tab.
//   Clear it before a take:  sessionStorage.removeItem("tv-pointer-log")
//   Read it after the take (compact, so it isn't cut off; save the result as screen/raw/<clip>.pointer.json):
//     (() => { const a = JSON.parse(sessionStorage.getItem("tv-pointer-log") || "[]"), t0 = a.length ? a[0].t : 0;
//              return JSON.stringify({ t0, ev: a.map(e => [e.t - t0, e.e[0], e.x, e.y, e.c[0]]) }); })()
//   (very long takes: add .slice(0, 150), .slice(150, 300) … after a.map(…) and join the parts)
// CURSOR = "plain": the black arrow is the video's cursor (quick fallback: no edit step, but robotic glides).
// Turn recording mode off:  document.getElementById("tv-recording-mode")?.remove()
(() => {
  const CURSOR = "hidden"; // house default: the cursor is drawn in the edit (cursor_overlay.py)
  const SCALE = 1.5; // (plain) tutorial-size pointer (Screen Studio/Loom style); 1 = the extension's native size
  document.getElementById("tv-recording-mode")?.remove();
  const s = document.createElement("style");
  s.id = "tv-recording-mode";
  s.textContent = `
    #claude-agent-glow-border, #claude-agent-stop-container, #claude-static-indicator-container,
    #claude-phantom-cursor-styled { display: none !important; }
    #claude-phantom-cursor-plain { transform: scale(${SCALE}); transform-origin: 0 0; }
    ${CURSOR === "hidden" ? "#claude-phantom-cursor { visibility: hidden !important; }" : ""}`;
  document.documentElement.appendChild(s); // not <head>: some apps re-render their head

  if (!window.__tvPointerLog) {
    window.__tvPointerLog = true;
    const KEY = "tv-pointer-log";
    const shape = (x, y) => {
      const el = document.elementFromPoint(x, y);
      const c = el ? getComputedStyle(el).cursor : "auto";
      if (c === "pointer") return "hand";
      if (c === "text" || (c === "auto" && el && (el.isContentEditable || /^(INPUT|TEXTAREA)$/.test(el.tagName)))) return "ibeam";
      return "arrow";
    };
    const log = (e, x, y) => {
      let a;
      try { a = JSON.parse(sessionStorage.getItem(KEY) || "[]"); } catch { a = []; }
      a.push({ t: Date.now(), e, x: Math.round(x), y: Math.round(y), c: shape(x, y) });
      try { sessionStorage.setItem(KEY, JSON.stringify(a)); } catch {}
    };
    // Moves come from the extension's pointer element: it gets every hover/click target, even inside iframes.
    let last = "";
    const moved = (el) => {
      const m = /translate3d\(([-\d.]+)px,\s*([-\d.]+)px/.exec(el.style.transform);
      if (m && m[0] !== last) { last = m[0]; log("move", +m[1], +m[2]); }
    };
    const watch = (el) => { moved(el); new MutationObserver(() => moved(el)).observe(el, { attributes: true, attributeFilter: ["style"] }); };
    const cur = document.getElementById("claude-phantom-cursor");
    if (cur) watch(cur);
    new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach((n) => n.id === "claude-phantom-cursor" && watch(n))))
      .observe(document.body, { childList: true });
    addEventListener("pointerdown", (ev) => log("down", ev.clientX, ev.clientY), true);
    addEventListener("pointerup", (ev) => log("up", ev.clientX, ev.clientY), true);
  }
  const n = (sessionStorage.getItem("tv-pointer-log") || "[]").split('"e"').length - 1;
  return `recording mode on (${location.host}), cursor ${CURSOR}, pointer log: ${n} events`;
})()
