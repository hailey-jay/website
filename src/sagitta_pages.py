"""The standalone Sagitta pages under /sagitta/.

Sagitta is not one of the tabs. The tabs are all facets of me and share one
document; Sagitta is a tool with its own navigation, its own app served from
/sagitta/app/, and a tutorial worth a URL someone can send, so it is built as
real files under a shell of its own (src/sagitta/). Those pages still inline
main.css and main.js, so the typography, the theme toggle, and the figure
lightbox are the site's and stay in step with it.

make.py calls `build()`, which writes the pages and returns their URLs for the
sitemap.
"""
from dataclasses import dataclass
from html import escape
import re

from common import (
    BASE_URL, expand_directives, front_matter, math_head,
    parse_row, photos, resolve_image, root, src,
)
from sitekit import assemble, minify
from sitekit.errors import need
from sitekit.markup import check_balance, require_listed
from sitekit.text import (
    expect_placeholders, indent, paragraphs, parse_fields, parse_kv,
    render, repeat, rows_of, split_data, split_sections, strip_comments,
)

SAGITTA_PARTIALS = ["shell.html", "landing.html", "tutorial.html"]

# Each partial's words live under src/data/sagitta/, named after it; the images
# both pages show (and the blog post about Sagitta borrows) share one folder.
SAGITTA_DATA   = src / "data/sagitta"
SAGITTA_IMAGES = "images/sagitta"

# Written by `make app` from the checkout's package.json, so the version the
# landing page states is the version of the editor it serves.
SAGITTA_VERSION = root / "sagitta/app/VERSION"

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

        One slot per nav entry that can be the current page, which is Home
        and the tutorial: the wordmark and the editor are not nav links."""
        return {f"current_{name}": ' aria-current="page"' if self.partial == partial else ""
                for name, partial in (("home", "landing"), ("tutorial", "tutorial"))}

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

def image_fields(row, base, sizes, prefix):
    """`{prefix}_attrs`, `{prefix}_alt`, and `{prefix}_caption` for one row."""
    img, caption, alt = parse_row(row)
    img = resolve_image(img, base)
    return {
        f"{prefix}_attrs":   photos.attrs(img, sizes),
        f"{prefix}_alt":     escape(alt),
        f"{prefix}_caption": escape(caption),
    }

# Hero is the full column; an example's figure sits in the left half of it.
HERO_SIZES = "(max-width: 640px) 100vw, 840px"
TRY_SIZES  = "(max-width: 640px) 100vw, 400px"

def kbd_keys(keys):
    """`SPC → SPC` as one <kbd> per whitespace-separated key."""
    return " ".join(f"<kbd>{escape(k, quote=False)}</kbd>" for k in keys.split())

def verbatim(text):
    """Escaped code for a <pre>, kept on one source line.

    build_standalone indents the whole body, and a literal newline inside a
    <pre> would carry that indent into what the reader sees; &#10; is a newline
    to the browser and not to indent()."""
    return escape(text.strip("\n"), quote=False).replace("\n", "&#10;")

def landing_data():
    """src/data/sagitta/landing.txt, split into its ---BLOCK---s."""
    # Read through assemble, so a note to self in an HTML comment is dropped
    # the way it is in a partial. This is the only comment syntax the data
    # files have, and a `#` would collide with the key named `#`.
    return split_data(assemble.read(SAGITTA_DATA / "landing.txt"))

def hero_row(data):
    return rows_of(data["HERO"])[0]

def sagitta_version():
    need(SAGITTA_VERSION.is_file(),
         f"{SAGITTA_VERSION.relative_to(root)} is missing; run `make app`")
    return "v" + SAGITTA_VERSION.read_text(encoding="utf-8").strip()

def og_image():
    """The off-site preview both Sagitta pages share: the landing page's hero.

    Absolute, since a preview is fetched from somewhere else."""
    img, _, alt = parse_row(hero_row(landing_data()))
    return {"og_image":     f"{BASE_URL}/{resolve_image(img, SAGITTA_IMAGES)}",
            "og_image_alt": escape(alt)}

def parse_landing(partial, page):
    """The landing page's body, from src/data/sagitta/landing.txt."""
    parts = split_sections(partial)
    data  = landing_data()
    head  = parse_kv(data[""], "sagitta landing",
                     ("title", "description", "tagline"))
    shots = f"{page.up}{SAGITTA_IMAGES}"

    try_head = parse_kv(data["TRY"], "sagitta TRY", ("lede", "output_caption"))
    examples = [parse_fields(row, 2) for row in rows_of(data["EXAMPLES"])]
    need(examples, "sagitta EXAMPLES: no examples")

    def slide(key, title):
        for block in (key, f"{key}_STEPS", f"{key}_OUTPUT"):
            need(block in data, f"sagitta EXAMPLES lists {key}, but ---{block}--- is missing")
        figure = parse_kv(data[key], f"sagitta {key}", ("image", "caption", "alt"))
        steps = repeat(parts["STEP"], [
            {"keys": kbd_keys(keys), "what": what}
            for keys, what in (parse_fields(row, 2) for row in rows_of(data[f"{key}_STEPS"]))
        ], sep="\n")
        row = " | ".join((figure["image"], figure["caption"], figure["alt"]))
        return {
            "id":             key.lower(),
            "title":          escape(title, quote=False),
            "steps":          indent(steps, "                "),
            "output":         verbatim(data[f"{key}_OUTPUT"]),
            "output_caption": try_head["output_caption"],
            **image_fields(row, shots, TRY_SIZES, "img"),
        }

    tabs = repeat(parts["TAB"], [
        {"index": i, "title": escape(title, quote=False)}
        for i, (_, title) in enumerate(examples)
    ], sep="\n")
    slides = repeat(parts["SLIDE"], [slide(key, title) for key, title in examples],
                    sep="\n")
    downloads = repeat(parts["DOWNLOAD"], [
        {"platform": platform, "package": package, "note": note, "url": url}
        for platform, package, note, url
        in (parse_fields(row, 4) for row in rows_of(data["DOWNLOADS"]))
    ], sep="\n")

    body = render(parts[""],
        tagline      = head["tagline"],
        version      = sagitta_version(),
        lede         = indent(paragraphs(data["LEDE"]), "        "),
        try_lede     = try_head["lede"],
        tabs         = indent(tabs, "            "),
        slides       = indent(slides, "            "),
        modes        = indent(paragraphs(data["MODES"]), "    "),
        downloads    = indent(downloads, "            "),
        install_note = paragraphs(data["INSTALL_NOTE"]),
        notes        = paragraphs(data["NOTES"]),
        base         = page.base,
        **image_fields(hero_row(data), shots, HERO_SIZES, "hero"),
    )
    return body, head["title"], head["description"]

