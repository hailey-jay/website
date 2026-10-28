"""What the home page and the Sagitta pages build with alike.

make.py builds the home page and the feed, sagitta_pages.py the standalone
Sagitta pages; both reach the image pipeline, the [gallery]/[image]
directives, front matter, and the maths head through here, so a post and the
tutorial cannot drift apart in how they set a figure. Nothing in this module
knows about a particular section or page.
"""
import sys
from pathlib import Path

# Everything is anchored to the repo root rather than the working directory,
# so the build can be run from anywhere. The root is also where the vendored
# sitekit package lives, so it goes on the path before sitekit is imported.
root = Path(__file__).resolve().parent.parent
src  = root / "src"
sys.path.insert(0, str(root))

from functools import cache
from html import escape
import re

from sitekit import assemble
from sitekit.errors import need
from sitekit.images import Pipeline, mirrored
from sitekit.text import parse_fields, parse_kv, render, rows_of, split_sections

BASE_URL = "https://haileyjay.net"

# ── Images ───────────────────────────────────────────────────
# Gallery originals are 1024-1600px but are displayed at ~200px in a grid, so
# the grid was pulling half-megabyte photos to fill a thumbnail. Copies are
# derived per image and offered in the srcset ahead of the original, which
# remains what the lightbox opens:
#   160   the Blog list's 56px icon, at 2x
#   440   the About carousel's 220px card and a grid card, at 2x
#   640   a grid card on a phone, and the original single copy
#   1280  a 420px inline figure at 2x and 3x, which otherwise skipped past
#         640 to the multi-megabyte original
# A source between rungs gets no copy at its own width: the original is
# already in the srcset at that width, and the Sagitta screenshots stay
# lossless PNGs.
# Derivatives mirror the source tree under images/thumbs/, minus a leading
# "images/" so blog photos land at images/thumbs/blog/... rather than
# images/thumbs/images/blog/... The 640 copy keeps the unsuffixed name it had
# when it was the only one; the others are suffixed with their width.
_unsuffixed = mirrored("images/thumbs", strip="images/")
_suffixed   = mirrored("images/thumbs", strip="images/", width_suffix=True)

def thumb_path(rel, width):
    return (_unsuffixed if width == 640 else _suffixed)(rel, width)

photos = Pipeline(
    root      = root,
    widths    = (160, 440, 640, 1280),
    out       = thumb_path,
    min_width = 640,
    own_width_rung = False,
)

# Grid cards sit in a ~640px main column at three-up, and go roughly
# half-width once the sidebar collapses. Layout, so it stays here.
GRID_SIZES   = "(max-width: 640px) 45vw, 210px"
FIGURE_SIZES = "(max-width: 480px) 100vw, 420px"

def thumb_for(path, width):
    """The narrowest derivative of `path` at least `width` wide, the widest
    if none is, or `path` itself if it has none."""
    derivatives = photos.derivatives(path)
    if not derivatives:
        return path
    return next((p for p, w in derivatives if w >= width), derivatives[-1][0])

def parse_row(row):
    """Split an `image | caption | alt` row.

    The caption fills the card title, the lightbox caption, and, absent
    a third field, the alt text."""
    img, caption, alt = parse_fields(row, 3)
    return img, caption, alt or caption

# ── Shared sub-templates ─────────────────────────────────────
# Markup used by more than one section or page: the gallery card, the grid
# that holds cards, and the inline figure. The card is identical for comics
# and blog galleries apart from the thumb class, which picks which lightbox
# instance claims it (see makeLightbox in main.js).
@cache
def load_shared():
    """The §NAME§ sub-templates shared between sections."""
    return split_sections(assemble.read(src / "shared.html"))

# ── Image directives ─────────────────────────────────────────
# A post body, or the Sagitta tutorial, may contain image directives instead
# of hand-written markup:
#
#   [gallery]
#   hilles | Hilles Hall
#   path   | The gravel path | alt text, if it should differ from the caption
#   [/gallery]
#
#   [image mordor | A passthrough between buildings]
#
# Both take `image | caption | alt` rows. A bare stem resolves against the
# caller's image folder (images/blog/<slug>/ for a post); a value with a slash
# is used as-is (and a missing extension defaults to .webp).
# One alternation rather than two passes, so a body's galleries and its
# inline figures are expanded in a single left-to-right sweep and the
# collected image list comes out in true source order.
DIRECTIVE_RE = re.compile(
    r"^[ \t]*\[gallery\][ \t]*\n(?P<rows>.*?)^[ \t]*\[/gallery\][ \t]*$"
    r"|"
    r"^[ \t]*\[image[ \t]+(?P<row>[^\]\n]+)\][ \t]*$",
    re.M | re.S,
)

