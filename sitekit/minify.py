"""One answer to minification instead of four.

rcssmin and rjsmin, both C-accelerated with pure-Python fallbacks, both
conservative enough to run on hand-written source. Chosen over a hand-rolled
regex pass (which is how you meet automatic semicolon insertion at two in the
morning) and over shelling out to a binary (which is one more thing to have
installed on a machine that is only supposed to need Python).

Minification is optional: a site that has not installed them gets a clear
message rather than an ImportError traceback, and `passthrough` is available
for a build that would rather ship readable source."""
from .errors import BuildError

_HINT = ("pip install rcssmin rjsmin  (or call sitekit.minify.passthrough "
         "if this site does not want minification)")


def css(text):
    try:
        import rcssmin
    except ImportError:
        raise BuildError(f"CSS minification needs rcssmin. {_HINT}")
    return rcssmin.cssmin(text)


def js(text):
    try:
        import rjsmin
    except ImportError:
        raise BuildError(f"JS minification needs rjsmin. {_HINT}")
    return rjsmin.jsmin(text)


def html(markup):
    """Strip leading and trailing whitespace per line, drop blank lines.

    Deliberately the whole of it. Anything more needs to know which elements
    are whitespace-sensitive, and getting that wrong shows up as a missing
    space between two inline elements on one page, six months later."""
    return "\n".join(line.strip() for line in markup.split("\n") if line.strip())


def passthrough(text):
    return text


__all__ = ["css", "js", "html", "passthrough"]
