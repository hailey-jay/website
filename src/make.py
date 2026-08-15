from PIL import Image
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
import rcssmin, rjsmin
import re
import json
from html import escape

BASE_URL = "https://haileyjay.net"

tabs = ["about", "cv", "teaching", "comics", "blog", "links", "printlab"]
unpublished = {"printlab", "links"}  # still built, but emitted as an empty section

# Everything is anchored to the repo root rather than the working directory,
# so the script can be run from anywhere.
root = Path(__file__).resolve().parent.parent
src = root / "src"

COMMENT_RE = re.compile(r"<!--.*?-->", re.S)

def strip_comments(markup):
    """Drop HTML comments, including commented-out blog drafts.

    Applied to each partial as it is read, before the minified CSS and
    JS are inlined, so a --> inside a script or style string is never
    seen by this regex."""
    return COMMENT_RE.sub("", markup)

raw_content = {key: strip_comments((src / f"{key}.html").read_text(encoding="utf-8")) for key in tabs}

def get_size(path):
    with Image.open(path) as im:
        return im.size

# ── Thumbnails ───────────────────────────────────────────────
# Gallery originals are 1024-1600px but are displayed at ~200px in a
# grid and capped at 640px in the lightbox, so the grid was pulling
# half-megabyte photos to fill a thumbnail. A downscaled copy is
# generated per image and offered first; the original stays in the
# srcset for wide viewports and remains what the lightbox opens.
THUMB_WIDTH = 640
thumb_dir = root / "images/thumbs"

def thumb_for(path):
    """Return (relative path, width, height) of `path`'s thumbnail.

    Images already at or under THUMB_WIDTH are their own thumbnail.
    Regenerated only when the source is newer, so repeat builds are
    cheap and the output stays byte-stable."""
    src_file = root / path
    w, h = get_size(src_file)
    if w <= THUMB_WIDTH:
        return path, w, h

    # Mirror the source tree under images/thumbs/, minus a leading
    # "images/" so blog photos land at images/thumbs/blog/... rather
    # than images/thumbs/images/blog/...
    stem = path.rsplit(".", 1)[0]
    if stem.startswith("images/"):
        stem = stem[len("images/"):]
    out_rel = f"images/thumbs/{stem}.webp"
    out_file = root / out_rel
    tw = THUMB_WIDTH
    th = round(h * THUMB_WIDTH / w)

    if not out_file.exists() or out_file.stat().st_mtime < src_file.stat().st_mtime:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src_file) as im:
            im.resize((tw, th), Image.LANCZOS).save(out_file, "WEBP", quality=82, method=6)
    return out_rel, tw, th

def img_attrs(path, sizes):
    """src/srcset/sizes/width/height for a gallery image."""
    w, h = get_size(root / path)
    thumb, tw, _ = thumb_for(path)
    if thumb == path:
        return f'src="{path}" width="{w}" height="{h}"'
    return (f'src="{thumb}" srcset="{thumb} {tw}w, {path} {w}w" '
            f'sizes="{sizes}" width="{w}" height="{h}"')

# Grid cards sit in a ~640px main column at three-up, and go roughly
# half-width once the sidebar collapses.
GRID_SIZES   = "(max-width: 640px) 45vw, 210px"
FIGURE_SIZES = "(max-width: 480px) 100vw, 420px"

# ── Markup validation ────────────────────────────────────────
# An unclosed tag is invisible in the built page (the parser closes
# it for you, usually in the wrong place) but corrupts the RSS body
# and swallows following prose into a link. Cheaper to catch here.
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr"}
TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>")

def check_balance(markup, label):
    """Assert that every non-void element in `markup` is closed, in order."""
    stack = []
    for closing, name, self_closing in TAG_RE.findall(markup):
        name = name.lower()
        if name in VOID or self_closing:
            continue
        if not closing:
            stack.append(name)
        else:
            assert stack, f"{label}: stray </{name}>"
            assert stack[-1] == name, \
                f"{label}: </{name}> closes <{stack[-1]}>"
            stack.pop()
    assert not stack, f"{label}: unclosed <{stack[-1]}>"

PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

