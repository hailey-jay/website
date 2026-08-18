import sys
from pathlib import Path

# Everything is anchored to the repo root rather than the working directory,
# so the script can be run from anywhere. The root is also where the vendored
# sitekit package lives, so it goes on the path before sitekit is imported.
root = Path(__file__).resolve().parent.parent
src  = root / "src"
sys.path.insert(0, str(root))

from datetime import datetime, timezone
from dataclasses import dataclass, field
import re
import json
from html import escape

from sitekit import assemble
from sitekit.errors import BuildError, need
from sitekit.images import Pipeline, mirrored
from sitekit.markup import check_balance, require_listed
from sitekit.text import (
    group_rows, indent, paragraphs, parse_fields, parse_kv, parse_records,
    render, repeat, rows_of, split_data, split_sections, strip_comments,
)

BASE_URL = "https://haileyjay.net"

tabs = ["about", "cv", "teaching", "comics", "blog", "links", "printlab"]
unpublished = {"printlab", "links"}  # still built, but emitted as an empty section

# The two partials that are not sections: the page shell and the shared
# sub-templates. Listed so `require_listed` can tell a new section partial
# that nobody wired up from one of these.
EXTRA_PARTIALS = ["index.html", "shared.html"]

# ── Images ───────────────────────────────────────────────────
# Gallery originals are 1024-1600px but are displayed at ~200px in a grid and
# capped at 640px in the lightbox, so the grid was pulling half-megabyte photos
# to fill a thumbnail. One 640px copy is derived per image and offered first;
# the original stays in the srcset for wide viewports and remains what the
# lightbox opens. Derivatives mirror the source tree under images/thumbs/,
# minus a leading "images/" so blog photos land at images/thumbs/blog/...
# rather than images/thumbs/images/blog/...
photos = Pipeline(
    root      = root,
    widths    = (640,),
    out       = mirrored("images/thumbs", strip="images/"),
    min_width = 640,
)

# Grid cards sit in a ~640px main column at three-up, and go roughly
# half-width once the sidebar collapses. Layout, so it stays here.
GRID_SIZES   = "(max-width: 640px) 45vw, 210px"
FIGURE_SIZES = "(max-width: 480px) 100vw, 420px"

def thumb_for(path):
    """The narrowest derivative of `path`, or `path` itself if it has none."""
    derivatives = photos.derivatives(path)
    return derivatives[0][0] if derivatives else path

def load_partials():
    """Read every section partial, comments stripped."""
    return {key: assemble.read(src / f"{key}.html") for key in tabs}

def parse_row(row):
    """Split an `image | caption | alt` row.

    The caption fills the card title, the lightbox caption, and, absent
    a third field, the alt text."""
    img, caption, alt = parse_fields(row, 3)
    return img, caption, alt or caption

# ── Shared sub-templates ─────────────────────────────────────
# Markup used by more than one section. The gallery card is identical
# for comics and blog galleries apart from the thumb class, which picks
# which lightbox instance claims it (see makeLightbox in main.js).
def load_shared():
    """The §NAME§ sub-templates shared between sections."""
    return split_sections(assemble.read(src / "shared.html"))

# ── Parse comics ─────────────────────────────────────────────
# Data lives in src/data/comics.txt: one `stem | caption | alt` row per
# comic, the same row format the blog uses. Blank lines are ignored.
def parse_comics(raw, template):
    parts = split_sections(raw)
    data  = (src / "data/comics.txt").read_text(encoding="utf-8")

    records = []
    for line in rows_of(data):
        stem, caption, alt = parse_row(line)
        path = f"comics/{stem}.webp"
        photos.require(path, "comics")
        records.append({
            "src":       path,
            "img_attrs": photos.attrs(path, GRID_SIZES),
            "alt":       escape(alt),
            "caption":   escape(caption),
        })
    body = repeat(template, records,
                  thumb_class="comic-thumb", label="View comic")
    return render(parts[""], body=body)

