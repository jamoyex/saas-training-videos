#!/usr/bin/env python3
"""Narration for training videos, from any voice: one audio file + one word-timing JSON per script segment.

Providers (--provider, or $TTS_PROVIDER):
  elevenlabs  any ElevenLabs voice: your own clones, voices you added, or the shared library. Word timings come back from
              the API. Audio tags like [inhales] [pause] [warmly] work on eleven_v3 / eleven_v4. Env: ELEVENLABS_API_KEY.
  openai      OpenAI TTS (gpt-4o-mini-tts, tts-1-hd …), fixed voice list, "--instructions" for tone. Env: OPENAI_API_KEY.
  say         macOS `say` (offline, free): good for drafts and timing passes, not for publishing.
  (human)     narration a person recorded: put vo/<SEG>.wav|mp3|m4a in place and run `align`.
Providers without word timings (openai, say, human) are aligned locally: whisper.cpp ($WHISPER_MODEL, a ggml model),
else faster-whisper (pip), else the OpenAI transcription API. Recognised words are mapped back onto the SCRIPT's words,
so EDL phrases ("say": "click Save") always match the script text.

Commands
  voices    [--provider P] [--library --search "warm narrator" --gender female --accent american --use-case narration]
  audition  --provider P --voices ID1 ID2 … [--text "…" | --script script.md --seg S02] [--stability 0.35 0.5] --out auditions/
            → one file per voice × setting, same words, to pick a voice by ear (play them back to back)
  speak     script.md --provider P --voice ID --out vo [--only S03 S04] [--dry-run]
  align     script.md --out vo [--only S03]          # word timings for existing audio (human recordings, other tools)
  say       "one line" --provider P --voice ID --out test.mp3

Output: vo/<SEG>.mp3 (or .wav), vo/<SEG>.words.json ([{word, start, end}]), vo/manifest.json (voice, model, settings,
duration, wpm per segment). Pronunciations: a pronunciations.json next to the script ({"Acme": "Ack-mee"}) respells words
for the voice and maps them back in the timings.
"""
import argparse
import base64
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ffprobe_duration, http, load_env, need_env, parse_script  # noqa: E402

WPM_EST = 165
EL_API = os.environ.get("ELEVENLABS_API_BASE", "https://api.elevenlabs.io")
OA_API = os.environ.get("OPENAI_API_BASE", "https://api.openai.com")
OPENAI_VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse"]
TAG_RE = re.compile(r"\s*\[[a-zA-Z][a-zA-Z ,'-]{0,40}\]")


# ---------------------------------------------------------------- text helpers
def load_pron(script=None):
    f = Path(script).resolve().parent / "pronunciations.json" if script else None
    return {k: v for k, v in json.loads(f.read_text()).items() if not k.startswith("_")} if f and f.exists() else {}


def respell(text, pron):
    for word, alias in pron.items():
        text = re.sub(rf"(?<![\w-]){re.escape(word)}(?![\w-])", alias, text) if text else text
    return text


def norm(t):
    return re.sub(r"[^0-9a-z]", "", t.lower())


def unrespell(words, pron):
    """Merge alias tokens back into the real word (keeping trailing punctuation)."""
    for word, alias in pron.items():
        parts = [norm(x) for x in alias.split()]
        i = 0
        while i <= len(words) - len(parts):
            if [norm(w["word"]) for w in words[i:i + len(parts)]] == parts:
                tail = re.search(r"[^\w]*$", words[i + len(parts) - 1]["word"]).group(0)
                words[i:i + len(parts)] = [{"word": word + tail, "start": words[i]["start"],
                                            "end": words[i + len(parts) - 1]["end"]}]
            i += 1
    return words


def strip_tag_tokens(words):
    """Drop audio-tag tokens ([inhales], [short pause] … possibly split over several tokens) from timings."""
    out, inside = [], False
    for w in words:
        tok = w["word"]
        if inside or tok.startswith("["):
            inside = not tok.rstrip(".,!?;:").endswith("]")
            continue
        out.append(w)
    return out


