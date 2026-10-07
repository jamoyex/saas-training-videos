#!/usr/bin/env python3
"""Assemble a training video from an EDL (edit decision list) with ffmpeg.

  python3 assemble_video.py edl.json            # builds edl["output"]
  python3 assemble_video.py edl.json --preview  # fast 540p draft (ultrafast, no loudnorm)
  python3 assemble_video.py edl.json --only S03 # rebuild one segment's intermediate, then re-concat

EDL (paths relative to the EDL file; see templates/edl_example.json):
{
  "output": "out/03_add-a-contact.mp4",
  "intro": "brand/intro.mp4",          # optional clip before the first segment (logo sting …); "outro" after the last
  "transition": {"in": "brand/wipe_in.mov", "out": "brand/wipe_out.mov"},   # optional alpha overlays for "wipe_in"
  "loudnorm": true,                    # final −16 LUFS / −1.5 dBTP
  "pip_style": "tutorial",             # default PiP preset: tutorial | lecture
  "segments": [
    {"id":"S01_OPEN",  "type":"full",   "video":"avatar/S01_OPEN.mp4"},
    {"id":"S02_NAV",   "type":"screen", "video":"screen/s02.mov", "pip":"avatar/S02_NAV.mp4", "wipe_in":true, "fit":"pad"},
    {"id":"S03_SLIDES","type":"slides", "slides":[{"image":"slides/01.png","until_say":"The second thing"},{"image":"slides/02.png"}],
                       "pip":"avatar/S03_SLIDES.mp4", "pip_style":"lecture"},
    {"id":"S04_VO",    "type":"image",  "image":"slides/08.png", "audio":"vo/S04_VO.mp3"},
    {"id":"S05_CLOSE", "type":"full",   "video":"avatar/S05_CLOSE.mp4", "wipe_in":true}
  ]
}
Segment keys
  type      full | screen | slides | image
  video     base video (full/screen). image: still for "image" type.
  pip       presenter clip (webcam, avatar) overlaid bottom-right (its audio is the narration unless "audio" is given)
  audio     explicit narration file (mp3/wav); overrides pip/video audio
  duration  force length (s). Default: audio → pip → video length.
  fit       screen video vs narration: auto (default for screen: retime up to 1.6x slower/faster, then hold
            the last frame) | pad (freeze last frame / trim) | speed (exact retime) ; max_slow / max_fast tune auto
  start/end sub-clip of the base video in seconds (screen/full), so one recording can feed several segments
  sync      [{"t": <footage s>, "say": "<phrase from the narration>", "offset": 0}, …] — lands each on-screen event on
            the word that describes it (phrases resolve via vo/<SEG>.words.json, so re-voicing keeps sync). Holds the
            frame just before each event while the narrator talks. With pacing (default) the footage never speeds up
            (see pace). Legacy ("pace": false) speeds through gaps (≤ max_speed, 6×).
  slides    [{"image": …, "until_say": "<first words of the next slide's sentence>", "lead": 0.15}, …, {"image": …}]
            (phrase-timed, so re-voicing keeps slide changes on the right words) or "until": <seconds from segment start>
  pace      (EDL or segment) pacing for synced screen segments, on by default:
            {"max_speed": 1.0, "min_step": 1.2, "lead": 0.25, "tail": 0.8} — footage at real speed, each click 0.25 s
            after its phrase starts, ≥1.2 s per step across a comma/full stop, a beat after the last one. The AUDIO IS
            NEVER EDITED: where the voice leaves too little room, the screen holds and the assembler prints where to add
            a few words (or a pause) to the script. false = legacy.
  cursor    (screen) draw the Mac cursor, presenter gestures and zooms after the sync, in narration time (Claude-driven
            footage has no pointer). true, or {"log": <pointer.json, default found via the clip's timing files>,
            "gestures": [...] | "file.json", "zooms": [...] | "file.json", "size": 1.5, "ring": "#3B82F6"}; gestures and
            zooms can be timed by phrase ("say"/"offset", "until_say" or "hold"). Positions/centers are VIDEO px
            (1920×1080 = page CSS px × 1.5). See scripts/cursor_overlay.py.
  wipe_in   true → play the EDL's "transition" overlays on the cut INTO this segment (out on the previous one)
  pip_style tutorial | lecture;  key: true → chroma-key the green (#00FF00) avatar background
  bg        (full + key) background image placed behind the keyed avatar
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ffprobe_duration, has_audio  # noqa: E402

W, H, FPS = 1920, 1080, 30
PIP = {
    "tutorial": {"w": 480, "h": 330, "margin": 0, "radius": 0},
    "lecture": {"w": 288, "h": 300, "margin": 18, "radius": 16},
}
WIPE = {"in": None, "out": None}          # set from the EDL's "transition" in main()
WIPE_OUT_D, WIPE_IN_D = 0.40, 0.30


def enc_args(preview):
    if preview:
        return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p", "-r", str(FPS),
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


def cover(label_in, label_out, w=W, h=H):
    return (f"[{label_in}]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
            f"fps={FPS},format=yuv420p[{label_out}]")


def rounded_mask(path, w, h, r):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=255)
    m.save(path)
    return path


def run(cmd, verbose=False):
    if verbose:
        print(" ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-4000:])
        raise SystemExit(f"ffmpeg failed ({r.returncode})")


def _norm(tok):
    return re.sub(r"[^0-9a-z]", "", tok.lower())


def load_words(seg, root, audio, sid):
    """The narration's word timings: seg["words"], else <audio>.words.json, else vo/<id>.words.json."""
    for wf in ([root / seg["words"]] if seg.get("words") else []) + \
              ([audio.with_suffix(".words.json")] if audio else []) + [root / "vo" / f"{sid}.words.json"]:
        if wf.exists():
            return json.loads(wf.read_text())
    return None