# ── Parse blog ───────────────────────────────────────────────
# One file per post under src/data/blog/, named <isodate>-<slug>.html:
# key: value meta lines, then the HTML body. Filename sort gives
# newest-first order; an underscore prefix marks a draft (skipped).
# A post body may contain image directives instead of hand-written markup:
#
#   [gallery]
#   hilles | Hilles Hall
#   path   | The gravel path | alt text, if it should differ from the caption
#   [/gallery]
#
#   [image mordor | A passthrough between buildings]
#
# Both take `image | caption | alt` rows. A bare stem resolves to
# images/blog/<slug>/<stem>.webp; a value with a slash is used as-is
# (and a missing extension defaults to .webp).
# One alternation rather than two passes, so a post's galleries and its
# inline figures are expanded in a single left-to-right sweep and the
# collected image list comes out in true source order.
DIRECTIVE_RE = re.compile(
    r"^[ \t]*\[gallery\][ \t]*\n(?P<rows>.*?)^[ \t]*\[/gallery\][ \t]*$"
    r"|"
    r"^[ \t]*\[image[ \t]+(?P<row>[^\]\n]+)\][ \t]*$",
    re.M | re.S,
)

def build_image(row, slug, template, collected, sizes=None):
    img, caption, alt = parse_row(row)
    if "/" not in img:
        img = f"images/blog/{slug}/{img}"
    if "." not in img.rsplit("/", 1)[-1]:
        img += ".webp"
    photos.require(img, f"post: {slug}")
    # Recorded as raw text, in DOM order. The carousel assigns these to
    # img.alt as a property, so they must not be HTML-escaped. The
    # carousel wants the thumbnail; the lightbox wants the original.
    collected.append({"src": img, "thumb": thumb_for(img), "alt": alt})
    return render(template,
        thumb_class = "gallery-thumb",
        label       = "View image",
        src         = img,
        img_attrs   = photos.attrs(img, sizes or GRID_SIZES),
        alt         = escape(alt),
        caption     = escape(caption),
        dims        = photos.dims_attr(img),
    ).strip()

def build_gallery(rows, slug, collected, card_tmpl, grid_tmpl):
    cards = [build_image(line, slug, card_tmpl, collected) for line in rows_of(rows)]
    return render(grid_tmpl, cards="\n  ".join(c.replace("\n", "\n  ") for c in cards)).strip()

# ── Feed rendering ───────────────────────────────────────────
# The page markup is wrong for a feed twice over: it wraps every image
# in a <button> that carries the lightbox data (feed sanitisers drop
# buttons, taking the <img> with them), and its URLs are relative, so
# a reader resolves them against its own origin and shows nothing.
# Directives are therefore expanded a second time against plain
# <figure> markup, and the result is made absolute.
FEED_FIGURE = (
    '<figure>\n'
    '  <img src="{src}" alt="{alt}"{dims}>\n'
    '  <figcaption>{caption}</figcaption>\n'
    '</figure>'
)

FEED_URL_RE = re.compile(r'\b(src|href)="(?!https?://|mailto:|//)([^"]*)"')

def absolutize(markup):
    """Point relative src/href at BASE_URL, including bare #fragments."""
    def fix(m):
        attr, value = m.group(1), m.group(2)
        return f'{attr}="{BASE_URL}/{value.lstrip("/")}"'
    return FEED_URL_RE.sub(fix, markup)

def build_feed_body(body, slug):
    throwaway = []

    def expand(m):
        if m.group("rows") is not None:
            figures = [build_image(line, slug, FEED_FIGURE, throwaway)
                       for line in rows_of(m.group("rows"))]
            return "\n".join(figures)
        return build_image(m.group("row"), slug, FEED_FIGURE, throwaway)

    return absolutize(DIRECTIVE_RE.sub(expand, body))

POST_NAME_RE = re.compile(r"^(?P<isodate>\d{4}-\d{2}-\d{2})-(?P<slug>.+)$")

def ordinal(n):
    if 11 <= n % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

def display_date(isodate):
    dt = datetime.strptime(isodate, "%Y-%m-%d")
    return f"{dt.strftime('%B')} {ordinal(dt.day)}, {dt.year}"

