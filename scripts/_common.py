"""Shared helpers for the training-video scripts (stdlib only)."""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "assets"


def _ssl_context():
    """python.org macOS builds often ship without CA certs → use certifi or the system bundle."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    for cafile in ("/etc/ssl/cert.pem", "/opt/homebrew/etc/openssl@3/cert.pem", "/usr/local/etc/openssl@3/cert.pem"):
        if Path(cafile).exists():
            return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


SSL_CTX = _ssl_context()


def load_env():
    """Load KEY=VALUE pairs from the nearest .env (cwd and up to 5 parents) plus ~/.training-video.env.
    Existing environment variables always win."""
    candidates = []
    p = Path.cwd()
    for _ in range(6):
        candidates.append(p / ".env")
        p = p.parent
    candidates.append(Path.home() / ".training-video.env")
    for c in candidates:
        if c.is_file():
            for line in c.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().removeprefix("export ").strip()
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)


def need_env(name, hint=""):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"Missing env var {name}. {hint}\nSet it in your shell or in a .env file (see templates/config.example.env).")
    return v


def http(method, url, headers=None, body=None, timeout=120, raw=False):
    """Tiny HTTP client. body may be dict (JSON), bytes, or None. Returns (status, headers, parsed|bytes)."""
    headers = dict(headers or {})
    data = None
    if isinstance(body, (dict, list)):
        data = json.dumps(body).encode()
        headers.setdefault("Content-Type", "application/json")
    elif isinstance(body, (bytes, bytearray)):
        data = bytes(body)
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
            content = r.read()
            status, rh = r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        content = e.read()
        msg = content.decode(errors="replace")[:2000]
        raise SystemExit(f"HTTP {e.code} {method} {url}\n{msg}")
    if raw:
        return status, rh, content
    try:
        return status, rh, json.loads(content.decode()) if content else None
    except json.JSONDecodeError:
        return status, rh, content


def ffprobe_duration(path):
    if not shutil.which("ffprobe"):
        return None
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return None


def has_audio(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                          "stream=index", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
    return bool(out)


SEG_RE = re.compile(r"^##\s*\[\s*([A-Za-z0-9_.-]+)\s*(?:\|\s*([^|\]]*))?(?:\|\s*([^\]]*))?\]\s*$")


def parse_script(path):
    """Parse a video script (templates/script_template.md).

    Segments start with a heading `## [SEG_ID | type | visual note]`.
    Inside a segment, lines starting with `>` (direction), `<!--` comments, and `[VISUAL...]`/`[ON SCREEN...]`
    notes are ignored for speech. Everything else is spoken text. Blank lines separate paragraphs.
    A script without markers is treated as a single segment `S01`.
    """
    text = Path(path).read_text()
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    segs, cur = [], None
    for line in text.splitlines():
        m = SEG_RE.match(line.strip())
        if m:
            cur = {"id": m.group(1), "type": (m.group(2) or "").strip().lower(),
                   "visual": (m.group(3) or "").strip(), "lines": []}
            segs.append(cur)
            continue
        if cur is None:
            continue  # title / metadata before first segment
        s = line.strip()
        if s.startswith(">") or re.match(r"^\[(VISUAL|ON SCREEN|SCREEN|SLIDE|B-ROLL|NOTE)[^\]]*\]", s, re.I) or s.startswith("#"):
            continue
        cur["lines"].append(line.rstrip())
    if not segs:
        body = "\n".join(l for l in text.splitlines() if not l.strip().startswith(("#", ">")))
        segs = [{"id": "S01", "type": "", "visual": "", "lines": body.splitlines()}]
    for s in segs:
        paras = re.split(r"\n\s*\n", "\n".join(s["lines"]).strip())
        s["paragraphs"] = [re.sub(r"\s+", " ", p).strip() for p in paras if p.strip()]
        s["text"] = "\n\n".join(s["paragraphs"])
        # strip light markdown emphasis for speech
        s["text"] = re.sub(r"[*_`]{1,3}([^*_`]+)[*_`]{1,3}", r"\1", s["text"])
        s["plain"] = re.sub(r"\s*\[[^\]]*\]", "", s["text"]).strip()   # without audio tags ([inhales], [pause] …)
        s["words"] = len(s["plain"].split())
        del s["lines"]
    return segs
