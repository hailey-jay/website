"""The shared skeleton: read fragments, bundle assets, fill a shell, write.

Deliberately thin and deliberately last. It has no opinion about what a
section is, how navigation works, or where content comes from - those are the
parts that differ per site and should keep differing. Everything here is the
part that was identical four times over.
"""
from pathlib import Path

from . import minify as _minify
from .errors import need
from .markup import require_listed
from .text import render, strip_comments


def read(path, comments=False):
    """Read a source file as UTF-8. HTML comments are stripped by default.

    Encoding is pinned at every read and write in this module. The sites carry
    literal §, –, ’, − and ← in their prose, and a platform-default encoding is
    how those turn into mojibake on one machine and not another."""
    text = Path(path).read_text(encoding="utf-8")
    return text if comments else strip_comments(text)


def write(path, text):
    """Write UTF-8, creating parent directories. Returns bytes written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path.stat().st_size


def concat(directory, names, banner=True, check=True):
    """Concatenate files in the given order.

    The order is explicit, never a glob. Path.glob yields directory order, so a
    cascade built from one varies by machine, and a stylesheet that lands after
    the one it is meant to override is a bug that only appears on someone
    else's checkout.

    `check` additionally fails if the directory holds a file of the same kind
    that the list forgot, which is the cost of hand-listing paid back."""
    directory = Path(directory)
    if check and names:
        suffix = Path(names[0]).suffix
        require_listed(directory, f"*{suffix}", names)
    parts = []
    for name in names:
        body = (directory / name).read_text(encoding="utf-8")
        parts.append(f"/* {name} */\n{body}" if banner and
                     Path(name).suffix == ".css" else body)
    return "\n\n".join(parts)


def css_block(directory, names, minifier=_minify.css, check=True):
    """An inline <style> block from an ordered list of stylesheets."""
    return "<style>" + minifier(concat(directory, names, check=check)) + "</style>"


def js_block(directory, names, minifier=_minify.js, preamble="", check=True):
    """An inline <script> block from an ordered list of scripts.

    `preamble` is for the values the build computes and the scripts need - the
    section list, a title map - emitted ahead of the bundle."""
    body = concat(directory, names, banner=False, check=check)
    return "<script>" + (preamble + "\n" if preamble else "") + minifier(body) + "</script>"


def sections(fragments, wrap):
    """Join page fragments into document order using a `wrap(key, markup)`.

    `fragments` is an ordered mapping; `wrap` returns the markup for one
    section. Kept as a callback because every site wraps differently - a class
    here, an aria-label there, a data attribute for lazy MathJax - and none of
    those belong in a shared function."""
    return "\n\n".join(wrap(key, markup) for key, markup in fragments.items())


def fill(template, **fields):
    """Fill the shell template. Re-exported so a site imports one name."""
    return render(template, **fields)


def sitemap(urls, path=None):
    """A minimal sitemap.xml. Only real pages belong in it: hash sections are
    one document to a crawler, which is also why a page with them wants a
    canonical link."""
    need(urls, "sitemap: no urls")
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
            + "</urlset>\n")
    if path:
        write(path, body)
    return body


__all__ = ["read", "write", "concat", "css_block", "js_block", "sections",
           "fill", "sitemap"]