def chars_to_words(alignment):
    chars = alignment.get("characters", [])
    st = alignment.get("character_start_times_seconds", [])
    en = alignment.get("character_end_times_seconds", [])
    words, cur, cs, ce = [], "", None, None
    for ch, s, e in zip(chars, st, en):
        if ch.isspace():
            if cur:
                words.append({"word": cur, "start": round(cs, 3), "end": round(ce, 3)})
            cur, cs, ce = "", None, None
        else:
            if not cur:
                cs = s
            cur += ch
            ce = e
    if cur:
        words.append({"word": cur, "start": round(cs, 3), "end": round(ce, 3)})
    return words


# ---------------------------------------------------------------- alignment (providers without timings, human audio)
def _wav16(src):
    tmp = Path(tempfile.mkdtemp()) / "a.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(tmp)], check=True)
    return tmp


def asr_words(audio):
    """[(word, start, end)] recognised in the audio, by the first available engine."""
    model = os.environ.get("WHISPER_MODEL")
    exe = shutil.which("whisper-cli") or shutil.which("whisper-cpp")
    if exe and model and Path(model).exists():
        wav = _wav16(audio)
        base = wav.with_suffix("")
        subprocess.run([exe, "-m", model, "-f", str(wav), "-ml", "1", "-sow", "-oj", "-of", str(base), "-np"],
                       check=True, capture_output=True)
        js = json.loads(Path(str(base) + ".json").read_text())
        return [(seg["text"].strip(), seg["offsets"]["from"] / 1000, seg["offsets"]["to"] / 1000)
                for seg in js.get("transcription", []) if seg["text"].strip()]
    try:
        from faster_whisper import WhisperModel   # pip install faster-whisper
        m = WhisperModel(os.environ.get("FASTER_WHISPER_MODEL", "small.en"), compute_type="int8")
        segs, _ = m.transcribe(str(audio), word_timestamps=True)
        return [(w.word.strip(), w.start, w.end) for s in segs for w in s.words]
    except ImportError:
        pass
    if os.environ.get("OPENAI_API_KEY"):
        boundary = uuid.uuid4().hex
        data = Path(audio).read_bytes()
        parts = [("model", "whisper-1"), ("response_format", "verbose_json"), ("timestamp_granularities[]", "word")]
        body = b"".join(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode() for k, v in parts)
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{Path(audio).name}\"\r\n"
                 f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
        _, _, js = http("POST", f"{OA_API}/v1/audio/transcriptions",
                        {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                         "Content-Type": f"multipart/form-data; boundary={boundary}"}, body, timeout=600)
        return [(w["word"], w["start"], w["end"]) for w in js.get("words", [])]
    sys.exit("No aligner: set WHISPER_MODEL to a whisper.cpp ggml model (brew install whisper-cpp), "
             "or `pip install faster-whisper`, or set OPENAI_API_KEY.")


def align_to_script(script_text, audio):
    """Script words with times: recognised words are matched to the script in order; unmatched script words get times
    interpolated between their matched neighbours."""
    toks = TAG_RE.sub("", script_text).split()
    rec = asr_words(audio)
    a = [norm(t) for t in toks]
    b = [norm(w) for w, _, _ in rec]
    times = [None] * len(toks)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            _, s, e = rec[blk.b + k]
            times[blk.a + k] = (s, e)
    dur = ffprobe_duration(audio) or (rec[-1][2] if rec else 0)
    known = [i for i, t in enumerate(times) if t]
    for i in range(len(toks)):
        if times[i]:
            continue
        prev = max([j for j in known if j < i], default=None)
        nxt = min([j for j in known if j > i], default=None)
        t0 = times[prev][1] if prev is not None else 0.0
        t1 = times[nxt][0] if nxt is not None else dur
        n_gap = (nxt if nxt is not None else len(toks)) - (prev if prev is not None else -1) - 1
        k = i - (prev if prev is not None else -1)
        step = max(t1 - t0, 0.0) / (n_gap + 1)
        times[i] = (t0 + step * (k - 0.5), t0 + step * k)
    matched = len(known) / max(1, len(toks))
    if matched < 0.6:
        print(f"   ⚠ only {matched:.0%} of the script words were recognised: check the audio matches the script")
    return [{"word": w, "start": round(s, 3), "end": round(e, 3)} for w, (s, e) in zip(toks, times)]


