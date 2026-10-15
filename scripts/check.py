"""Structural check of the built page.

The complement to the source-side checks the build already runs: this parses
the built pages as they were actually written and looks for what only shows up in the
finished artifact - a local href or src pointing at nothing, a duplicate id, an
<img> missing its alt, dimensions, or loading hint, and the total weight of
image a single page pulls.

It reads the committed HTML, which is what Cloudflare serves.
`make verify` is the separate question of whether that file is still current.

    python scripts/check.py            structure only
    python scripts/check.py --links    the off-site URLs instead (network, slow)
"""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from sitekit import check

# The built pages, and only those: sagitta/app/ is the editor itself, rsynced
# in from its own repo by `make app`, and is not this build's to audit.
PAGES = ["index.html", "sagitta/index.html", "sagitta/tutorial/index.html"]

if __name__ == "__main__":
    os.chdir(root)          # so problems are reported as repo-relative paths
    raise SystemExit(check.run(PAGES, links="--links" in sys.argv))
