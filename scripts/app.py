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

The version comes along as `VERSION`, read out of the clone's
package.json (which is the desktop build's and does not travel itself), so the
landing page states the version of the editor it actually serves.

The copy is tracked in this repo, because the repo is what gets served. It is
pruned as well as written: a file that has left the source leaves the copy, or
it would be served forever after it stopped existing.

    python scripts/app.py [REPO [REF]]

The source is always a fresh clone of REF (default: main) from REPO (default:
the public GitHub repo), made into a temporary directory and thrown away
afterwards. Copying out of a working checkout served whatever branch it
happened to be on, test branches included. REPO may be a local path; it is
still cloned, so only committed work on REF travels.

Written in Python rather than as an rsync line in the Makefile so it runs on a
machine that has no rsync, which is most Windows ones and some minimal Linux
images.
"""
import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent

DEST = root / "sagitta/app"

# Where the editor comes from. scripts/check.py reads UPSTREAM too, to tell
# whether the copy here is behind the latest release.
UPSTREAM = "https://github.com/hailey-jay/sagitta.git"
REF = "main"

# Everything index.html pulls in, plus the licences that have to travel with a
# GPL program. Hand-listed, like every other manifest in this build: a glob
# would quietly start shipping whatever lands in the source next.
FILES = ["index.html", "main.css", "katex.css", "icon.svg", "icon.png",
         "manifest.webmanifest", "service-worker.js", "LICENSE", "NOTICE"]
DIRS  = ["src", "web", "fonts", "icons"]

# Written into the copy rather than copied, from package.json's "version".
VERSION = Path("VERSION")

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


def clone(repo, ref, into):
    """Shallow-clone `ref` of `repo` into `into`; return the commit, or None."""
    local = Path(repo).expanduser()
    if local.is_dir():
        # A plain path ignores --depth; a file:// URL honours it.
        repo = local.resolve().as_uri()
    result = subprocess.run(
        ["git", "clone", "--quiet", "--depth", "1", "--branch", ref, repo, str(into)],
        capture_output=True, text=True)
    if result.returncode:
        print(result.stderr.strip() or f"git clone of {repo} failed")
        return None
    return subprocess.run(["git", "-C", str(into), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def main(argv):
    repo = argv[1] if len(argv) > 1 and argv[1] else UPSTREAM
    ref = argv[2] if len(argv) > 2 and argv[2] else REF
    with tempfile.TemporaryDirectory(prefix="sagitta-") as tmp:
        src = Path(tmp) / "sagitta"
        commit = clone(repo, ref, src)
        if commit is None:
            return 1
        print(f"cloned {repo} at {ref} ({commit})")
        return copy(src)


def copy(src):
    if not (src / "index.html").is_file():
        print(f"no Sagitta editor in {src}")
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

    version = json.loads((src / "package.json").read_text(encoding="utf-8"))["version"]
    wanted.add(VERSION)
    target = DEST / VERSION
    if not (target.is_file() and target.read_text(encoding="utf-8") == version + "\n"):
        target.write_text(version + "\n", encoding="utf-8")
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