def load_blog_entries():
    """Yield (isodate, slug, text) per published post.

    The date and slug come from the filename rather than the front
    matter, so they cannot drift out of sync with it. Filename sort
    gives newest-first; an underscore prefix marks a draft."""
    files = sorted((src / "data/blog").glob("*.html"), reverse=True)
    entries = []
    for f in files:
        if f.name.startswith("_"):
            continue
        m = POST_NAME_RE.match(f.stem)
        need(m, f"Post {f.name} is not named <isodate>-<slug>.html")
        entries.append((m["isodate"], m["slug"], f.read_text(encoding="utf-8")))
    return entries

@dataclass
class Post:
    slug:      str
    isodate:   str
    title:     str
    teaser:    str
    body:      str
    feed_body: str = ""
    images:    list = field(default_factory=list)

    @property
    def date(self):
        return display_date(self.isodate)

    @property
    def url(self):
        return f"{BASE_URL}/#blog-{self.slug}"

def parse_blog(raw, raw_entries, card_tmpl):
    parts           = split_sections(raw)
    entry_template  = parts["ENTRY"]
    post_template   = parts["POST"]
    grid_template   = parts["GRID"]
    figure_template = parts["FIGURE"]

    posts = []

    for isodate, slug, raw in raw_entries:
        # Front matter is the leading key: value block, ended by a blank
        # line. An explicit terminator means a body whose first line
        # happens to contain a colon cannot be swallowed as metadata.
        head, sep, body = raw.strip().partition("\n\n")
        need(sep, f"Post {slug} has no blank line after its front matter")

        meta = parse_kv(head, f"Post {slug} front matter", ("title", "teaser"))
        body = strip_comments(body).strip()

        post = Post(
            slug    = slug,
            isodate = isodate,
            title   = meta["title"],
            teaser  = meta["teaser"],
            body    = "",
        )

        # Images are collected as the directives expand, in source order.
        def expand(m, post=post):
            if m.group("rows") is not None:
                return build_gallery(m.group("rows"), post.slug, post.images,
                                     card_tmpl, grid_template)
            return build_image(m.group("row"), post.slug, figure_template, post.images, FIGURE_SIZES)

        post.body = DIRECTIVE_RE.sub(expand, body)
        check_balance(post.body, f"Post {slug}")

        post.feed_body = build_feed_body(body, post.slug)
        check_balance(post.feed_body, f"Post {slug} (feed)")

        posts.append(post)

    def thumb_for_post(post):
        if not post.images:
            return ""
        return (f'<img class="blog-entry-thumb" src="{post.images[0]["thumb"]}" alt="" '
                f'width="56" height="56" loading="lazy" decoding="async">')

    entries = repeat(entry_template, [
        {"slug": p.slug, "date": p.date, "title": p.title,
         "teaser": p.teaser, "thumb": thumb_for_post(p)}
        for p in posts
    ])
    sections = repeat(post_template, [
        {"slug": p.slug, "title": p.title, "date": p.date, "body": p.body}
        for p in posts
    ])
    return render(parts[""], entries=entries, posts=sections), posts

def carousel_images(posts):
    """Every blog image, in post order, for the homepage carousel."""
    return [{**image, "slug": post.slug, "title": post.title}
            for post in posts for image in post.images]

# ── Parse about ──────────────────────────────────────────────
# Everything the page says lives in src/data/about.txt: the identity
# fields, the labelled meta pairs, the bio prose, and the Lately note.
# The partial is left holding only the shape.
def parse_about(raw, blog_images):
    parts    = split_sections(raw)
    data     = split_data((src / "data/about.txt").read_text(encoding="utf-8"))
    identity = parse_kv(data[""], "about",
                        ("name", "pronouns", "splash", "photo_alt", "photo_caption"))

    meta = repeat(parts["META_ROW"], [
        {"label": label, "value": value}
        for label, value in (parse_fields(row, 2) for row in rows_of(data["META"]))
    ], sep="\n")

    return render(parts[""], **identity,
        meta             = indent(meta, "    "),
        bio              = paragraphs(data["BIO"]),
        lately           = data["LATELY"],
        blog_images_json = json.dumps(blog_images),
    )

