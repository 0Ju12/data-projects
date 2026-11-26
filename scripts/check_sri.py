"""Check that every CDN <script> in the published pages pins an SRI hash.

python scripts/check_sri.py           # offline: every CDN script has integrity + crossorigin
python scripts/check_sri.py --fetch   # also download each file and compare its sha384
"""

import base64
import hashlib
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAG = re.compile(r'<script\b[^>]*\bsrc="(https://[^"]+)"[^>]*>')
INTEGRITY = re.compile(r'\bintegrity="(sha384-[A-Za-z0-9+/=]+)"')


def sources():
    for path in sorted(ROOT.glob("*/**/*")):
        if path.suffix in (".html", ".py") and "node_modules" not in path.parts and path.is_file():
            yield path


def main(fetch):
    problems, pinned = [], {}
    for path in sources():
        for tag in TAG.finditer(path.read_text(encoding="utf-8")):
            url, where = tag.group(1), f"{path.relative_to(ROOT)}: {tag.group(1)}"
            found = INTEGRITY.search(tag.group(0))
            if not found or 'crossorigin="anonymous"' not in tag.group(0):
                problems.append(f"missing integrity/crossorigin  {where}")
            elif pinned.setdefault(url, found.group(1)) != found.group(1):
                problems.append(f"conflicting hashes             {where}")
    if fetch:
        for url, expected in pinned.items():
            request = urllib.request.Request(url, headers={"User-Agent": "sri-check"})
            with urllib.request.urlopen(request, timeout=60) as response:
                actual = "sha384-" + base64.b64encode(hashlib.sha384(response.read()).digest()).decode()
            if actual != expected:
                problems.append(f"hash mismatch {url}\n  pinned {expected}\n  served {actual}")
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"{len(pinned)} CDN scripts pinned, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main("--fetch" in sys.argv))
