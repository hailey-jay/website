"""The one exception type the library raises.

Every failure here is a content or configuration mistake with a fix the author
can make, so it gets a sentence rather than a traceback. Call sites catch
BuildError in main() and exit non-zero with the message.

This exists because the sites it replaces used bare `assert` for exactly these
failures, and `python -O` strips assertions: the build would then skip the check
and emit corrupt output instead of stopping."""


class BuildError(Exception):
    pass


def need(condition, message):
    """Assert-shaped, but survives -O and raises something catchable."""
    if not condition:
        raise BuildError(message)