def find_phrase(words, phrase, pos, sid):
    """Index of the first word of phrase at or after word index pos (case/punctuation-insensitive)."""
    toks = [_norm(w["word"]) for w in words]
    ph = [_norm(x) for x in phrase.split() if _norm(x)]
    hit = next((i for i in range(pos, len(toks) - len(ph) + 1) if toks[i:i + len(ph)] == ph), None)
    if hit is None:
        raise SystemExit(f"{sid}: phrase not found in the narration (in order): {phrase!r}")
    return hit


def resolve_sync(seg, root, audio, sid):
    """Turn seg["sync"] anchors into [(footage_t, output_t)].
    Anchor forms: {"t": 1.15, "say": "Add Contact", "offset": 0.1}  (phrase looked up in the narration's
    words.json, searched in order, so the SAME anchors survive a re-voice) or [1.15, 7.3] (explicit seconds)."""
    anchors = seg.get("sync") or []
    words = load_words(seg, root, audio, sid)
    pos, out = 0, []
    for an in anchors:
        if isinstance(an, (list, tuple)):
            out.append((float(an[0]), float(an[1])))
            continue
        if words is None:
            raise SystemExit(f"{sid}: sync anchor {an} needs a words.json next to the audio")
        hit = find_phrase(words, an["say"], pos, sid)
        pos = hit + 1
        out.append((float(an["t"]), words[hit]["start"] + float(an.get("offset", 0))))
    for (f0, o0), (f1, o1) in zip(out, out[1:]):
        if f1 <= f0 or o1 <= o0:
            raise SystemExit(f"{sid}: sync anchors must increase in both footage and narration time: {out}")
    return out


PACE_DEFAULT = {"max_speed": 1.0, "min_step": 1.2, "lead": 0.25, "tail": 0.8, "max_late": 1.5}
BREAK_END, BREAK_ANY = tuple(".!?"), tuple(".!?,;:")


