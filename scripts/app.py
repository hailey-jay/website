"""Copy the Sagitta editor into sagitta/app/, so this site serves it.

Sagitta is a static page in its own repo: one index.html, a stylesheet, and a
directory of plain <script> files, all referenced by relative paths. There is
no bundler and no build step, so hosting it is a file copy - of exactly the
files the browser asks for, and none of the desktop shell's own half
(electron/), the suites (tests/), or the packaging output (dist/,
node_modules/).

What the web build needs beyond the editor itself: `web/host.js`, which stands
in for the desktop shell in a browser, the manifest that lets it install as an
app, and the service worker that keeps it working offline. Both the manifest
and the worker use relative paths, so they are correct under /sagitta/app/ as
they are at a site root.

The icon travels too, to `images/sagitta.svg`, which is what the site's own
pages use for Sagitta: the landing page's favicon and wordmark, and the
sidebar entry. One copy, kept in step with the app rather than drawn again.

The copy is tracked in this repo, because the repo is what gets served. It is
pruned as well as written: a file that has left the source leaves the copy, or
it would be served forever after it stopped existing.

    python scripts/app.py [SAGITTA_CHECKOUT]     (default: ../sagitta)

Written in Python rather than as an rsync line in the Makefile so it runs on a
machine that has no rsync, which is most Windows ones and some minimal Linux
images.
"""
import filecmp
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent

DEST = root / "sagitta/app"

# Everything index.html pulls in, plus the licences that have to travel with a
# GPL program. Hand-listed, like every other manifest in this build: a glob
# would quietly start shipping whatever lands in the source next.
FILES = ["index.html", "main.css", "katex.css", "icon.svg", "icon.png",
         "manifest.webmanifest", "service-worker.js", "LICENSE", "NOTICE"]
DIRS  = ["src", "web", "fonts", "icons"]

# Files copied out of the editor's copy and into the site proper, as
# `source: destination` relative to the repo root.
SHARED = {"icon.svg": "images/sagitta.svg"}


def sources(src):
    """Every (source file, path relative to the copy) pair, in sorted order."""
    for name in FILES:
        yield src / name, Path(name)
    for name in DIRS:
        for path in sorted((src / name).rglob("*")):
            if path.is_file():
                yield path, path.relative_to(src)


def main(argv):
    src = Path(argv[1]).expanduser().resolve() if len(argv) > 1 else root.parent / "sagitta"
    if not (src / "index.html").is_file():
        print(f"no Sagitta checkout at {src}; pass the path as an argument")
        return 1

    wanted, copied = set(), 0
    for source, rel in sources(src):
        if not source.is_file():
            print(f"missing from {src}: {rel}")
            return 1
        wanted.add(rel)
        target = DEST / rel
        # Unchanged files are left alone, so a no-op sync does not restamp
        # every file in the copy.
        if target.is_file() and filecmp.cmp(source, target, shallow=False):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1

    removed = 0
    for path in sorted(DEST.rglob("*"), reverse=True):
        if path.is_file() and path.relative_to(DEST) not in wanted:
            path.unlink()
            removed += 1
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()

    for name, destination in SHARED.items():
        target = root / destination
        if not (target.is_file() and filecmp.cmp(src / name, target, shallow=False)):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / name, target)
            print(f"{destination}: copied from {name}")

    total = sum(p.stat().st_size for p in DEST.rglob("*") if p.is_file())
    print(f"{DEST.relative_to(root)}: {len(wanted)} files, "
          f"{total / 1e6:.1f} MB ({copied} written, {removed} pruned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
