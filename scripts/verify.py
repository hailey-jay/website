"""Rebuild, and fail if the committed output is not what the sources produce.

`index.html`, `rss.xml`, and `sitemap.xml` are committed and served directly, so
stale output ships silently with no error anywhere. The build is deterministic
(the feed's lastBuildDate comes from the newest post's date, not the clock), so
a rebuild that leaves these three unchanged means the committed output is
current. The worktree is left exactly as it was found.

`images/thumbs/` is deliberately not checked: it regenerates on mtime, and a
fresh checkout's mtimes are checkout time.
"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from sitekit.verify import verify

OUTPUTS = ["index.html", "rss.xml", "sitemap.xml"]

if __name__ == "__main__":
    raise SystemExit(verify(OUTPUTS, [sys.executable, "src/make.py"], cwd=root))