def parse_tutorial(partial, page):
    """The walkthrough's body, from src/data/sagitta/tutorial.html.

    Front matter and [image ...] directives work as they do in a blog post;
    the images come from images/sagitta/ instead of a post folder, reached
    through the page's own ../ prefix."""
    raw = (SAGITTA_DATA / "tutorial.html").read_text(encoding="utf-8")
    meta, prose = front_matter(raw, "sagitta tutorial",
                               ("title", "standfirst", "description"))

    body = expand_directives(strip_comments(prose).strip(),
                             f"{page.up}{SAGITTA_IMAGES}", [])
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
    expect_placeholders(shell, ["main", "css", "js", "math", "og_image"],
                        "src/sagitta/shell.html")
    return assemble.fill(shell,
        main        = indent(body, "            "),
        title       = escape(title),
        description = escape(description),
        canonical   = page.url,
        **og_image(),
        up          = page.up,
        base        = page.base,
        math        = math_head(body, page.up),
        **page.nav_current,
        **page_assets(page),
    )

def build():
    """Write every Sagitta page; return the URLs the sitemap should list.

    The app is rsynced in rather than built, and is a page all the same."""
    # The partial list is hand-written, so a new src/sagitta/foo.html would
    # otherwise be built by nobody and noticed by no one.
    require_listed(src / "sagitta", "*.html", SAGITTA_PARTIALS, "src/sagitta")
    for page in sagitta_pages:
        assemble.write(root / page.out, build_standalone(page))
    return [*(p.url for p in sagitta_pages), APP_URL]
