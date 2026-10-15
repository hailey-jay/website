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

from sitekit import assemble, minify
from sitekit.errors import BuildError, need
from sitekit.images import Pipeline, mirrored
from sitekit.markup import check_balance, require_listed
from sitekit.text import (
    expect_placeholders, indent, paragraphs, parse_fields, parse_kv,
    render, repeat, rows_of, split_data, split_sections, strip_comments,
)

BASE_URL = "https://haileyjay.net"

tabs = ["about", "cv", "papers", "teaching", "comics", "blog", "colophon"]
unpublished = set()  # built, but emitted as an empty section

# Sagitta is not one of the tabs. The tabs are all facets of me and share one
# document; Sagitta is a tool with its own navigation, its own app served from
# /sagitta/app/, and a tutorial worth a URL someone can send, so it is built as
# real files under a shell of its own (src/sagitta/). Those pages still inline
# main.css and main.js, so the typography, the theme toggle, and the figure
# lightbox are the site's and stay in step with it.
SAGITTA_PARTIALS = ["shell.html", "landing.html", "tutorial.html"]

# The one off-site preview image the Sagitta pages share.
OG_IMAGE = f"{BASE_URL}/images/sagitta-tutorial/complete.png"

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

def build_gallery(rows, base, collected, card_tmpl, grid_tmpl):
    cards = [build_image(line, base, card_tmpl, collected) for line in rows_of(rows)]
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
    base = f"images/blog/{slug}"

    def expand(m):
        if m.group("rows") is not None:
            figures = [build_image(line, base, FEED_FIGURE, throwaway)
                       for line in rows_of(m.group("rows"))]
            return "\n".join(figures)
        return build_image(m.group("row"), base, FEED_FIGURE, throwaway)

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
        def expand(m, post=post, base=f"images/blog/{slug}"):
            if m.group("rows") is not None:
                return build_gallery(m.group("rows"), base, post.images,
                                     card_tmpl, grid_template)
            return build_image(m.group("row"), base, figure_template, post.images, FIGURE_SIZES)

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
        <description>Combinatorics, topology, comics, and whatever else is on my mind.</description>
        <language>en-us</language>
        <lastBuildDate>{format_rfc2822(posts[0].isodate) if posts else ""}</lastBuildDate>
        <atom:link href="{BASE_URL}/rss.xml" rel="self" type="application/rss+xml"/>
{items_xml}
    </channel>
