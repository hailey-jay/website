"""Rebuild and ask whether the committed output is still current.

These sites deploy by having the repo sit on the server, so the built files are
tracked and stale output ships silently with no error anywhere. The check that
catches it is "rebuild, then diff" - but the build writes over the tracked
files in place, so running it dirties the tree and needs a git checkout to
undo. This does that safely and leaves the worktree exactly as it found it.

The check is only worth anything if the build is deterministic. A build that
stamps datetime.now() into its output reports a spurious diff every month and
every New Year, and a check that cries wolf is a check nobody runs. Use
`build_date()` for anything date-shaped so it can be pinned.
"""
import os
import subprocess
from datetime import date

from .errors import BuildError


def build_date():
    """Today, or the date in $SITE_BUILD_DATE.

    Pin it in CI and in `make verify` so the output is reproducible; leave it
    unset for an ordinary build."""
    stamp = os.environ.get("SITE_BUILD_DATE")
    if not stamp:
        return date.today()
    try:
        return date.fromisoformat(stamp)
    except ValueError:
        raise BuildError(
            f"SITE_BUILD_DATE is not an ISO date: {stamp!r}")


def _git(*args, cwd=None):
    return subprocess.run(("git",) + args, cwd=cwd, capture_output=True,
                          text=True)


def verify(outputs, build, cwd=None, verbose=True):
    """Rebuild and report whether `outputs` changed. Returns an exit code.

    `build` is a callable, or an argv list run as a subprocess. Refuses to run
    on a tree that already has uncommitted changes to the outputs, because it
    cannot tell those apart from what the rebuild produced and would throw them
    away restoring."""
    outputs = list(outputs)

    if _git("diff", "--quiet", "--", *outputs, cwd=cwd).returncode:
        print("worktree already has uncommitted changes to the build outputs;")
        print("commit or stash them before verifying.")
        return 2

    if callable(build):
        build()
    else:
        r = subprocess.run(build, cwd=cwd)
        if r.returncode:
            return r.returncode

    if not _git("diff", "--quiet", "--", *outputs, cwd=cwd).returncode:
        if verbose:
            print("build output matches what is committed")
        return 0

    print("a rebuild changes the committed output:")
    print(_git("diff", "--stat", "--", *outputs, cwd=cwd).stdout, end="")
    _git("checkout", "--", *outputs, cwd=cwd)
    return 1


__all__ = ["verify", "build_date"]