def pace_settings(edl, seg):
    """Beginner-friendly pacing: EDL "pace" {…} overrides the defaults, a segment's "pace" overrides
    the EDL's, and "pace": false = legacy sync (footage may run up to 6× to keep up with the narration)."""
    if edl.get("pace") is False or seg.get("pace") is False:
        return None
    return {**PACE_DEFAULT, **(edl.get("pace") or {}), **(seg.get("pace") or {})}


def _ends_clause(word, group=BREAK_ANY):
    return word.rstrip('"”’)').endswith(group)


def pace_screen(seg, root, audio, sid, vdur, pace):
    """Pace the SCREEN to the narration, never the narration to the screen: the audio is not edited.
    Room for slow steps comes from the narration itself: a few more words ("give it a second to load…") or a pause
    the voice engine performs, written into script.md between two on-screen steps.
    - footage never runs faster than pace["max_speed"] (1.0 = real time);
    - each event lands pace["lead"] s after its phrase starts (say it, then do it);
    - across a comma/full stop, the previous result stays on screen ≥ pace["min_step"] s before the next event;
    - if the voice doesn't leave that much room, the event lands late (the frame before it holds), and this prints
      where to add a pause tag; after the last event the screen finishes at real speed plus a pace["tail"] s beat.
    Returns (pairs, duration) or None (no words / explicit-second anchors)."""
    words = load_words(seg, root, audio, sid)
    if words is None or any(isinstance(an, (list, tuple)) for an in seg["sync"]):
        return None
    idx, ft, off, pos = [], [], [], 0
    for an in seg["sync"]:
        hit = find_phrase(words, an["say"], pos, sid)
        pos = hit + 1
        idx.append(hit)
        ft.append(float(an["t"]))
        off.append(float(an.get("offset", 0)) + pace["lead"])
    o = lambda i: words[idx[i]]["start"] + off[i]       # noqa: E731
    E, tips = [], []
    for i in range(len(idx)):
        if i == 0:
            earliest, brk = ft[0] / pace["max_speed"], [j for j in range(0, idx[0]) if _ends_clause(words[j]["word"])]
        else:
            brk = [j for j in range(idx[i - 1], idx[i]) if _ends_clause(words[j]["word"])]
            foot = (ft[i] - ft[i - 1]) / pace["max_speed"]
            earliest = E[-1] + (max(foot, pace["min_step"]) if brk else foot)
        late = earliest - o(i)
        if late > 0.5 and brk:
            tips.append((words[brk[-1]]["word"], late))
        E.append(o(i) + max(0.0, late))
    src_dur = ffprobe_duration(audio) or words[-1]["end"]
    need = E[-1] + (vdur - ft[-1]) / pace["max_speed"] + pace["tail"]
    dur = max(src_dur, need)
    for w, late in tips:
        print(f"       {sid}: the screen needs +{late:.1f}s after “{w}” → add ~{max(2, round(late * 2.6))} words "
              f"(or a pause) there in script.md")
    if need - src_dur > 0.5:
        print(f"       {sid}: the screen runs {need - src_dur:.1f}s past the narration → add "
              f"~{max(2, round((need - src_dur) * 2.6))} words at the end of the segment")
    out = root / "vo" / f"{sid}.timing.json"
    pairs = [(ft[i], E[i]) for i in range(len(idx))]
    out.write_text(json.dumps({"pairs": pairs, "pace": pace, "late": [round(E[i] - o(i), 3) for i in range(len(idx))],
                               "tips": tips, "end_hold": round(max(0.0, need - src_dur), 3)}))
    return pairs, dur