# ---------------------------------------------------------------- providers
def el_headers():
    return {"xi-api-key": need_env("ELEVENLABS_API_KEY", "elevenlabs.io → Profile → API Keys."), "Accept": "application/json"}


def synth(provider, text, voice, a, prev_text=None, next_text=None):
    """→ (audio bytes, file suffix, words or None)"""
    pron = a.pron
    text = respell(text, pron)
    if provider == "elevenlabs":
        body = {"text": text, "model_id": a.model or os.environ.get("ELEVENLABS_MODEL", "eleven_v4"),
                "voice_settings": {"stability": a.stability, "similarity_boost": a.similarity, "style": a.style,
                                   "use_speaker_boost": True, "speed": a.speed}}
        if prev_text:
            body["previous_text"] = respell(prev_text, pron)[-1000:]
        if next_text:
            body["next_text"] = respell(next_text, pron)[:1000]
        _, _, data = http("POST", f"{EL_API}/v1/text-to-speech/{voice}/with-timestamps?output_format=mp3_44100_128",
                          el_headers(), body, timeout=300)
        words = chars_to_words(data.get("alignment") or data.get("normalized_alignment") or {})
        return base64.b64decode(data["audio_base64"]), ".mp3", strip_tag_tokens(unrespell(words, pron))
    plain = TAG_RE.sub("", text).strip()          # other engines would read tags aloud
    if provider == "openai":
        body = {"model": a.model or os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"), "voice": voice,
                "input": plain, "response_format": "mp3", "speed": a.speed}
        if a.instructions:
            body["instructions"] = a.instructions
        _, _, audio = http("POST", f"{OA_API}/v1/audio/speech",
                           {"Authorization": f"Bearer {need_env('OPENAI_API_KEY')}"}, body, timeout=300, raw=True)
        return audio, ".mp3", None
    if provider == "say":
        tmp = Path(tempfile.mkdtemp())
        rate = str(int(175 * a.speed))
        subprocess.run(["say", "-v", voice, "-r", rate, "-o", str(tmp / "a.aiff"), plain], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp / "a.aiff"), "-b:a", "128k", str(tmp / "a.mp3")], check=True)
        return (tmp / "a.mp3").read_bytes(), ".mp3", None
    sys.exit(f"unknown provider {provider}")


# ---------------------------------------------------------------- commands
def cmd_voices(a):
    if a.provider == "openai":
        print("\n".join(OPENAI_VOICES))
        return
    if a.provider == "say":
        print(subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout)
        return
    if a.library:
        q = {"page_size": 30, "search": a.search, "gender": a.gender, "accent": a.accent, "age": a.age,
             "use_cases": a.use_case, "language": a.language}
        qs = "&".join(f"{k}={v}" for k, v in q.items() if v)
        _, _, data = http("GET", f"{EL_API}/v1/shared-voices?{qs}", el_headers())
        for v in data.get("voices", []):
            print(f"{v['voice_id']}\t{v.get('gender', '')}\t{v.get('age', '')}\t{v.get('accent', '')}\t"
                  f"{v.get('use_case', '')}\t{v['name']}\t{(v.get('description') or '')[:60]}")
        print("(library voices: add one to your account in the ElevenLabs app, or use its id directly if your plan allows)")
        return
    _, _, data = http("GET", f"{EL_API}/v1/voices", el_headers())
    for v in data.get("voices", []):
        lab = v.get("labels") or {}
        print(f"{v['voice_id']}\t{v.get('category', '')}\t{v['name']}\t"
              f"{' '.join(str(x) for x in (lab.get('gender'), lab.get('accent'), lab.get('age'), lab.get('use_case')) if x)}")


