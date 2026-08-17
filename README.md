# haileyjay.net
Source for my personal website.
Built with a small Python script.

## Structure
+ `src/`: source files (HTML partials, CSS, JS, build script)
+ `src/shared.html`: sub-templates used by more than one section (currently the gallery card)
+ `src/data/`: content data, kept separate from markup
  + `about.txt`: the identity fields, meta pairs, bio, and Lately note
  + `comics.txt`: one `stem | caption | alt` row per comic
  + `links.txt`: a bare heading line, then `label | url` rows under it
  + `blog/<isodate>-<slug>.html`: one file per post.
    Filename sort gives newest-first order.
    An underscore prefix (`_2026-...`) marks a draft; drafts are skipped by the build.

The date and slug come from the filename, so the front matter is just a title and teaser, ended by a blank line:

```
title: Haverford BSM REU
teaser: Public transit? What's that?

<p>Hey yall!</p>
```

A post body can use a gallery block instead of hand-written card markup:

```
[gallery]
hilles      | Hilles Hall
path        | The gravel path | alt text, only if it should differ from the caption
[/gallery]
```

A single image set inline in the prose uses the same row format on one line:

```
[image mordor | A passthrough between buildings, apparently dubbed Mordor]
```

One image per line, `image | caption | alt`, the same row format `comics.txt` and the print gallery use.
A bare stem resolves to `images/blog/<slug>/<stem>.webp`; anything with a slash is used as the path as-is.
The caption fills the card title or figcaption, the lightbox caption, and (absent a third field) the alt text.
The build reads each image's dimensions and emits them, so images reserve their space before they load.
The build fails if an image is missing.

Both forms open the lightbox, and the prev/next sequence is scoped to the post, so a post's gallery and its inline figures scroll together in DOM order.

Anything wider than 640px also gets a 640px thumbnail written to `images/thumbs/`, mirroring the source path minus the leading `images/`.
The thumbnail is what the grid, the blog index, and the homepage carousel load; the original stays in the `srcset` for wide viewports and is what the lightbox opens.
Thumbnails are rebuilt only when the source is newer, so a no-op build is fast.
They are committed alongside the other built output.

+ `src/make.py`: builds `index.html`, `rss.xml`, and `images/thumbs/` from the source files
+ `src/formats.py`: the shared text helpers: data-format parsing, template filling, and markup checking.
  Pure text in, pure text out: nothing in it knows which section it is serving, reads a file, or touches an image.
+ `src/images.py`: image measurement and thumbnail generation, the only part of the build that opens an image and so the only part that needs Pillow.
+ `index.html`, `rss.xml`, `images/thumbs/`: built output

## Data formats
Four shapes cover every section, and they are parsed by shared helpers in `formats.py` rather than per-section code:

+ `---NAME---` on its own line splits a data file into blocks (`split_data`).
  Screaming case only, so a line of prose cannot open one.
  Markup uses `§NAME§` for the same job (`split_sections`).
+ `key: value` lines are fields (`parse_kv`).
  A line with no colon is an error, as is a missing required field.
+ Blank-line-separated groups of those are records (`parse_records`), used for the printer list.
+ `a | b | c` lines are rows (`parse_fields`).
  Too many fields is an error.
  A bare line with no `|` opens a group, and the rows under it belong to it (`group_rows`), which is how the filament table gets its diameters and the links list its categories.

Prose in a data file needs no `<p>` wrap: blank-line-separated blocks are wrapped by the build, and a block may be soft-wrapped across lines.
Inline markup inside a paragraph (a link, an `<em>`) is passed through as written.

## Templates
Partials are split on `§NAME§` marker lines, and `{name}` placeholders are filled by `render()` in `formats.py`.
Braces that are not a known placeholder are left alone, so a partial can contain inline CSS or JS verbatim.

Every emitted section is checked for unclosed tags before it is wrapped, which covers the markup a data file contributes.
An unclosed `<a>` in a bio paragraph is invisible in the built page but swallows the prose after it, so the build fails instead.

`src/about.html` keeps the photo's `srcset` and its 148x185 display size: those are layout, and swapping the photo means regenerating both widths anyway.
The alt text and caption are in `about.txt`.

Partials carry no `style` attributes; styling lives in `src/main.css`.
The shared pieces are `.section-intro` and `.section-note` for the paragraphs under a heading, `.eyebrow` for a small uppercase label, `.quick-links`, `.plain-list` for an unbulleted nested list, and `.reason-list` for a bulleted one.
The two exceptions are a value the build computes (the filament swatch's `background`) and `src/cv.html`, which is generated outside this repo.

## Typography
Source files are UTF-8, the page and the feed both declare UTF-8, and every read and write in `make.py` pins `encoding="utf-8"`.
A literal `–`, `’`, `§`, `−`, or `←` passes through to the output untouched, so type the character.

Two kinds of entity are still written as entities:

+ `&nbsp;`, since a non-breaking space is invisible in source.
+ `&amp;`, `&lt;`, and `&gt;`, which are required escapes rather than typography.

`src/cv.html` is generated outside this repo and still uses entities; leave it alone.

One hazard is worth knowing: `§` is both prose (section numbers) and the sub-template delimiter.
`split_sections` only treats a line matching `^§[A-Z][A-Z0-9_]*§$` as a delimiter, so `<li><strong>§7:</strong> ...</li>` is safe.
Do not put a bare `§WORD§` on a line of its own in body copy.

## Setup
The build needs Python and three packages:

```
pip install -r requirements.txt
```

Regenerating the sidebar wireframes needs more, including ffmpeg on PATH, and is only occasionally necessary:

```
pip install -r requirements-wireframes.txt
```

## Building
```
make
```
Edit files in `src/`, run the build.
Paths are resolved relative to the repo root, so the underlying `python src/make.py` still runs from anywhere.

`make check` rebuilds, then fails if the committed `index.html` or `rss.xml` differs from what the source produces.
The build is deterministic so a clean result means the committed output is current.
Worth running before a push: Cloudflare serves the committed files, so stale output ships silently with no error anywhere.

`make wireframes` regenerates `images/wireframes/`.

Sections listed in `unpublished` in `make.py` are skipped and emitted empty (currently: printlab and links).
HTML comments are stripped from the built output.
