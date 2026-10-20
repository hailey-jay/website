"""Structural check of the built page.

The complement to the source-side checks the build already runs: this parses
the built pages as they were actually written and looks for what only shows up in the
finished artifact - a local href or src pointing at nothing, a duplicate id, an
<img> missing its alt, dimensions, or loading hint, and the total weight of
image a single page pulls.

It reads the committed HTML, which is what Cloudflare serves.
`make verify` is the separate question of whether that file is still current.

It also compares the editor copy in sagitta/app/ (its VERSION) with the newest
release tag upstream, and fails if the copy is behind; `make app` catches it
up. That one step needs the network; offline, it says so and does not fail.

    python scripts/check.py            structure and Sagitta version
    python scripts/check.py --links    the off-site URLs instead (network, slow)
"""
import os
import re
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from sitekit import check
from scripts.app import DEST, UPSTREAM

# The built pages, and only those: sagitta/app/ is the editor itself, copied
# in from its own repo by `make app`, and is not this build's to audit.
PAGES = ["index.html", "sagitta/index.html", "sagitta/tutorial/index.html"]


def semver(text):
    """(major, minor, patch) from "0.6.0" or "v0.6.0", or None."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text.strip())
    return tuple(map(int, m.groups())) if m else None


def sagitta_behind():
    """Compare the served editor with upstream's newest release tag.

    Returns an exit code: 1 if the copy is behind, else 0.
    """
    served = semver((DEST / "VERSION").read_text(encoding="utf-8"))
    try:
        result = subprocess.run(["git", "ls-remote", "--tags", "--refs", UPSTREAM],
                                capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        result = None
    if result is None or result.returncode:
        print(f"\nSagitta: could not reach {UPSTREAM}; version not compared")
        return 0
    tags = [semver(line.rsplit("refs/tags/", 1)[-1]) for line in result.stdout.splitlines()]
    latest = max((t for t in tags if t), default=None)
    show = lambda v: ".".join(map(str, v)) if v else "unknown"
    if served is None or (latest and served < latest):
        print(f"\nSagitta: serving {show(served)}, upstream is at {show(latest)}; run `make app`")
        return 1
    print(f"\nSagitta: serving {show(served)}, upstream is at {show(latest)}")
    return 0


if __name__ == "__main__":
    os.chdir(root)          # so problems are reported as repo-relative paths
    if "--links" in sys.argv:
        raise SystemExit(check.run(PAGES, links=True))
    status = check.run(PAGES)
    raise SystemExit(sagitta_behind() or status)