def write_words(path, words):
    Path(path).write_text(json.dumps(words, indent=0))


def cmd_audition(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    text = a.text
    if a.script:
        segs = {s["id"]: s for s in parse_script(a.script)}
        text = segs[a.seg or next(iter(segs))]["text"]
    if not text:
        sys.exit("give --text or --script (+ --seg)")
    rows = []
    for v in a.voices:
        for st in a.stability_list or [a.stability]:
            a.stability = st
            audio, suf, _ = synth(a.provider, text, v, a)
            name = re.sub(r"[^\w.-]", "_", f"{a.provider}_{v}_stab{st}") + suf
            (out / name).write_bytes(audio)
            rows.append((name, ffprobe_duration(out / name)))
            print(f"  {name}  {rows[-1][1]:.1f}s")
    (out / "README.txt").write_text("Same words, different voices/settings. Listen back to back; pick by ear.\n\n" +
                                    "\n".join(f"{n}\t{d:.1f}s" for n, d in rows) + f"\n\nText:\n{text}\n")
    print(f"→ {out}/ (play them back to back; note the voice id you like)")


def cmd_speak(a):
    segs = parse_script(a.script)
    out = Path(a.out)
    total = sum(s["words"] for s in segs)
    print(f"{len(segs)} segments, {total} words, est. {total / WPM_EST:.1f} min at {WPM_EST} wpm")
    for s in segs:
        print(f"  {s['id']:<18} {s['type']:<8} {s['words']:>5} w  ~{s['words'] / WPM_EST * 60:5.0f}s  {s['visual'][:50]}")
    if a.dry_run:
        return
    out.mkdir(parents=True, exist_ok=True)
    voice = a.voice or os.environ.get("TTS_VOICE") or sys.exit("--voice (or $TTS_VOICE) is required: run `voices` / `audition`")
    man_path = out / "manifest.json"
    manifest = json.loads(man_path.read_text()) if man_path.exists() else {"segments": {}}
    for i, s in enumerate(segs):
        if (a.only and s["id"] not in a.only) or not s["text"]:
            continue
        prev_t = segs[i - 1]["text"] if i > 0 else None
        next_t = segs[i + 1]["text"] if i + 1 < len(segs) else None
        print(f"→ {s['id']} ({s['words']} words)…", flush=True)
        for attempt in range(4):                     # TTS APIs drop connections now and then
            try:
                audio, suf, words = synth(a.provider, s["text"], voice, a, prev_t, next_t)
                break
            except (SystemExit, OSError) as e:
                if attempt == 3:
                    raise
                print(f"   retry ({e})")
        f = out / f"{s['id']}{suf}"
        f.write_bytes(audio)
        if words is None:
            words = align_to_script(respell(s["text"], {}), f)
        write_words(out / f"{s['id']}.words.json", words)
        dur = ffprobe_duration(f) or (words[-1]["end"] if words else None)
        manifest["segments"][s["id"]] = {"type": s["type"], "visual": s["visual"], "audio": f.name,
                                         "words_file": f"{s['id']}.words.json", "duration": dur, "word_count": s["words"],
                                         "provider": a.provider, "voice": voice, "model": a.model, "speed": a.speed,
                                         "stability": a.stability if a.provider == "elevenlabs" else None,
                                         "wpm": round(s["words"] / dur * 60) if dur else None}
        print(f"   saved {f} ({dur:.1f}s, {s['words'] / dur * 60:.0f} wpm)" if dur else f"   saved {f}")
    manifest["script"] = str(Path(a.script).resolve())
    man_path.write_text(json.dumps(manifest, indent=2))
    print(f"manifest: {man_path}")


def cmd_align(a):
    out = Path(a.out)
    for s in parse_script(a.script):
        if a.only and s["id"] not in a.only:
            continue
        f = next((out / f"{s['id']}{x}" for x in (".wav", ".mp3", ".m4a", ".aiff") if (out / f"{s['id']}{x}").exists()), None)
        if not f:
            print(f"  {s['id']}: no audio in {out}/ (expected {s['id']}.wav|mp3|m4a)")
            continue
        words = align_to_script(s["text"], f)
        write_words(out / f"{s['id']}.words.json", words)
        print(f"  {s['id']}: {len(words)} words aligned ({ffprobe_duration(f):.1f}s)")


def cmd_say(a):
    voice = a.voice or os.environ.get("TTS_VOICE") or sys.exit("--voice is required")
    audio, suf, words = synth(a.provider, a.text, voice, a)
    Path(a.out).write_bytes(audio)
    if words is None:
        words = align_to_script(a.text, a.out)
    write_words(Path(a.out).with_suffix(".words.json"), words)
    print(a.out)


def main():
    load_env()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--provider", default=os.environ.get("TTS_PROVIDER", "elevenlabs"), choices=["elevenlabs", "openai", "say"])
        sp.add_argument("--model", default=None, help="elevenlabs: eleven_v4 (default) / eleven_v3 / eleven_multilingual_v2; "
                                                     "openai: gpt-4o-mini-tts (default) / tts-1-hd")
        sp.add_argument("--stability", type=float, default=float(os.environ.get("TTS_STABILITY", 0.4)),
                        help="elevenlabs: lower = more expressive (0.3–0.4 natural narration), higher = steadier")
        sp.add_argument("--similarity", type=float, default=float(os.environ.get("TTS_SIMILARITY", 0.8)))
        sp.add_argument("--style", type=float, default=float(os.environ.get("TTS_STYLE", 0.2)))
        sp.add_argument("--speed", type=float, default=float(os.environ.get("TTS_SPEED", 1.0)))
        sp.add_argument("--instructions", default=os.environ.get("TTS_INSTRUCTIONS"),
                        help="openai gpt-4o-mini-tts: tone, e.g. 'friendly, upbeat software trainer'")

    sp = sub.add_parser("voices")
    sp.add_argument("--provider", default=os.environ.get("TTS_PROVIDER", "elevenlabs"), choices=["elevenlabs", "openai", "say"])
    sp.add_argument("--library", action="store_true", help="elevenlabs: search the shared voice library")
    for k in ("search", "gender", "accent", "age", "use-case", "language"):
        sp.add_argument(f"--{k}")
    sp = sub.add_parser("audition")
    common(sp)
    sp.add_argument("--voices", nargs="+", required=True)
    sp.add_argument("--text")
    sp.add_argument("--script")
    sp.add_argument("--seg")
    sp.add_argument("--stability-list", type=float, nargs="*", help="try several stability values per voice")
    sp.add_argument("--out", default="auditions")
    sp = sub.add_parser("speak")
    common(sp)
    sp.add_argument("script")
    sp.add_argument("--voice")
    sp.add_argument("--out", default="vo")
    sp.add_argument("--only", nargs="*")
    sp.add_argument("--dry-run", action="store_true")
    sp = sub.add_parser("align")
    sp.add_argument("script")
    sp.add_argument("--out", default="vo")
    sp.add_argument("--only", nargs="*")
    sp = sub.add_parser("say")
    common(sp)
    sp.add_argument("text")
    sp.add_argument("--voice")
    sp.add_argument("--out", default="say.mp3")
    a = p.parse_args()
    a.pron = load_pron(getattr(a, "script", None))
    {"voices": cmd_voices, "audition": cmd_audition, "speak": cmd_speak, "align": cmd_align, "say": cmd_say}[a.cmd](a)


if __name__ == "__main__":
    main()