def render(template, **fields):
    """Substitute {name} placeholders in a template.

    Unlike str.format, a literal brace needs no escaping and an
    unrecognised {name} is left alone, so a partial can carry inline
    JS or CSS verbatim. Values are inserted as-is; escape before
    passing anything that needs it."""
    return PLACEHOLDER_RE.sub(
        lambda m: str(fields[m.group(1)]) if m.group(1) in fields else m.group(0),
        template,
    )

def repeat(template, records, sep="\n\n", **common):
    """Render `template` once per record dict, joined by `sep`.

    `common` supplies the fields every copy shares; a record may
    override them. Empty renders are dropped, so a record that expands
    to nothing leaves no blank gap behind."""
    out = [render(template, **{**common, **record}).strip() for record in records]
    return sep.join(chunk for chunk in out if chunk)

# ── Content formats ──────────────────────────────────────────
# Four shapes cover every section: delimited blocks, `key: value`
# fields, blank-line-separated records of those fields, and pipe rows.
# They are defined once here and shared, so a section's data file reads
# the same whichever section it belongs to.

def split_on(text, pattern):
    """Split `text` on whole-line delimiters matching `pattern`.

    The text before the first delimiter is keyed ""; each delimiter's
    captured name keys the block that follows it. Naming the pieces
    means adding one cannot silently shift the others."""
    parts   = {}
    key     = ""
    current = []
    for line in text.splitlines():
        m = pattern.match(line.strip())
        if m:
            parts[key] = "\n".join(current).strip()
            key        = m.group(1)
            current    = []
        else:
            current.append(line)
    parts[key] = "\n".join(current).strip()
    return parts

# Markup uses §NAME§, data files use ---NAME---. Both are matched
# strictly: a whole line, screaming case, nothing else. Prose contains a
# literal § for section numbers ("§7: Monday 13:30-14:20"), and a loose
# match would let a line of copy open a sub-template and silently
# truncate the section above it.
SECTION_RE = re.compile(r"^§([A-Z][A-Z0-9_]*)§$")
DATA_RE    = re.compile(r"^-{3}([A-Z][A-Z0-9_]*)-{3}$")

def split_sections(raw):
    """Split a partial into its markup and its §NAME§ sub-templates."""
    return split_on(raw, SECTION_RE)

def split_data(raw):
    """Split a data file into its ---NAME--- blocks."""
    return split_on(raw, DATA_RE)

def parse_kv(text, label, required=()):
    """Parse a block of `key: value` lines into a dict."""
    fields = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, colon, val = line.partition(":")
        assert colon, f"{label}: line is not 'key: value': {line!r}"
        fields[key.strip()] = val.strip()
    missing = [k for k in required if k not in fields]
    assert not missing, f"{label}: missing {', '.join(missing)}"
    return fields

def parse_records(text, label, required=()):
    """Parse blank-line-separated `key: value` blocks into a list of dicts."""
    return [parse_kv(block, label, required)
            for block in re.split(r"\n[ \t]*\n", text) if block.strip()]

def parse_fields(row, count=None):
    """Split a `a | b | c` row, padding to `count` with empty strings."""
    fields = [f.strip() for f in row.split("|")]
    if count is not None:
        assert len(fields) <= count, \
            f"Row has {len(fields)} fields, expected at most {count}: {row!r}"
        fields += [""] * (count - len(fields))
    return fields

def rows_of(text):
    """Yield the non-blank lines of a block of pipe rows."""
    return [line for line in text.splitlines() if line.strip()]

def group_rows(text, label):
    """Group pipe rows under bare heading lines.

    A line with no `|` opens a group and every row after it belongs to
    that group, which is how the filament table gets its diameters and
    the links list its categories."""
    groups  = []
    current = None
    for line in rows_of(text):
        line = line.strip()
        if "|" not in line:
            current = (line, [])
            groups.append(current)
        else:
            assert current, f"{label}: row before any heading: {line!r}"
            current[1].append(line)
    return groups

def indent(text, pad):
    """Indent every line of `text` after the first by `pad`.

    Templates place their own first line, so only the continuations
    need padding to line up under it."""
    return text.replace("\n", "\n" + pad)

