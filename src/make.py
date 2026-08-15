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

def parse_row(row):
    """Split an `image | caption | alt` row.

    The caption fills the card title, the lightbox caption, and, absent
    a third field, the alt text."""
    fields  = [f.strip() for f in row.split("|")]
    img     = fields[0]
    caption = fields[1] if len(fields) > 1 else ""
    alt     = fields[2] if len(fields) > 2 else caption
    return img, caption, alt

# Prose uses a literal § for section numbers ("§7: Monday 13:30-14:20"),
# so the delimiter is matched strictly: a whole line, screaming case, no
# inner punctuation. Anything less and a line of copy could open a
# sub-template and silently truncate the section above it.
SECTION_RE = re.compile(r"^§([A-Z][A-Z0-9_]*)§$")

def split_sections(raw):
    """Split a partial on §NAME§ delimiter lines.

    The text before the first delimiter is keyed "" (the section's own
    markup); every §NAME§ line opens a named sub-template. Naming the
    pieces means adding one cannot silently shift the others."""
    parts   = {}
    key     = ""
    current = []
    for line in raw.splitlines():
        m = SECTION_RE.match(line.strip())
        if m:
            parts[key] = "\n".join(current).strip()
            key        = m.group(1)
            current    = []
        else:
            current.append(line)
    parts[key] = "\n".join(current).strip()
    return parts

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
    comics = []
    for line in data.splitlines():
        if not line.strip():
            continue
        stem, caption, alt = parse_row(line)
        path = f"comics/{stem}.webp"
        comics.append(render(template,
            thumb_class = "comic-thumb",
            label       = "View comic",
            src         = path,
            img_attrs   = img_attrs(path, GRID_SIZES),
            alt         = escape(alt),
            caption     = escape(caption),
        ).strip())
    return "\n\n".join(comics)

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
    cards = [build_image(line, slug, card_template, collected) for line in rows.splitlines() if line.strip()]
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
                       for line in m.group("rows").splitlines() if line.strip()]
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
    index_items   = []
    post_sections = []
    posts         = []

    for isodate, slug, raw in raw_entries:
        # Front matter is the leading key: value block, ended by a blank
        # line. An explicit terminator means a body whose first line
        # happens to contain a colon cannot be swallowed as metadata.
        head, sep, body = raw.strip().partition("\n\n")
        assert sep, f"Post {slug} has no blank line after its front matter"

        meta = {}
        for line in head.splitlines():
            key, colon, val = line.partition(":")
            assert colon, f"Front matter line in {slug} is not 'key: value': {line!r}"
            meta[key.strip()] = val.strip()

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
        thumb = (f'<img class="blog-entry-thumb" src="{post.images[0]["thumb"]}" alt="" '
                 f'width="56" height="56" loading="lazy" decoding="async">') if post.images else ""

        index_items.append(render(entry_template,
            slug=post.slug, date=post.date, title=post.title,
            teaser=post.teaser, thumb=thumb).strip())

        post_sections.append(render(post_template,
            slug=post.slug, title=post.title, date=post.date,
            body=post.body).strip())

        posts.append(post)

    return "\n\n".join(index_items), "\n\n".join(post_sections), posts

entries_html, posts_html, posts = parse_blog(load_blog_entries())
raw_content["blog"] = render(blog_html, entries=entries_html, posts=posts_html)

# ── Collect blog images for the homepage carousel ──────────────
blog_images = []
for post in posts:
    for image in post.images:
        blog_images.append({**image, "slug": post.slug, "title": post.title})

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
    data_block = data_file.read_text(encoding="utf-8")

    # ── Parse DATA block ──────────────────────────────────────
    data_sections = {}
    cur_sec = None
    cur_sec_lines = []
    for line in data_block.splitlines():
        if line.startswith("---") and line.endswith("---"):
            if cur_sec is not None:
                data_sections[cur_sec] = "\n".join(cur_sec_lines).strip()
            cur_sec = line.strip("-").strip()
            cur_sec_lines = []
        else:
            cur_sec_lines.append(line)
    if cur_sec is not None:
        data_sections[cur_sec] = "\n".join(cur_sec_lines).strip()

    # Meta (key: value lines before first ---)
    meta = {}
    for line in data_block.splitlines():
        if line.startswith("---"):
            break
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()

    # ── Printers ──────────────────────────────────────────────
    status_labels = {
        "idle":        "Idle",
        "printing":    "Printing",
        "offline":     "Offline",
        "maintenance": "Maintenance",
    }

    printer_blocks = [b.strip() for b in data_sections["PRINTERS"].split("\n\n") if b.strip()]
    printer_rows = []
    for block in printer_blocks:
        p = {}
        for line in block.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                p[k.strip()] = v.strip()
        status = p.get("status", "offline")
        printer_rows.append(render(printer_template,
            name         = p.get("name", ""),
            status       = status,
            status_label = status_labels.get(status, status.title()),
            note         = p.get("note", ""),
        ).strip())

    # ── Gallery ───────────────────────────────────────────────
    # Same `image | caption | alt` rows and same shared card as the
    # comics and blog galleries; only the aria-label verb differs.
    gallery_cards = []
    for line in data_sections["GALLERY"].splitlines():
        if not line.strip():
            continue
        img, caption, alt = parse_row(line)
        assert (root / img).exists(), f"Print gallery image {img} does not exist"
        gallery_cards.append(render(card_template,
            thumb_class = "gallery-thumb",
            label       = "View print",
            src         = img,
            img_attrs   = img_attrs(img, GRID_SIZES),
            alt         = escape(alt),
            caption     = escape(caption),
        ).strip())

    # ── Filament ──────────────────────────────────────────────
    filament_groups = []
    current_diameter = None
    current_rows = []

    def flush_group(diameter, rows, ftmpl, rtmpl):
        if not diameter or not rows:
            return ""
        row_html = []
        for r in rows:
            fields = [f.strip() for f in r.split("|")]
            material = fields[0]
            color    = fields[1]
            hex_val  = fields[2]
            stock    = fields[3]
            blurb    = fields[4] if len(fields) > 4 else ""
            blurb_html = f'<span class="filament-blurb">({blurb})</span>' if blurb else ""
            row_html.append(render(rtmpl,
                material = material,
                color    = color,
                hex      = hex_val,
                stock    = stock + " spools",
                blurb    = blurb_html,
            ).strip())
        return render(ftmpl,
            diameter = diameter,
            rows     = "\n            ".join(row_html),
        ).strip()

    for line in data_sections["FILAMENT"].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.endswith("mm") and "|" not in stripped:
            if current_diameter:
                filament_groups.append(flush_group(current_diameter, current_rows, filament_template, filament_row_tmpl))
            current_diameter = stripped
            current_rows = []
        else:
            current_rows.append(stripped)
    if current_diameter:
        filament_groups.append(flush_group(current_diameter, current_rows, filament_template, filament_row_tmpl))

    return render(html_template,
        printer_count = meta.get("printer_count", ""),
        printers      = "\n        ".join(printer_rows),
        gallery       = "\n\n".join(gallery_cards),
        filament      = "\n\n".join(filament_groups),
    )

if "printlab" not in unpublished:
    raw_content["printlab"] = parse_printlab(raw_content["printlab"])

# ── Assemble index.html ──────────────────────────────────────

def wrap_section(key):
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