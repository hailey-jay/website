from PIL import Image
from pathlib import Path
from datetime import datetime, timezone
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

raw_content = {key: (src / f"{key}.html").read_text() for key in tabs}

def get_size(path):
    with Image.open(path) as im:
        return im.size

def split_sections(raw):
    """Split a partial on §NAME§ delimiter lines.

    The text before the first delimiter is keyed "" (the section's own
    markup); every §NAME§ line opens a named sub-template. Naming the
    pieces means adding one cannot silently shift the others."""
    parts   = {}
    key     = ""
    current = []
    for line in raw.splitlines():
        marker = line.strip()
        if marker.startswith("§") and marker.endswith("§") and marker.strip("§").strip():
            parts[key] = "\n".join(current).strip()
            key        = marker.strip("§").strip()
            current    = []
        else:
            current.append(line)
    parts[key] = "\n".join(current).strip()
    return parts

# ── Shared sub-templates ─────────────────────────────────────
# Markup used by more than one section. The gallery card is identical
# for comics and blog galleries apart from the thumb class, which picks
# which lightbox instance claims it (see makeLightbox in main.js).
shared_parts  = split_sections((src / "shared.html").read_text())
card_template = shared_parts["CARD"]

# ── Parse comics ─────────────────────────────────────────────
# Data lives in src/data/comics.txt: three lines per comic
# (filename stem, alt text, caption), blank lines ignored.
comic_parts    = split_sections(raw_content["comics"])
comics_html    = comic_parts[""]
comic_data     = (src / "data/comics.txt").read_text()

def parse_comics(data, template):
    lines = [l for l in data.splitlines() if l.strip()]
    assert len(lines) % 3 == 0, f"Comic data has {len(lines)} lines, expected a multiple of 3"
    comics = []
    for i in range(0, len(lines), 3):
        src_file, alt, caption = lines[i], lines[i+1], lines[i+2]
        path = f"comics/{src_file}.webp"
        w, h = get_size(root / path)
        comics.append(template.format(
            thumb_class = "comic-thumb",
            label       = "View comic",
            src         = path,
            alt         = escape(alt),
            caption     = escape(caption),
            dims        = f' width="{w}" height="{h}"',
        ).strip())
    return "\n\n".join(comics)

raw_content["comics"] = comics_html.format(body=parse_comics(comic_data, card_template))

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
GALLERY_RE = re.compile(r"^[ \t]*\[gallery\][ \t]*\n(.*?)^[ \t]*\[/gallery\][ \t]*$", re.M | re.S)
IMAGE_RE   = re.compile(r"^[ \t]*\[image[ \t]+(.+?)\][ \t]*$", re.M)

def build_image(row, slug, template):
    fields  = [f.strip() for f in row.split("|")]
    img     = fields[0]
    caption = fields[1] if len(fields) > 1 else ""
    alt     = fields[2] if len(fields) > 2 else caption
    if "/" not in img:
        img = f"images/blog/{slug}/{img}"
    if "." not in img.rsplit("/", 1)[-1]:
        img += ".webp"
    assert (root / img).exists(), f"Image {img} (post: {slug}) does not exist"
    w, h = get_size(root / img)
    return template.format(
        thumb_class = "gallery-thumb",
        label       = "View image",
        src         = img,
        alt         = escape(alt),
        caption     = escape(caption),
        dims        = f' width="{w}" height="{h}"',
    ).strip()

def build_gallery(rows, slug):
    cards = [build_image(line, slug, card_template) for line in rows.splitlines() if line.strip()]
    return grid_template.format(cards="\n  ".join(c.replace("\n", "\n  ") for c in cards)).strip()

def load_blog_entries():
    files = sorted((src / "data/blog").glob("*.html"), reverse=True)
    return [f.read_text() for f in files if not f.name.startswith("_")]

def parse_blog(raw_entries, index_template):
    index_items   = []
    post_sections = []
    feed_entries  = []  # list of (slug, title, isodate, teaser, body)

    for raw in raw_entries:
        lines = raw.strip().splitlines()

        meta = {}
        body_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "":
                continue
            if ":" in stripped and not stripped.startswith("<"):
                key, _, val = stripped.partition(":")
                meta[key.strip()] = val.strip()
                body_start = i + 1
            else:
                body_start = i
                break

        body = "\n".join(lines[body_start:]).strip()

        slug    = meta["slug"]
        date    = meta["date"]
        isodate = meta["isodate"]
        title   = meta["title"]
        teaser  = meta["teaser"]

        body = GALLERY_RE.sub(lambda m: build_gallery(m.group(1), slug), body)
        body = IMAGE_RE.sub(lambda m: build_image(m.group(1), slug, figure_template), body)

        img_match = re.search(r'<img[^>]+src="([^"]+)"', body)
        thumb = f'<img class="blog-entry-thumb" src="{img_match.group(1)}" alt="">' if img_match else ""

        index_items.append(
            index_template.format(slug=slug, date=date, title=title, teaser=teaser, thumb=thumb).strip()
        )

        post_sections.append(
            post_template.format(slug=slug, title=title, date=date, body=body).strip()
        )

        feed_entries.append((slug, title, isodate, teaser, body))

    return "\n\n".join(index_items), "\n\n".join(post_sections), feed_entries