def paragraphs(text, template="<p>{body}</p>"):
    """Wrap blank-line-separated prose in `template`.

    Lets a data file hold body copy without the <p> boilerplate, while
    still allowing inline markup (a link, an <em>) inside a paragraph.
    Lines within one paragraph are joined, so prose can be wrapped to a
    comfortable width in the source."""
    blocks = [b.strip() for b in re.split(r"\n[ \t]*\n", text) if b.strip()]
    return "\n\n".join(
        render(template, body=" ".join(line.strip() for line in b.splitlines()))
        for b in blocks
    )

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
shared_parts  = split_sections(strip_comments((src / "shared.html").read_text(encoding="utf-8")))
card_template = shared_parts["CARD"]

# ── Parse comics ─────────────────────────────────────────────
# Data lives in src/data/comics.txt: one `stem | caption | alt` row per
# comic, the same row format the blog uses. Blank lines are ignored.
comic_parts    = split_sections(raw_content["comics"])
comics_html    = comic_parts[""]
comic_data     = (src / "data/comics.txt").read_text(encoding="utf-8")

def parse_comics(data, template):
    records = []
    for line in rows_of(data):
        stem, caption, alt = parse_row(line)
        path = f"comics/{stem}.webp"
        records.append({
            "src":       path,
            "img_attrs": img_attrs(path, GRID_SIZES),
            "alt":       escape(alt),
            "caption":   escape(caption),
        })
    return repeat(template, records,
                  thumb_class="comic-thumb", label="View comic")

raw_content["comics"] = render(comics_html, body=parse_comics(comic_data, card_template))

# ── Parse blog ───────────────────────────────────────────────
# One file per post under src/data/blog/, named <isodate>-<slug>.html:
# key: value meta lines, then the HTML body. Filename sort gives
# newest-first order; an underscore prefix marks a draft (skipped).
blog_parts      = split_sections(raw_content["blog"])
blog_html       = blog_parts[""]
entry_template  = blog_parts["ENTRY"]
post_template   = blog_parts["POST"]
grid_template   = blog_parts["GRID"]
figure_template = blog_parts["FIGURE"]

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
    assert (root / img).exists(), f"Image {img} (post: {slug}) does not exist"
    w, h = get_size(root / img)
    # Recorded as raw text, in DOM order. The carousel assigns these to
    # img.alt as a property, so they must not be HTML-escaped. The
    # carousel wants the thumbnail; the lightbox wants the original.
    thumb, _, _ = thumb_for(img)
    collected.append({"src": img, "thumb": thumb, "alt": alt})
    return render(template,
        thumb_class = "gallery-thumb",
        label       = "View image",
        src         = img,
        img_attrs   = img_attrs(img, sizes or GRID_SIZES),
        alt         = escape(alt),
        caption     = escape(caption),
        dims        = f' width="{w}" height="{h}"',
    ).strip()

def build_gallery(rows, slug, collected):
    cards = [build_image(line, slug, card_template, collected) for line in rows_of(rows)]
    return render(grid_template, cards="\n  ".join(c.replace("\n", "\n  ") for c in cards)).strip()

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
        assert m, f"Post {f.name} is not named <isodate>-<slug>.html"
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

def parse_blog(raw_entries):
    posts = []

    for isodate, slug, raw in raw_entries:
        # Front matter is the leading key: value block, ended by a blank
        # line. An explicit terminator means a body whose first line
        # happens to contain a colon cannot be swallowed as metadata.
        head, sep, body = raw.strip().partition("\n\n")
        assert sep, f"Post {slug} has no blank line after its front matter"

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
                return build_gallery(m.group("rows"), post.slug, post.images)
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
    return entries, sections, posts

entries_html, posts_html, posts = parse_blog(load_blog_entries())
raw_content["blog"] = render(blog_html, entries=entries_html, posts=posts_html)

# ── Collect blog images for the homepage carousel ──────────────
blog_images = []
for post in posts:
    for image in post.images:
        blog_images.append({**image, "slug": post.slug, "title": post.title})

