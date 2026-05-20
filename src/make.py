from pathlib import Path
from datetime import datetime, timezone
import rcssmin, rjsmin

BASE_URL = "https://haileyjay.net"

tabs = ["about", "cv", "teaching", "comics", "blog", "links", "printlab"]
src = Path("src")

raw_content = {key: (src / f"{key}.html").read_text() for key in tabs}

# ── Parse comics ─────────────────────────────────────────────
comics_html, comic_template, comic_data = raw_content["comics"].split("§")

def parse_comics(data, template):
    lines = [l for l in data.splitlines() if l.strip()]
    assert len(lines) % 3 == 0, f"Comic data has {len(lines)} lines, expected a multiple of 3"
    comics = []
    for i in range(0, len(lines), 3):
        src_file, alt, caption = lines[i], lines[i+1], lines[i+2]
        w,h = get_size(f"comics/{src_file}.webp")
        comics.append(template.format(src=f"comics/{src_file}.webp", alt=alt, caption=caption, w=w, h=h).strip())
    return "\n\n".join(comics)

raw_content["comics"] = comics_html.format(body=parse_comics(comic_data, comic_template))

# ── Parse blog ───────────────────────────────────────────────
blog_html, entry_template, entry_data = raw_content["blog"].split("§")

def parse_blog(data, index_template):
    raw_entries = [e.strip() for e in data.strip().split("---") if e.strip()]
    index_items   = []
    post_sections = []
    feed_entries  = []  # list of (slug, title, isodate, teaser, body)

    for raw in raw_entries:
        lines = raw.splitlines()

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

        index_items.append(
            index_template.format(slug=slug, date=date, title=title, teaser=teaser).strip()
        )

        post_sections.append(f'''<div class="blog-post" id="blog-{slug}" data-blog-entry="true">
    <a href="#blog" class="blog-back">&larr; All posts</a>
    <div class="blog-post-header">
        <h2 class="blog-post-title">{title}</h2>
        <p class="blog-post-date">{date}</p>
    </div>
    <div class="blog-post-body">
        {body}
    </div>
</div>''')

        feed_entries.append((slug, title, isodate, teaser, body))

    return "\n\n".join(index_items), "\n\n".join(post_sections), feed_entries

entries_html, posts_html, feed_entries = parse_blog(entry_data, entry_template)
raw_content["blog"] = blog_html.format(entries=entries_html, posts=posts_html)

# ── Generate RSS feed ─────────────────────────────────────────
def format_rfc2822(isodate):
    dt = datetime.strptime(isodate, "%Y-%m-%d").replace(tzinfo=timezone.utc)
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

Path("rss.xml").write_text(feed)

# ── Parse print lab ──────────────────────────────────────────
def parse_printlab(raw):
    parts = {}
    current_key = ""
    current_lines = []
    for line in raw.splitlines():
        if line.startswith("§") and line.endswith("§") and line != "§":
            parts[current_key] = "\n".join(current_lines).strip()
            current_key = line.strip("§").strip()
            current_lines = []
        else:
            current_lines.append(line)
    parts[current_key] = "\n".join(current_lines).strip()

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
    key: f'<section id="{key}"{about_fix.get(key,"")}>\n{raw_content[key]}\n</section>'
    for key in tabs
}


css_raw = Path("src/main.css").read_text()
js_raw  = Path("src/main.js").read_text()

aux = {
    "css": "<style>"  + rcssmin.cssmin(css_raw) + "</style>",
    "js" : "<script>" + rjsmin.jsmin(js_raw)   + "</script>",
}

index_template = (src / "index.html").read_text()
Path("index.html").write_text(index_template.format(**sections, **aux))