def sync_chain(label_in, pairs, vdur, dur, max_speed=6.0):
    """Piecewise retime: every footage event f_i lands exactly at narration time o_i. Where narration needs more time
    than the footage, the frame just BEFORE the next event is held (pointer waiting on its target); where it needs
    less, the footage plays faster (≤ max_speed). Returns filter lines producing [base]."""
    pts = [(0.0, 0.0)] + [(f, o) for f, o in pairs if 0 < f < vdur and 0 < o < dur] + [(vdur, dur)]
    n = len(pts) - 1
    lines = [f"[{label_in}]split={n}" + "".join(f"[sy{i}]" for i in range(n))]
    segs = []
    for i in range(n):
        (fa, oa), (fb, ob) = pts[i], pts[i + 1]
        fin, fout = max(fb - fa, 1 / FPS), max(ob - oa, 1 / FPS)
        c = f"[sy{i}]trim=start={fa:.4f}:end={fa + fin:.4f},setpts=PTS-STARTPTS"
        if fout >= fin:
            c += f",tpad=stop_mode=clone:stop_duration={fout - fin:.4f}"
        else:
            c += f",setpts=PTS*{max(fout / fin, 1 / max_speed):.6f}"
        c += f",trim=duration={fout:.4f},setpts=PTS-STARTPTS[sz{i}]"
        lines.append(c)
        segs.append(f"[sz{i}]")
    lines.append("".join(segs) + f"concat=n={n}:v=1:a=0,fps={FPS},trim=duration={dur:.3f},setpts=PTS-STARTPTS,format=yuv420p[base]")
    return lines


def sync_footage_time(o, pairs, vdur, dur, max_speed):
    """output time → footage time for sync_chain: each piece plays at real speed then holds its last frame, or runs
    faster (≤ max_speed) when the narration is shorter."""
    pts = [(0.0, 0.0)] + [(f, q) for f, q in pairs if 0 < f < vdur and 0 < q < dur] + [(vdur, dur)]
    for (fa, oa), (fb, ob) in zip(pts, pts[1:]):
        if o < ob or (fb, ob) == pts[-1]:
            fin, fout = max(fb - fa, 1 / FPS), max(ob - oa, 1 / FPS)
            r = 1.0 if fout >= fin else max(fout / fin, 1 / max_speed)
            # the hold repeats the piece's LAST frame, one frame before the event, so the event lands at ob
            return fa + min(max(o - oa, 0.0) / r, fin - 1 / FPS)
    return vdur


def resolve_times(items, words, sid, keys):
    """Gestures/zooms may be timed by phrase instead of seconds: {"say": "cheapest price", "offset": 0.2} sets "at"
    (or "from"), "until_say" sets "to", "hold" gives the length. Phrases are searched in order within the list, in the
    (paced) narration, so a re-voice keeps them on the right words."""
    out, pos = [], 0
    for it in items:
        it = dict(it)
        if it.get("say"):
            if words is None:
                raise SystemExit(f"{sid}: cursor timing by phrase needs the narration's words.json")
            hit = find_phrase(words, it["say"], pos, sid)
            pos = hit + 1
            it[keys[0]] = words[hit]["start"] + float(it.get("offset", 0))
        if it.get("until_say"):
            hit = find_phrase(words, it["until_say"], pos, sid)
            it[keys[1]] = words[hit]["start"] + float(it.get("until_offset", 0))
        if it.get("hold") is not None and keys[1] not in it:
            it[keys[1]] = it[keys[0]] + float(it["hold"])
        out.append(it)
    return out


