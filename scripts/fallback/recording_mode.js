// Recording mode (fallback recorder only): hide an agent extension's on-page overlays and log every pointer move and
// click, so the edit can draw a human cursor. For agents that drive the user's own Chrome through an extension.
// Paste this file's contents into the extension's run-JavaScript tool on the tab you're recording, before
// `window_recorder.py start` and again after every navigate or reload (a full page load drops the style). Clicks
// inside one single-page app don't drop it. Leave recording mode on for the whole recording.
//
// PRESET picks which extension's overlays to hide (add your own: CSS selectors of its glow / stop button / pointer):
//   "claude-in-chrome"  Claude in Chrome (content script agent-visual-indicator.js, checked on v1.0.94):
//       #claude-agent-glow-border (orange viewport glow), #claude-agent-stop-container ("Stop" button),
//       #claude-static-indicator-container (status pill), #claude-phantom-cursor (its pointer: a styled orange arrow
//       on top of a plain black one). The extension only sets inline styles without !important, so these rules win.
//   "none"              nothing to hide (the agent dispatches real mouse events and draws nothing on the page).
//
// CURSOR = "hidden" (default): no pointer in the footage; cursor_overlay.py draws one in the edit from the pointer log
//   kept here (sessionStorage "tv-pointer-log": wall-clock ms, CSS px, move/down/up, and the cursor shape the page asks
//   for there). The log survives reloads of this tab.
//   Clear it before a take:  sessionStorage.removeItem("tv-pointer-log")
//   Read it after the take (compact; save the result as screen/raw/<clip>.pointer.json):
//     (() => { const a = JSON.parse(sessionStorage.getItem("tv-pointer-log") || "[]"), t0 = a.length ? a[0].t : 0;
//              return JSON.stringify({ t0, ev: a.map(e => [e.t - t0, e.e[0], e.x, e.y, e.c[0]]) }); })()
//   (very long takes: add .slice(0, 150), .slice(150, 300) … after a.map(…) and join the parts)
// CURSOR = "plain": keep the extension's plain pointer (if the preset has one) as the video's cursor (no edit step).
// Turn recording mode off:  document.getElementById("tv-recording-mode")?.remove()
(() => {
  const PRESET = "claude-in-chrome"; // which agent extension's overlays to hide: see the list above
  const CURSOR = "hidden";           // the cursor is drawn in the edit (cursor_overlay.py)
  const SCALE = 1.5;                 // (plain) tutorial-size pointer; 1 = the extension's native size
  const PRESETS = {
    "claude-in-chrome": {
      hide: ["#claude-agent-glow-border", "#claude-agent-stop-container", "#claude-static-indicator-container",
             "#claude-phantom-cursor-styled"],
      pointer: "claude-phantom-cursor",          // element whose transform follows the agent's pointer (id)
      plain: "#claude-phantom-cursor-plain",     // the plain arrow inside it (kept when CURSOR = "plain")
    },
    "none": { hide: [], pointer: null, plain: null },
  };
  const P = PRESETS[PRESET];
  document.getElementById("tv-recording-mode")?.remove();
  const s = document.createElement("style");
  s.id = "tv-recording-mode";
  s.textContent = [
    P.hide.length ? `${P.hide.join(", ")} { display: none !important; }` : "",
    P.plain ? `${P.plain} { transform: scale(${SCALE}); transform-origin: 0 0; }` : "",
    CURSOR === "hidden" && P.pointer ? `#${P.pointer} { visibility: hidden !important; }` : "",
  ].join("\n");
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
    if (P.pointer) {
      // Moves come from the extension's pointer element: it gets every hover/click target, even inside iframes.
      let last = "";
      const moved = (el) => {
        const m = /translate3d\(([-\d.]+)px,\s*([-\d.]+)px/.exec(el.style.transform);
        if (m && m[0] !== last) { last = m[0]; log("move", +m[1], +m[2]); }
      };
      const watch = (el) => { moved(el); new MutationObserver(() => moved(el)).observe(el, { attributes: true, attributeFilter: ["style"] }); };
      const cur = document.getElementById(P.pointer);
      if (cur) watch(cur);
      new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach((n) => n.id === P.pointer && watch(n))))
        .observe(document.body, { childList: true });
    } else {
      addEventListener("pointermove", (ev) => log("move", ev.clientX, ev.clientY), true);
    }
    addEventListener("pointerdown", (ev) => log("down", ev.clientX, ev.clientY), true);
    addEventListener("pointerup", (ev) => log("up", ev.clientX, ev.clientY), true);
  }
  const n = (sessionStorage.getItem("tv-pointer-log") || "[]").split('"e"').length - 1;
  return `recording mode on (${location.host}), preset ${PRESET}, cursor ${CURSOR}, pointer log: ${n} events`;
})()