# ── Parse about ──────────────────────────────────────────────
# Everything the page says lives in src/data/about.txt: the identity
# fields, the labelled meta pairs, the bio prose, and the Lately note.
# The partial is left holding only the shape.
def parse_about(raw):
    parts    = split_sections(raw)
    data     = split_data((src / "data/about.txt").read_text(encoding="utf-8"))
    identity = parse_kv(data[""], "about",
                        ("name", "pronouns", "splash", "photo_alt", "photo_caption"))

    meta = repeat(parts["META_ROW"], [
        {"label": label, "value": value}
        for label, value in (parse_fields(row, 2) for row in rows_of(data["META"]))
    ], sep="\n")

    return render(parts[""], **identity,
        meta   = indent(meta, "    "),
        bio    = paragraphs(data["BIO"]),
        lately = data["LATELY"],
    )

raw_content["about"] = parse_about(raw_content["about"])
raw_content["about"] = render(raw_content["about"], blog_images_json=json.dumps(blog_images))

# ── Generate RSS feed ─────────────────────────────────────────
def format_rfc2822(isodate):
    dt = datetime.strptime(isodate, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")

def cdata(text):
    """Wrap text in CDATA, splitting any literal ]]> that would close it early."""
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"

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

feed = f"""<?xml version="1.0" encoding="UTF-8"?>
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

(root / "rss.xml").write_text(feed, encoding="utf-8")

# ── Parse print lab ──────────────────────────────────────────
def parse_printlab(raw):
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
    assert data_file.exists(), \
        "src/data/printlab.txt is missing; printlab cannot be published without it"
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
        assert (root / img).exists(), f"Print gallery image {img} does not exist"
        gallery_records.append({
            "src":       img,
            "img_attrs": img_attrs(img, GRID_SIZES),
            "alt":       escape(alt),
            "caption":   escape(caption),
        })
    gallery_cards = repeat(card_template, gallery_records,
                           thumb_class="gallery-thumb", label="View print")

    # ── Filament ──────────────────────────────────────────────
    # Rows are grouped under bare diameter headings ("1.75mm"), so a
    # heading is any non-row line; everything else is a filament row.
    groups  = []
    current = None
    for line in rows_of(data["FILAMENT"]):
        line = line.strip()
        if "|" not in line:
            current = (line, [])
            groups.append(current)
            continue
        assert current, f"Filament row before any diameter heading: {line!r}"
        material, color, hex_val, stock, blurb = parse_fields(line, 5)
        current[1].append({
            "material": material,
            "color":    color,
            "hex":      hex_val,
            "stock":    f"{stock} spools",
            "blurb":    f'<span class="filament-blurb">({blurb})</span>' if blurb else "",
        })

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

if "printlab" not in unpublished:
    raw_content["printlab"] = parse_printlab(raw_content["printlab"])

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
            assert key in parts, f"links: no §{key}§ template for {label!r}"
            links.append(render(parts[key], label=label, url=url).strip())
        groups.append({"title": title, "links": indent("\n".join(links), "        ")})

    return render(parts[""], groups=repeat(parts["GROUP"], groups))

if "links" not in unpublished:
    raw_content["links"] = parse_links(raw_content["links"])

# ── Assemble index.html ──────────────────────────────────────

def wrap_section(key):
    # Checked here rather than at read time: a partial is only whole
    # once its sub-templates have been filled, and this is also where a
    # data file's inline markup (a bio paragraph's link, a meta value)
    # first meets the page.
    check_balance(raw_content[key], f"Section {key}")
    active = ' class="active"' if key == "about" else ""
    return f'<section id="{key}"{active}>\n{raw_content[key]}\n</section>'

sections = {key: "" if key in unpublished else wrap_section(key) for key in tabs}


css_raw = (src / "main.css").read_text(encoding="utf-8")
js_raw  = (src / "main.js").read_text(encoding="utf-8")

aux = {
    "css": "<style>"  + rcssmin.cssmin(css_raw) + "</style>",
    "js" : "<script>" + rjsmin.jsmin(js_raw)   + "</script>",
}

index_template = strip_comments((src / "index.html").read_text(encoding="utf-8"))
check_balance(index_template, "src/index.html")
html = render(index_template, **sections, **aux)
(root / "index.html").write_text(html, encoding="utf-8")