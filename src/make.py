"""Build the home page, the feed, the sitemap, and (through sagitta_pages)
the standalone Sagitta pages.

    python src/make.py

What both kinds of page build with, the image pipeline and the image
directives among it, is in common.py.
"""
# common goes first: it puts the repo root, and so the vendored sitekit, on
# the path.
from common import (
    BASE_URL, DIRECTIVE_RE, GRID_SIZES, build_image, expand_directives,
    front_matter, load_shared, math_head, parse_row, photos, root, src,
)
import sagitta_pages

from datetime import datetime, timezone
from dataclasses import dataclass, field
import json
from html import escape
import re

from sitekit import assemble
from sitekit.errors import BuildError, need
from sitekit.markup import check_balance, require_listed
from sitekit.text import (
    expect_placeholders, indent, paragraphs, parse_fields, parse_kv,
    render, repeat, rows_of, split_data, split_sections, strip_comments,
)

tabs = ["about", "cv", "papers", "teaching", "comics", "blog", "colophon"]
unpublished = set()  # built, but emitted as an empty section

# The two partials that are not sections: the page shell and the shared
# sub-templates. Listed so `require_listed` can tell a new section partial
# that nobody wired up from one of these.
EXTRA_PARTIALS = ["index.html", "shared.html"]

def load_partials():
    """Read every section partial, comments stripped."""
    return {key: assemble.read(src / f"{key}.html") for key in tabs}

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
# Image directives in a body are expanded by common.expand_directives, with
# bare stems resolving to images/blog/<slug>/.
# An optional `colour: #rrggbb` line gives the post its own colour (as --post,
# see main.css); without one it takes the Blog accent. Dates use it mixed 30%
# toward the ink, so any mid-tone stays readable as text in both themes.

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
    base = f"images/blog/{slug}"

    def expand(m):
        if m.group("rows") is not None:
            figures = [build_image(line, base, FEED_FIGURE, throwaway)
                       for line in rows_of(m.group("rows"))]
            return "\n".join(figures)
        return build_image(m.group("row"), base, FEED_FIGURE, throwaway)

    return absolutize(DIRECTIVE_RE.sub(expand, body))

COLOUR_RE = re.compile(r"#[0-9a-fA-F]{6}")

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
    colour:    str = ""

    @property
    def style(self):
        return f' style="--post: {self.colour}"' if self.colour else ""

    @property
    def date(self):
        return display_date(self.isodate)

    @property
    def url(self):
        return f"{BASE_URL}/#blog-{self.slug}"

def parse_blog(raw, raw_entries):
    parts          = split_sections(raw)
    entry_template = parts["ENTRY"]
    post_template  = parts["POST"]

    posts = []

    for isodate, slug, raw in raw_entries:
        meta, body = front_matter(raw, f"Post {slug}", ("title", "teaser"))
        body = strip_comments(body).strip()

        post = Post(
            slug    = slug,
            isodate = isodate,
            title   = meta["title"],
            teaser  = meta["teaser"],
            body    = "",
            colour  = meta.get("colour", ""),
        )
        need(not post.colour or COLOUR_RE.fullmatch(post.colour),
             f"Post {slug}: colour must be #rrggbb, not {post.colour!r}")

        # Images are collected as the directives expand, in source order.
        post.body = expand_directives(body, f"images/blog/{slug}", post.images)
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
         "teaser": p.teaser, "thumb": thumb_for_post(p), "style": p.style}
        for p in posts
    ])
    sections = repeat(post_template, [
        {"slug": p.slug, "title": p.title, "date": p.date, "body": p.body,
         "style": p.style}
        for p in posts
    ])
    return render(parts[""], entries=entries, posts=sections), posts

def carousel_images(posts):
    """Every blog image, in post order, for the homepage carousel."""
    return [{**image, "slug": post.slug, "title": post.title, "colour": post.colour}
            for post in posts for image in post.images]

# ── Parse about ──────────────────────────────────────────────
# Everything the page says lives in src/data/about.txt: the identity
# fields, the meta lines under the name, the bio prose, and the Lately note.
# The partial is left holding only the shape.
def parse_about(raw, blog_images):
    parts    = split_sections(raw)
    data     = split_data((src / "data/about.txt").read_text(encoding="utf-8"))
    identity = parse_kv(data[""], "about",
                        ("name", "pronouns", "splash", "photo_alt", "photo_caption"))

    # One printed line per META line: position, advisors, then contact. Each
    # is its own block, so main.css can space the lines apart while a line
    # that wraps on a phone stays tight. Each • is wrapped to colour it.
    meta = "\n".join('<span class="about-line">'
                     + line.replace("•", '<span class="about-sep" aria-hidden="true">•</span>')
                     + "</span>"
                     for line in rows_of(data["META"]))

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
        <description>Combinatorics, topology, comics, and whatever else is on my mind.</description>
        <language>en-us</language>
        <lastBuildDate>{format_rfc2822(posts[0].isodate) if posts else ""}</lastBuildDate>
        <atom:link href="{BASE_URL}/rss.xml" rel="self" type="application/rss+xml"/>
{items_xml}
    </channel>
</rss>"""


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
        "math": math_head("".join(sections.values()), ""),
    }

    index_template = assemble.read(src / "index.html")
    check_balance(index_template, "src/index.html")
    check_nav(index_template)
    # A section with no {slot} in the shell is built and then dropped
    # without a word; this is how Papers first went missing.
    expect_placeholders(index_template, [*sections, *aux], "src/index.html")
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
        raw_content["blog"], load_blog_entries())

    raw_content["about"] = parse_about(raw_content["about"], carousel_images(posts))

    assemble.write(root / "rss.xml", build_feed(posts))
    assemble.write(root / "index.html", build_index(raw_content))

    # The home page's sections are hash fragments, which are the same document
    # to a crawler and get one URL between them; the Sagitta pages are real
    # ones.
    assemble.sitemap([f"{BASE_URL}/", *sagitta_pages.build()],
                     root / "sitemap.xml")

if __name__ == "__main__":
    try:
        main()
    except BuildError as e:
        raise SystemExit(f"build failed: {e}")