def render_cursor(seg, sid, idx, root, build, a, video, start, dur, foot, audio, inputs, filters):
    """Screen segment with "cursor": render the retimed footage (native resolution, no cursor), write the raw time of
    every output frame next to it, then draw the human cursor, gestures and zooms on it with cursor_overlay.py —
    in narration time, so the cursor moves at human speed however the footage was held or sped up."""
    cfg = seg["cursor"] if isinstance(seg["cursor"], dict) else {}
    base = build / f"{idx:02d}_{sid}_screen.mp4"
    q = ["-preset", "ultrafast", "-crf", "26"] if a.preview else ["-preset", "fast", "-crf", "12"]
    run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[base]", "-an",
         "-t", f"{dur:.3f}", "-c:v", "libx264", *q, "-pix_fmt", "yuv420p", base], a.verbose)
    mp, fp = Path(str(video) + ".map.json"), Path(str(video) + ".frames.json")
    if mp.exists():                                     # a tightened clip: its map gives the raw time of each frame
        m = json.loads(mp.read_text())
        src, to_raw = m["src"], (lambda c: m["t"][min(len(m["t"]) - 1, max(0, int(round(c * m["fps"]))))])
    elif fp.exists():                                   # the raw recording itself
        src, to_raw = str(video), (lambda c: c)
    else:
        raise SystemExit(f"{sid}: \"cursor\" needs the recorder's timing file ({fp.name}) next to {video.name}")
    n = int(round(dur * FPS))
    Path(str(base) + ".map.json").write_text(json.dumps(
        {"src": src, "fps": FPS, "t": [round(to_raw(start + foot(j / FPS)), 4) for j in range(n)]}))
    log = root / cfg["log"] if cfg.get("log") else Path(src).with_suffix(".pointer.json")
    if not log.exists():
        raise SystemExit(f"{sid}: pointer log not found: {log} (pw_record.py take writes it next to the raw clip)")
    words = load_words(seg, root, audio, sid)
    cmd = [sys.executable, str(Path(__file__).resolve().parent / "cursor_overlay.py"), str(base), "--log", str(log),
           "--out", str(build / f"{idx:02d}_{sid}_cursor.mp4"), "--out-size", str(W), str(H),
           "--size", str(cfg.get("size", 1.5)), "--ring", cfg.get("ring", a.ring), "--crf", "28" if a.preview else "15"]
    for key, keys in (("gestures", ("at", "_end")), ("zooms", ("from", "to"))):
        items = cfg.get(key) or []
        if isinstance(items, str):
            items = json.loads((root / items).read_text())
        if items:
            items = resolve_times(items, words, sid, keys)
            for it in items:
                if key == "gestures" and "dur" not in it:
                    it["dur"] = it.pop("_end", it["at"] + 1.0) - it["at"]
                it.pop("_end", None)
            f = build / f"{idx:02d}_{sid}_{key}.json"
            f.write_text(json.dumps(items))
            cmd += [f"--{key}", str(f)]
    run(cmd, a.verbose)
    return build / f"{idx:02d}_{sid}_cursor.mp4"


