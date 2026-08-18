"""sitekit - the shared parts of four hand-rolled site builds.

Not a framework and not a CLI. Each site keeps its own make.py and its own
makefile; this holds the pieces that were being written four times, at four
levels of quality, and drifting apart.

What is here: text and data-format parsing, template filling, markup
validation, one responsive-image pipeline, a post-build checker, asset
bundling, minification, and a deterministic rebuild-and-diff.

What is deliberately not here: anything that knows what a site *is*. Calendars,
author macros, RSS, blog directives, people and paper tables, decorative SVG -
those are content models, they belong to their sites, and this is better for
refusing them.

Usage is by import, one module at a time:

    from sitekit.text import render, repeat, split_sections
    from sitekit.markup import check_balance
    from sitekit.images import Pipeline, mirrored
    from sitekit import assemble, check, minify
"""
from .errors import BuildError, need

__version__ = "0.1.0"

__all__ = ["BuildError", "need", "__version__"]