entries_html, posts_html, feed_entries = parse_blog(load_blog_entries(), entry_template)
raw_content["blog"] = blog_html.format(entries=entries_html, posts=posts_html)

# ── Collect blog images for the homepage carousel ──────────────
blog_images = []
for slug, title, isodate, teaser, body in feed_entries:
    for img_src, alt in re.findall(r'<img[^>]+src="([^"]+)"[^>]*alt="([^"]*)"', body):
        blog_images.append({"src": img_src, "alt": alt, "slug": slug, "title": title})

raw_content["about"] = raw_content["about"].format(blog_images_json=json.dumps(blog_images))

# ── Generate RSS feed ─────────────────────────────────────────
def format_rfc2822(isodate):
    try:
        dt = datetime.strptime(isodate, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        dt = datetime.strptime(re.sub(r'(\d+)(st|nd|rd|th)', r'\1', isodate), "%B %d, %Y").replace(tzinfo=timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")

items_xml = ""
for slug, title, isodate, teaser, body in feed_entries:
    items_xml += f"""
    <item>
        <title>{title}</title>
        <link>{BASE_URL}/#blog-{slug}</link>
        <guid isPermaLink="true">{BASE_URL}/#blog-{slug}</guid>
        <pubDate>{format_rfc2822(isodate)}</pubDate>
        <description>{teaser}</description>
        <content:encoded><![CDATA[{body}]]></content:encoded>
    </item>"""

feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">
    <channel>
        <title>Hailey Jay Garcia</title>
        <link>{BASE_URL}/</link>
        <description>Math, teaching, and whatever else is on my mind.</description>
        <language>en-us</language>
        <atom:link href="{BASE_URL}/rss.xml" rel="self" type="application/rss+xml"/>
{items_xml}
    </channel>
</rss>"""

(root / "rss.xml").write_text(feed)

# ── Parse print lab ──────────────────────────────────────────
def parse_printlab(raw):
    parts = split_sections(raw)

    html_template     = parts[""]
    printer_template  = parts["PRINTER"]
    gallery_template  = parts["GALLERY"]
    filament_template = parts["FILAMENT"]
    filament_row_tmpl = parts["FILAMENT_ROW"]
    data_block        = parts["DATA"]

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
        printer_rows.append(printer_template.format(
            name         = p.get("name", ""),
            status       = status,
            status_label = status_labels.get(status, status.title()),
            note         = p.get("note", ""),
        ).strip())

    # ── Gallery ───────────────────────────────────────────────
    gallery_lines = [l for l in data_sections["GALLERY"].splitlines() if l.strip()]
    assert len(gallery_lines) % 3 == 0, "Gallery data must have lines in multiples of 3"
    gallery_cards = []
    for i in range(0, len(gallery_lines), 3):
        src_file, alt, caption = gallery_lines[i], gallery_lines[i+1], gallery_lines[i+2]
        gallery_cards.append(gallery_template.format(
            src     = src_file,
            alt     = alt,
            caption = caption,
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
            row_html.append(rtmpl.format(
                material = material,
                color    = color,
                hex      = hex_val,
                stock    = stock + " spools",
                blurb    = blurb_html,
            ).strip())
        return ftmpl.format(
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

    return html_template.format(
        printer_count = meta.get("printer_count", ""),
        printers      = "\n        ".join(printer_rows),
        gallery       = "\n\n".join(gallery_cards),
        filament      = "\n\n".join(filament_groups),
    )

raw_content["printlab"] = parse_printlab(raw_content["printlab"])

# ── Assemble index.html ──────────────────────────────────────

about_fix = {"about":' class="active"'}
sections = {
    key: "" if key in unpublished
    else f'<section id="{key}"{about_fix.get(key,"")}>\n{raw_content[key]}\n</section>'
    for key in tabs
}


css_raw = (src / "main.css").read_text()
js_raw  = (src / "main.js").read_text()

aux = {
    "css": "<style>"  + rcssmin.cssmin(css_raw) + "</style>",
    "js" : "<script>" + rjsmin.jsmin(js_raw)   + "</script>",
}

index_template = (src / "index.html").read_text()
html = index_template.format(**sections, **aux)
html = re.sub(r"<!--.*?-->", "", html, flags=re.S)  # comments (incl. blog drafts) stay out of prod
(root / "index.html").write_text(html)