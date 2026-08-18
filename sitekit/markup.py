"""Checks that run on markup before it is written out.

Source-side validation. The complement is sitekit.check, which parses the
finished page; these two catch different things and neither subsumes the
other."""
import re

from .errors import BuildError, need

# ── Balance ──────────────────────────────────────────────────
# An unclosed tag is invisible in the built page (the parser closes it for you,
# usually in the wrong place) but corrupts an RSS body and swallows following
# prose into a link. Cheaper to catch here than to notice in a feed reader
# three weeks later.
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr"}
TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>")


def check_balance(markup, label):
    """Require every non-void element in `markup` to be closed, in order."""
    stack = []
    for closing, name, self_closing in TAG_RE.findall(markup):
        name = name.lower()
        if name in VOID or self_closing:
            continue
        if not closing:
            stack.append(name)
        else:
            need(stack, f"{label}: stray </{name}>")
            need(stack[-1] == name, f"{label}: </{name}> closes <{stack[-1]}>")
            stack.pop()
    if stack:
        raise BuildError(f"{label}: unclosed <{stack[-1]}>")


# ── Escaping ─────────────────────────────────────────────────
def escape(s, quote=True):
    """HTML-escape a value. `quote=False` for text that is not in an attribute."""
    s = (str(s).replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
    return s.replace('"', "&quot;") if quote else s


# ── Manifest completeness ────────────────────────────────────
def require_listed(directory, pattern, listed, label=None):
    """Require every file matching `pattern` in `directory` to appear in `listed`.

    The cascade order of CSS, the load order of JS, and the set of page
    fragments are all hand-listed on purpose: glob order varies by machine, and
    a stylesheet that lands after the one it is meant to override is a bug you
    only see on someone else's checkout.

    The cost of hand-listing is that a newly added file is silently ignored.
    This is that cost paid back. Returns the listed names so it can wrap a
    constant in place:

        CSS_ORDER = require_listed(SRC / "css", "*.css", ["tokens.css", ...])
    """
    label = label or str(directory)
    present = {p.name for p in directory.glob(pattern)}
    unlisted = sorted(present - set(listed))
    need(not unlisted,
         f"{label}: file(s) not listed in the build order: {', '.join(unlisted)}. "
         "Add them where they belong, or delete them.")
    missing = [n for n in listed if n not in present]
    need(not missing,
         f"{label}: listed file(s) do not exist: {', '.join(missing)}")
    return list(listed)


__all__ = ["check_balance", "escape", "require_listed", "VOID"]