def build_segment(seg, idx, root, build, a, wipe_out_next):
    sid = seg.get("id", f"seg{idx:02d}")
    t = seg["type"]
    P = lambda k: (root / seg[k]) if seg.get(k) else None  # noqa: E731
    video, pip, audio, image = P("video"), P("pip"), P("audio"), P("image")
    # --- duration
    dur = seg.get("duration")
    if not dur:
        for cand in (audio, pip, video):
            if cand and cand.exists():
                dur = ffprobe_duration(cand)
                if dur:
                    break
    if t == "slides" and not dur:
        dur = sum(s.get("duration", 5) for s in seg["slides"])
    if not dur:
        raise SystemExit(f"{sid}: cannot determine duration (give audio, pip, video or duration)")
    dur = float(dur)

    pairs = None
    if t == "screen" and seg.get("sync") and audio and a.pace_for(seg):
        start0 = float(seg.get("start", 0))
        vdur0 = (float(seg["end"]) - start0) if seg.get("end") is not None else (ffprobe_duration(video) or dur) - start0
        paced = pace_screen(seg, root, audio, sid, vdur0, a.pace_for(seg))
        if paced:
            pairs, dur = paced

    inputs, filters = [], []
    def add_input(args):
        inputs.extend(args)
        return sum(1 for x in inputs if x == "-i") - 1

    # --- base layer
    if t in ("full", "screen"):
        start = float(seg.get("start", 0))
        end = seg.get("end")
        if end is not None:
            vi = add_input(["-ss", str(start), "-t", f"{float(end) - start:.3f}", "-i", video])
            vdur = float(end) - start
        else:
            vi = add_input(["-ss", str(start), "-i", video])
            vdur = (ffprobe_duration(video) or dur) - start
        fit = seg.get("fit", "auto" if t == "screen" else "pad")
        cursor = seg.get("cursor") if t == "screen" else None
        chain = f"[{vi}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1,fps={FPS}"
        if cursor:  # keep the footage's own resolution: cursor_overlay.py zooms from it, then scales to the output
            chain = f"[{vi}:v]setsar=1,fps={FPS}"
        if t == "full":
            chain = f"[{vi}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"
        foot = lambda o: min(o, vdur)  # noqa: E731  output time → footage time (mirrors the retime below)
        if seg.get("sync") and t == "screen":
            pace = a.pace_for(seg)
            if pairs is None:
                pairs = resolve_sync(seg, root, audio, sid)
            max_speed = float(seg.get("max_speed", pace["max_speed"] if pace else 6.0))
            filters.append(chain + "[synin]")
            filters.extend(sync_chain("synin", pairs, vdur, dur, max_speed))
            foot = lambda o: sync_footage_time(o, pairs, vdur, dur, max_speed)  # noqa: E731
            chain = None
        elif fit == "speed" and vdur > 0:
            chain += f",setpts=PTS*{dur / vdur:.6f}"
            foot = lambda o: o * vdur / dur  # noqa: E731
        elif fit == "auto" and vdur > 0:
            # slow down (≤ max_slow) or speed up (≤ max_fast) toward the narration length, then hold the last frame
            factor = dur / vdur
            factor = min(factor, float(seg.get("max_slow", 1.6))) if factor >= 1 else max(factor, 1 / float(seg.get("max_fast", 1.6)))
            chain += f",setpts=PTS*{factor:.6f}"
            if vdur * factor < dur:
                chain += f",tpad=stop_mode=clone:stop_duration={dur - vdur * factor + 0.5:.3f}"
            foot = lambda o: min(o / factor, vdur)  # noqa: E731
        else:
            if vdur < dur:
                chain += f",tpad=stop_mode=clone:stop_duration={dur - vdur + 0.5:.3f}"
        if chain is not None:  # (with sync, sync_chain already produced [base])
            chain += f",trim=duration={dur:.3f},setpts=PTS-STARTPTS,format=yuv420p"
            if t == "full" and seg.get("key"):
                chain = chain.replace("format=yuv420p", "format=yuva420p") + ",colorkey=0x00FF00:0.30:0.10"
                bg = P("bg")
                if bg:
                    bi = add_input(["-loop", "1", "-t", f"{dur:.3f}", "-i", bg])
                else:   # no background image given: plain dark backdrop
                    bi = add_input(["-f", "lavfi", "-t", f"{dur:.3f}", "-i", f"color=c=0x1f2430:s={W}x{H}:r={FPS}"])
                filters.append(cover(f"{bi}:v", "bgk"))
                filters.append(chain + "[fg]")
                filters.append("[bgk][fg]overlay=0:0:shortest=1,format=yuv420p[base]")
            else:
                filters.append(chain + "[base]")
        if cursor:
            cur_mp4 = render_cursor(seg, sid, idx, root, build, a, video, start, dur, foot, audio, inputs, filters)
            inputs, filters = [], []
            vi = add_input(["-i", cur_mp4])
            filters.append(f"[{vi}:v]setsar=1,fps={FPS},trim=duration={dur:.3f},setpts=PTS-STARTPTS,format=yuv420p[base]")
    elif t == "slides":
        labels, t0, pos = [], 0.0, 0
        words = load_words(seg, root, audio, sid) if any(s.get("until_say") for s in seg["slides"]) else None
        for k, s in enumerate(seg["slides"]):
            end = s.get("until")
            if s.get("until_say"):                   # change slide just before this phrase (survives a re-voice)
                if words is None:
                    raise SystemExit(f"{sid}: until_say needs the narration's words.json")
                hit = find_phrase(words, s["until_say"], pos, sid)
                pos = hit + 1
                end = words[hit]["start"] - float(s.get("lead", 0.15))
            d = (end - t0) if end else s.get("duration")
            if k == len(seg["slides"]) - 1:
                d = max(0.1, dur - t0)
            d = float(d)
            si = add_input(["-loop", "1", "-framerate", str(FPS), "-t", f"{d:.3f}", "-i", root / s["image"]])
            filters.append(cover(f"{si}:v", f"s{k}"))
            labels.append(f"[s{k}]")
            t0 += d
        filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0,trim=duration={dur:.3f},setpts=PTS-STARTPTS[base]")
    elif t == "image":
        ii = add_input(["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", image])
        filters.append(cover(f"{ii}:v", "base"))
    else:
        raise SystemExit(f"{sid}: unknown type {t}")

    cur = "base"
    # --- PiP
    pip_i = None
    if pip and t != "full":
        preset = PIP[seg.get("pip_style") or a.pip_style]
        pw, ph, m, r = preset["w"], preset["h"], preset["margin"], preset["radius"]
        pip_i = add_input(["-i", pip])
        aspect = pw / ph
        pchain = (f"[{pip_i}:v]crop='min(iw,ih*{aspect:.4f})':'min(ih,iw/{aspect:.4f})',scale={pw}:{ph},setsar=1,fps={FPS},"
                  f"tpad=stop_mode=clone:stop_duration=2,trim=duration={dur:.3f},setpts=PTS-STARTPTS")
        if seg.get("key"):
            pchain += ",format=yuva420p,colorkey=0x00FF00:0.30:0.10"
        if r:
            mask = rounded_mask(build / f"mask_{pw}x{ph}_{r}.png", pw, ph, r)
            if mask:
                mi = add_input(["-loop", "1", "-i", mask])
                filters.append(pchain + ",format=yuva420p[pv0]")
                filters.append(f"[{mi}:v]format=gray,scale={pw}:{ph}[pm]")
                filters.append("[pv0][pm]alphamerge[pv]")
            else:
                filters.append(pchain + "[pv]")
        else:
            filters.append(pchain + "[pv]")
        filters.append(f"[{cur}][pv]overlay=W-w-{m}:H-h-{m}:eof_action=repeat[withpip]")
        cur = "withpip"

    # --- logo wipes
    if seg.get("wipe_in"):
        if not WIPE["in"]:
            raise SystemExit(f"{sid}: \"wipe_in\" needs \"transition\": {{\"in\": …, \"out\": …}} in the EDL")
        wi = add_input(["-i", WIPE["in"]])
        filters.append(f"[{wi}:v]setpts=PTS-STARTPTS,format=yuva420p[wi]")
        filters.append(f"[{cur}][wi]overlay=0:0:eof_action=pass[wpi]")
        cur = "wpi"
    if wipe_out_next:
        wo = add_input(["-i", WIPE["out"]])
        off = max(0.0, dur - WIPE_OUT_D)
        filters.append(f"[{wo}:v]setpts=PTS-STARTPTS+{off:.3f}/TB,format=yuva420p[wo]")
        filters.append(f"[{cur}][wo]overlay=0:0:eof_action=pass[wpo]")
        cur = "wpo"
    filters.append(f"[{cur}]format=yuv420p[vout]")

    # --- audio
    asrc = None
    if audio:
        asrc = add_input(["-i", audio])
    elif pip and pip_i is not None and has_audio(pip):
        asrc = pip_i
    elif video and t in ("full", "screen") and has_audio(video) and seg.get("use_video_audio", t == "full"):
        asrc = 0
    if asrc is None:
        asrc = add_input(["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"])
    filters.append(f"[{asrc}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                   f"apad,atrim=duration={dur:.3f},asetpts=PTS-STARTPTS[aout]")

    out = build / f"{idx:02d}_{sid}.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters),
           "-map", "[vout]", "-map", "[aout]", "-t", f"{dur:.3f}", *enc_args(a.preview), out]
    print(f"  [{idx:02d}] {sid:<16} {t:<7} {dur:6.1f}s" + (" +pip" if pip_i is not None else "")
          + (" +wipe_in" if seg.get("wipe_in") else "") + (" +wipe_out" if wipe_out_next else ""), flush=True)
    run(cmd, a.verbose)
    return out, dur


