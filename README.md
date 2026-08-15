# haileyjay.net
Source for my personal website. Built with a small Python script.

## Structure
+ `src/`: source files (HTML partials, CSS, JS, build script)
+ `src/shared.html`: sub-templates used by more than one section (currently the gallery card)
+ `src/data/`: content data, kept separate from markup
  + `comics.txt`: one `stem | caption | alt` row per comic
  + `printlab.txt`: printer, gallery, and filament data for the 3D print lab.
    Currently absent: the section is unpublished and its last contents were
    placeholders, archived to `~/Port/website-printlab-data-2026-08-15.tar.xz`.
    The build asserts on the missing file, so restore it before taking
    `printlab` out of `unpublished`.
  + `blog/<isodate>-<slug>.html`: one file per post. Filename sort gives newest-first order. An underscore prefix (`_2026-...`) marks a draft; drafts are skipped by the build.

The date and slug come from the filename, so the front matter is just a
title and teaser, ended by a blank line:

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

One image per line, `image | caption | alt` -- the same row format `comics.txt`
and the print gallery use. A bare stem resolves to `images/blog/<slug>/<stem>.webp`;
anything with a slash is used as the path as-is. The caption fills the card title
or figcaption, the lightbox caption, and (absent a third field) the alt text.
The build reads each image's dimensions and emits them, so images reserve their
space before they load. The build fails if an image is missing.

Both forms open the lightbox, and the prev/next sequence is scoped to the post, so a post's gallery and its inline figures scroll together in DOM order.

Anything wider than 640px also gets a 640px thumbnail written to
`images/thumbs/`, mirroring the source path minus the leading `images/`.
The thumbnail is what the grid, the blog index, and the homepage carousel
load; the original stays in the `srcset` for wide viewports and is what the
lightbox opens. Thumbnails are rebuilt only when the source is newer, so a
no-op build is fast. They are committed alongside the other built output.

+ `src/make.py`: builds `index.html`, `rss.xml`, and `images/thumbs/` from the source files
+ `index.html`, `rss.xml`, `images/thumbs/`: built output

## Templates
Partials are split on `§NAME§` marker lines, and `{name}` placeholders are
filled by `render()` in `make.py`. Braces that are not a known placeholder are
left alone, so a partial can contain inline CSS or JS verbatim.

## Typography
Type the character. Source files are UTF-8, the page and the feed both declare
UTF-8, and every read and write in `make.py` pins `encoding="utf-8"`, so a
literal `–`, `’`, `§`, `−`, or `←` passes through to the output untouched.
There is no escape-code table to remember and no build step in the way.

Two entities are still worth writing as entities:

+ `&nbsp;` -- a non-breaking space is invisible in source, so the entity is
  the only readable form.
+ `&amp;`, `&lt;`, `&gt;` -- required escapes, not typography.

`src/cv.html` is generated from `~/Quarters/CV` and still uses entities; leave
it alone, it round-trips fine either way.

One thing to watch: `§` is both prose (section numbers) and the sub-template
delimiter. `split_sections` only treats a line matching `^§[A-Z][A-Z0-9_]*§$`
as a delimiter, so `<li><strong>§7:</strong> ...</li>` is safe, but do not put
a bare `§WORD§` on a line of its own in body copy.

## Building
``` python src/make.py ```
Paths are resolved relative to the repo root, so the script can be run from
anywhere. Edit files in `src/`, run the script.

Sections listed in `unpublished` in `make.py` are skipped and emitted empty
(currently: printlab and links). HTML comments are stripped from the built output.