def resolve_image(img, base):
    """A row's image value as a site path.

    A bare stem resolves against `base`, which is also the label a missing
    image is reported under. An extensionless value is a .webp, since that is
    what the galleries hold. `base` carries any ../ prefix a standalone page
    needs; the pipeline strips it before touching the disk and puts it back in
    the markup."""
    if "/" not in img:
        img = f"{base}/{img}"
    if "." not in img.rsplit("/", 1)[-1]:
        img += ".webp"
    return photos.require(img, base)

def build_image(row, base, template, collected, sizes=None):
    img, caption, alt = parse_row(row)
    img = resolve_image(img, base)
    # Recorded as raw text, in DOM order. The carousel assigns these to
    # img.alt as a property, so they must not be HTML-escaped. The
    # carousel wants the thumbnail; the lightbox wants the original.
    collected.append({"src": img, "thumb": thumb_for(img, 440), "alt": alt})
    return render(template,
        thumb_class = "gallery-thumb",
        label       = "View image",
        src         = img,
        img_attrs   = photos.attrs(img, sizes or GRID_SIZES),
        alt         = escape(alt),
        caption     = escape(caption),
        dims        = photos.dims_attr(img),
    ).strip()

def build_gallery(rows, base, collected, card_tmpl, grid_tmpl):
    cards = [build_image(line, base, card_tmpl, collected) for line in rows_of(rows)]
    return render(grid_tmpl, cards="\n  ".join(c.replace("\n", "\n  ") for c in cards)).strip()

def expand_directives(body, base, collected):
    """`body` with its directives expanded into page markup.

    Each image is appended to `collected` as it is met. The feed expands the
    same directives against plainer markup of its own (see make.py)."""
    shared = load_shared()

    def expand(m):
        if m.group("rows") is not None:
            return build_gallery(m.group("rows"), base, collected,
                                 shared["CARD"], shared["GRID"])
        return build_image(m.group("row"), base, shared["FIGURE"], collected,
                           FIGURE_SIZES)

    return DIRECTIVE_RE.sub(expand, body)

# ── Front matter ─────────────────────────────────────────────
def front_matter(raw, label, keys):
    """(meta, body) for a file that opens with a key: value block.

    The block is ended by a blank line. An explicit terminator means a body
    whose first line happens to contain a colon cannot be swallowed as
    metadata."""
    head, sep, body = raw.strip().partition("\n\n")
    need(sep, f"{label} has no blank line after its front matter")
    return parse_kv(head, f"{label} front matter", keys), body

# ── Maths ──────────────────────────────────────────────────
# KaTeX is vendored in katex/ and rendered in the reader's browser, since the
# server runs no build. A page links it only when its prose holds \( or \[;
# <pre> and <code> are left out of the test, since auto-render leaves them out
# of the rendering, so a tikz-cd listing or a `\coker` in code costs nothing.
# There are no $ delimiters, so a price in prose is never read as maths.
MATH_RE = re.compile(r"\\[(\[]")
VERBATIM_RE = re.compile(r"<(pre|code)\b.*?</\1>", re.S)

MATH_HEAD = """<link rel="stylesheet" href="{up}katex/katex.min.css">
    <script defer src="{up}katex/katex.min.js"></script>
    <script defer src="{up}katex/auto-render.min.js"></script>
    <script>document.addEventListener('DOMContentLoaded',function(){renderMathInElement(document.body,{delimiters:[{left:'\\\\[',right:'\\\\]',display:true},{left:'\\\\(',right:'\\\\)',display:false}],throwOnError:false});});</script>"""

def math_head(body, up):
    """The KaTeX tags for a page's <head>, or nothing if it sets no maths."""
    if not MATH_RE.search(VERBATIM_RE.sub("", body)):
        return ""
    return render(MATH_HEAD, up=up)
