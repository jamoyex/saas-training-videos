#!/usr/bin/env python3
"""Package the skill as a zip for skill uploads (ChatGPT workspace Skills, Claude.ai, other Agent Skills hosts).

  python3 scripts/package_skill.py            # → dist/saas-training-videos.zip

The zip's top folder is named after the skill (`name` in SKILL.md), as the Agent Skills format expects. It contains only
tracked source files (git ls-files): no media, logins, keys or build output.
"""
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    name = re.search(r"^name:\s*(\S+)", (ROOT / "SKILL.md").read_text(), re.M).group(1)
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    files = [f for f in files if not f.startswith(("docs/demo.gif", "dist/"))]
    out = ROOT / "dist" / f"{name}.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(ROOT / f, f"{name}/{f}")
    print(f"{out} ({len(files)} files, {out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