# ── Generate RSS feed ─────────────────────────────────────────
def format_rfc2822(isodate):
    dt = datetime.strptime(isodate, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")

def cdata(text):
    """Wrap text in CDATA, splitting any literal ]]> that would close it early."""
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"

def build_feed(posts):
    items_xml = ""
    for post in posts:
        items_xml += f"""
    <item>
        <title>{escape(post.title, quote=False)}</title>
        <link>{post.url}</link>
        <guid isPermaLink="true">{post.url}</guid>
        <pubDate>{format_rfc2822(post.isodate)}</pubDate>
        <description>{escape(post.teaser, quote=False)}</description>
        <content:encoded>{cdata(post.feed_body)}</content:encoded>
    </item>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">
    <channel>
        <title>Hailey Jay Garcia</title>
        <link>{BASE_URL}/</link>
        <description>Math, teaching, and whatever else is on my mind.</description>
        <language>en-us</language>
        <lastBuildDate>{format_rfc2822(posts[0].isodate) if posts else ""}</lastBuildDate>
        <atom:link href="{BASE_URL}/rss.xml" rel="self" type="application/rss+xml"/>
{items_xml}
    </channel>
</rss>"""

# ── Parse print lab ──────────────────────────────────────────
def parse_printlab(raw, card_tmpl):
    parts = split_sections(raw)

    html_template     = parts[""]
    printer_template  = parts["PRINTER"]
    filament_template = parts["FILAMENT"]
    filament_row_tmpl = parts["FILAMENT_ROW"]

    # Data lives in src/data/printlab.txt, not in the partial. The file
    # is absent while the section is unpublished (the last contents were
    # placeholders and were archived off); restore it before removing
    # "printlab" from `unpublished`.
    data_file = src / "data/printlab.txt"
    need(data_file.exists(),
         "src/data/printlab.txt is missing; printlab cannot be published without it")
    data = split_data(data_file.read_text(encoding="utf-8"))
    meta = parse_kv(data[""], "printlab meta")

    # ── Printers ──────────────────────────────────────────────
    STATUS_LABELS = {
        "idle":        "Idle",
        "printing":    "Printing",
        "offline":     "Offline",
        "maintenance": "Maintenance",
    }

    printers = parse_records(data["PRINTERS"], "printlab printer", ("name", "status"))
    printer_rows = repeat(printer_template, [
        {
            "name":         p["name"],
            "status":       p["status"],
            "status_label": STATUS_LABELS.get(p["status"], p["status"].title()),
            "note":         p.get("note", ""),
        }
        for p in printers
    ], sep="\n        ")

    # ── Gallery ───────────────────────────────────────────────
    # Same `image | caption | alt` rows and same shared card as the
    # comics and blog galleries; only the aria-label verb differs.
    gallery_records = []
    for line in rows_of(data["GALLERY"]):
        img, caption, alt = parse_row(line)
        photos.require(img, "print gallery")
        gallery_records.append({
            "src":       img,
            "img_attrs": photos.attrs(img, GRID_SIZES),
            "alt":       escape(alt),
            "caption":   escape(caption),
        })
    gallery_cards = repeat(card_tmpl, gallery_records,
                           thumb_class="gallery-thumb", label="View print")

    # ── Filament ──────────────────────────────────────────────
    # Rows are grouped under bare diameter headings ("1.75mm"), so a
    # heading is any non-row line; everything else is a filament row.
    groups = []
    for diameter, rows in group_rows(data["FILAMENT"], "filament"):
        records = []
        for line in rows:
            material, color, hex_val, stock, blurb = parse_fields(line, 5)
            records.append({
                "material": material,
                "color":    color,
                "hex":      hex_val,
                "stock":    f"{stock} spools",
                "blurb":    f'<span class="filament-blurb">({blurb})</span>' if blurb else "",
            })
        groups.append((diameter, records))

    filament = repeat(filament_template, [
        {
            "diameter": diameter,
            "rows":     repeat(filament_row_tmpl, rows, sep="\n            "),
        }
        for diameter, rows in groups if rows
    ])

    return render(html_template,
        printer_count = meta.get("printer_count", ""),
        printers      = printer_rows,
        gallery       = gallery_cards,
        filament      = filament,
    )

# ── Parse links ──────────────────────────────────────────────
# src/data/links.txt is heading-then-rows, the same shape as the
# filament table: a bare line opens a group, and each `label | url`
# row under it is one link. An optional third field names a variant
# template, which is how the RSS entry gets its icon.
def parse_links(raw):
    parts = split_sections(raw)
    data  = (src / "data/links.txt").read_text(encoding="utf-8")

    groups = []
    for title, rows in group_rows(data, "links"):
        links = []
        for row in rows:
            label, url, variant = parse_fields(row, 3)
            key = f"LINK_{variant.upper()}" if variant else "LINK"
            need(key in parts, f"links: no §{key}§ template for {label!r}")
            links.append(render(parts[key], label=label, url=url).strip())
        groups.append({"title": title, "links": indent("\n".join(links), "        ")})

    return render(parts[""], groups=repeat(parts["GROUP"], groups))

# ── Assemble index.html ──────────────────────────────────────

def wrap_section(key, markup):
    # Checked here rather than at read time: a partial is only whole
    # once its sub-templates have been filled, and this is also where a
    # data file's inline markup (a bio paragraph's link, a meta value)
    # first meets the page.
    check_balance(markup, f"Section {key}")
    active = ' class="active"' if key == "about" else ""
    return f'<section id="{key}"{active}>\n{markup}\n</section>'

# An unpublished section is emitted as an empty string, so its <section>
# disappears from the page while anything linking to it stays and lands
# nowhere.
NAV_TARGET_RE = re.compile(r'href="#([\w-]+)"')

def check_nav(template):
    for target in NAV_TARGET_RE.findall(template):
        need(target not in unpublished,
             f"src/index.html links to #{target}, which is in `unpublished` "
             "and is emitted as an empty section")

def build_index(raw_content):
    sections = {key: "" if key in unpublished else wrap_section(key, raw_content[key])
                for key in tabs}

    aux = {
        "css": assemble.css_block(src, ["main.css"]),
        "js":  assemble.js_block(src, ["main.js"]),
    }

    index_template = assemble.read(src / "index.html")
    check_balance(index_template, "src/index.html")
    check_nav(index_template)
    return assemble.fill(index_template, **sections, **aux)

# ── Build ────────────────────────────────────────────────────
def main():
    # The section list is hand-written, so a new src/foo.html would
    # otherwise be built by nobody and noticed by no one.
    require_listed(src, "*.html",
                   [f"{key}.html" for key in tabs] + EXTRA_PARTIALS, "src")

    raw_content   = load_partials()
    card_template = load_shared()["CARD"]

    raw_content["comics"] = parse_comics(raw_content["comics"], card_template)

    raw_content["blog"], posts = parse_blog(
        raw_content["blog"], load_blog_entries(), card_template)

    raw_content["about"] = parse_about(raw_content["about"], carousel_images(posts))

    # Unpublished sections are emitted empty by build_index, so their
    # data files need not exist and are not parsed.
    if "printlab" not in unpublished:
        raw_content["printlab"] = parse_printlab(raw_content["printlab"], card_template)
    if "links" not in unpublished:
        raw_content["links"] = parse_links(raw_content["links"])

    assemble.write(root / "rss.xml", build_feed(posts))
    assemble.write(root / "index.html", build_index(raw_content))
    # One page, so one URL. The sections are hash fragments, which are the
    # same document to a crawler and do not belong here.
    assemble.sitemap([f"{BASE_URL}/"], root / "sitemap.xml")

if __name__ == "__main__":
    try:
        main()
    except BuildError as e:
        raise SystemExit(f"build failed: {e}")