</rss>"""

# ── Standalone pages ─────────────────────────────────────────
# A page group under its own directory. `up` is the prefix from the written
# file back to the site root, `base` the prefix back to the group's own
# directory; the shell and the partials carry both, so moving a page one level
# deeper does not mean hand-editing every asset path in it.
@dataclass
class Page:
    out:     str   # repo-relative path of the written file
    partial: str   # src/sagitta/<partial>.html

    @property
    def nav_current(self):
        """` aria-current="page"` for the nav link that points at this page.

        One slot per nav entry that can be the current page, which is the
        tutorial alone: the wordmark and the editor are not nav links."""
        return {"current_tutorial":
                ' aria-current="page"' if self.partial == "tutorial" else ""}

    @property
    def url(self):
        """Canonical URL: the directory, since the file is its index."""
        return f"{BASE_URL}/{self.out[:-len('index.html')]}"

    @property
    def up(self):
        return "../" * self.out.count("/")

    @property
    def base(self):
        # "./" rather than "" at the group root, so a link to the group's own
        # index is href="./" and not an empty href.
        return "../" * (self.out.count("/") - 1) or "./"


sagitta_pages = [
    Page("sagitta/index.html", "landing"),
    Page("sagitta/tutorial/index.html", "tutorial"),
]

# The app is rsynced in from the Sagitta repo by `make app`, not built here,
# but it is a real URL and belongs in the sitemap with the rest.
APP_URL = f"{BASE_URL}/sagitta/app/"

# A relative url() in the stylesheet resolves against the document, so the
# fonts are at fonts/ for the root page and ../fonts/ one directory down. The
# stylesheet is inlined, so there is no stylesheet URL to resolve against and
# nothing else fixes this.
CSS_URL_RE = re.compile(r"""url\(\s*(['"]?)(?!https?:|data:|/|\#)""")

def relocate_css(css, up):
    return CSS_URL_RE.sub(lambda m: f"url({m.group(1)}{up}", css)

def page_assets(page):
    """The inline <style> and <script> for a standalone page.

    main.css first and the page's own sheet after it, in one block, so the
    cascade order is the file order."""
    css = (assemble.concat(src, ["main.css"]) + "\n"
           + assemble.concat(src / "sagitta", ["sagitta.css"]))
    return {
        "css": "<style>" + minify.css(relocate_css(css, page.up)) + "</style>",
        "js":  assemble.js_block(src, ["main.js"]),
    }

def image_fields(row, base, sizes, prefix, eager=False):
    """`{prefix}_attrs`, `{prefix}_alt`, and `{prefix}_caption` for one row."""
    img, caption, alt = parse_row(row)
    img = resolve_image(img, base)
    return {
        f"{prefix}_attrs":   photos.attrs(img, sizes),
        f"{prefix}_alt":     escape(alt),
        f"{prefix}_caption": escape(caption),
    }

# Hero is the full column; the key figure sits beside the table at half of it.
HERO_SIZES = "(max-width: 640px) 100vw, 840px"
KEYS_SIZES = "(max-width: 640px) 100vw, 400px"

def parse_landing(partial, page):
    """The landing page's body, from src/data/sagitta.txt."""
    parts = split_sections(partial)
    # Read through assemble, so a note to self in an HTML comment is dropped
    # the way it is in a partial. This is the only comment syntax the data
    # files have, and a `#` would collide with the key named `#`.
    data  = split_data(assemble.read(src / "data/sagitta.txt"))
    head  = parse_kv(data[""], "sagitta",
                     ("title", "description", "tagline", "version"))
    shots = f"{page.up}images/sagitta-tutorial"

    keys_figure = parse_kv(data["KEYS_FIGURE"], "sagitta KEYS_FIGURE",
                           ("lede", "image", "caption", "alt"))
    keys_row = " | ".join((keys_figure["image"], keys_figure["caption"],
                           keys_figure["alt"]))

    features = repeat(parts["FEATURE"], [
        {"title": title, "body": body}
        for title, body in (parse_fields(row, 2) for row in rows_of(data["FEATURES"]))
    ])
    keys = repeat(parts["KEYROW"], [
        {"key": key, "what": what}
        for key, what in (parse_fields(row, 2) for row in rows_of(data["KEYS"]))
    ], sep="\n")
    downloads = repeat(parts["DOWNLOAD"], [
        {"platform": platform, "package": package, "note": note, "url": url}
        for platform, package, note, url
        in (parse_fields(row, 4) for row in rows_of(data["DOWNLOADS"]))
    ], sep="\n")

    body = render(parts[""],
        tagline      = head["tagline"],
        version      = head["version"],
        lede         = paragraphs(data["LEDE"]),
        features     = indent(features, "        "),
        keys_lede    = escape(keys_figure["lede"], quote=False),
        keys         = indent(keys, "                "),
        downloads    = indent(downloads, "            "),
        install_note = paragraphs(data["INSTALL_NOTE"]),
        notes        = paragraphs(data["NOTES"]),
        base         = page.base,
        **image_fields(rows_of(data["HERO"])[0], shots, HERO_SIZES, "hero"),
        **image_fields(keys_row, shots, KEYS_SIZES, "keys"),
    )
    return body, head["title"], head["description"]

def parse_tutorial(partial, page):
    """The walkthrough's body, from src/data/sagitta-tutorial.html.

    Front matter and [image ...] directives work as they do in a blog post;
    the images come from images/sagitta-tutorial/ instead of a post folder,
    reached through the page's own ../ prefix."""
    raw = (src / "data/sagitta-tutorial.html").read_text(encoding="utf-8")
    head, sep, prose = raw.strip().partition("\n\n")
    need(sep, "sagitta-tutorial has no blank line after its front matter")
    meta = parse_kv(head, "sagitta-tutorial front matter",
                    ("title", "standfirst", "description"))

    parts     = split_sections(assemble.read(src / "blog.html"))
    collected = []
    base      = f"{page.up}images/sagitta-tutorial"

    def expand(m):
        if m.group("rows") is not None:
            return build_gallery(m.group("rows"), base, collected,
                                 load_shared()["CARD"], parts["GRID"])
        return build_image(m.group("row"), base, parts["FIGURE"], collected,
                           FIGURE_SIZES)

    body = DIRECTIVE_RE.sub(expand, strip_comments(prose).strip())
    rendered = render(partial, title=escape(meta["title"], quote=False),
                      standfirst=escape(meta["standfirst"], quote=False),
                      body=indent(body, "        "), base=page.base)
    return rendered, f"{meta['title']} · Sagitta", meta["description"]

BUILDERS = {"landing": parse_landing, "tutorial": parse_tutorial}

def build_standalone(page):
    """One standalone page, shell and all, ready to write."""
    partial = assemble.read(src / f"sagitta/{page.partial}.html")
    body, title, description = BUILDERS[page.partial](partial, page)
    check_balance(body, f"src/sagitta/{page.partial}.html")

    shell = assemble.read(src / "sagitta/shell.html")
    check_balance(shell, "src/sagitta/shell.html")
    # The title, the description, and the canonical URL each appear twice (the
    # document head and the Open Graph block), so only the one-shot slots -
    # the ones whose silent absence would drop a whole page or bundle - are
    # checked here.
    expect_placeholders(shell, ["main", "css", "js", "og_image"],
                        "src/sagitta/shell.html")
    return assemble.fill(shell,
        main        = indent(body, "            "),
        title       = escape(title),
        description = escape(description),
        canonical   = page.url,
        og_image    = OG_IMAGE,
        up          = page.up,
        base        = page.base,
        **page.nav_current,
        **page_assets(page),
    )


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
    require_listed(src / "sagitta", "*.html", SAGITTA_PARTIALS, "src/sagitta")

    raw_content   = load_partials()
    card_template = load_shared()["CARD"]

    raw_content["comics"] = parse_comics(raw_content["comics"], card_template)

    raw_content["blog"], posts = parse_blog(
        raw_content["blog"], load_blog_entries(), card_template)

    raw_content["about"] = parse_about(raw_content["about"], carousel_images(posts))

    assemble.write(root / "rss.xml", build_feed(posts))
    assemble.write(root / "index.html", build_index(raw_content))

    for page in sagitta_pages:
        assemble.write(root / page.out, build_standalone(page))

    # The home page's sections are hash fragments, which are the same document
    # to a crawler and get one URL between them; the Sagitta pages are real
    # ones. The app is rsynced in rather than built, and is a page all the same.
    assemble.sitemap([f"{BASE_URL}/", *(p.url for p in sagitta_pages), APP_URL],
                     root / "sitemap.xml")

if __name__ == "__main__":
    try:
        main()
    except BuildError as e:
        raise SystemExit(f"build failed: {e}")