def normalize_clip(src, out, a):
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf",
         f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},format=yuv420p",
         "-af", "aresample=48000,aformat=channel_layouts=stereo", *enc_args(a.preview), out], a.verbose)
    return out


def main():
    global W, H
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edl")
    ap.add_argument("--preview", action="store_true", help="540p ultrafast draft")
    ap.add_argument("--only", nargs="*", help="rebuild only these segment ids (others reused from .build)")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found (brew install ffmpeg)")
    edl_path = Path(a.edl).resolve()
    root = edl_path.parent
    edl = json.loads(edl_path.read_text())
    a.pip_style = edl.get("pip_style", "tutorial")
    a.ring = edl.get("cursor_ring", "#3B82F6")
    tr = edl.get("transition") or {}
    WIPE.update({k: root / tr[k] for k in ("in", "out") if tr.get(k)})
    a.pace_for = lambda seg: pace_settings(edl, seg)
    if a.preview:
        W, H = 960, 540
        for p in PIP.values():
            p.update(w=p["w"] // 2, h=p["h"] // 2, margin=p["margin"] // 2, radius=p["radius"] // 2)
    build = root / ".build" / ("preview" if a.preview else "full")
    build.mkdir(parents=True, exist_ok=True)
    parts, total = [], 0.0
    intro = edl.get("intro") or (edl.get("bumper") if isinstance(edl.get("bumper"), str) else None)
    if intro:
        bp = build / "00_intro.mp4"
        parts.append(bp if (bp.exists() and a.only) else normalize_clip(root / intro, bp, a))
        total += ffprobe_duration(parts[-1]) or 0
    segs = edl["segments"]
    print(f"Assembling {len(segs)} segments → {edl['output']}")
    for i, seg in enumerate(segs, 1):
        nxt = segs[i] if i < len(segs) else None
        wipe_out_next = bool(nxt and nxt.get("wipe_in"))
        sid = seg.get("id", f"seg{i:02d}")
        cached = build / f"{i:02d}_{sid}.mp4"
        if a.only and sid not in a.only and cached.exists():
            parts.append(cached)
            total += ffprobe_duration(cached) or 0
            continue
        p, d = build_segment(seg, i, root, build, a, wipe_out_next)
        parts.append(p)
        total += d
    if edl.get("outro"):
        op = build / "99_outro.mp4"
        parts.append(op if (op.exists() and a.only) else normalize_clip(root / edl["outro"], op, a))
        total += ffprobe_duration(parts[-1]) or 0
    lst = build / "concat.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    out = root / edl["output"]
    if a.preview:
        out = out.with_name(out.stem + "_preview" + out.suffix)
    out.parent.mkdir(parents=True, exist_ok=True)
    joined = build / "joined.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined], a.verbose)
    if edl.get("loudnorm", True) and not a.preview:
        # two-pass loudnorm → accurate −16 LUFS integrated; TP −2.5 leaves room for AAC overshoot (lands ≈ −1.5 to −2)
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(joined), "-af",
                            "loudnorm=I=-16:TP=-2.5:LRA=11:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True)
        js = r.stderr[r.stderr.rfind("{"): r.stderr.rfind("}") + 1]
        try:
            m = json.loads(js)
            af = ("loudnorm=I=-16:TP=-2.5:LRA=11:linear=true:"
                  f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
                  f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}")
        except (ValueError, KeyError):
            af = "loudnorm=I=-16:TP=-2.5:LRA=11"
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", joined, "-c:v", "copy", "-af", af,
             "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], a.verbose)
    else:
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", joined, "-c", "copy", "-movflags", "+faststart", out], a.verbose)
    print(f"✔ {out}  ({(ffprobe_duration(out) or total) / 60:.1f} min)")


if __name__ == "__main__":
    main()
