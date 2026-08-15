# haileyjay.net
Source for my personal website. Built with a small Python script.

## Structure
+ `src/`: source files (HTML partials, CSS, JS, build script)
+ `src/shared.html`: sub-templates used by more than one section (currently the gallery card)
+ `src/data/`: content data, kept separate from markup
  + `comics.txt`: one `stem | caption | alt` row per comic
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

## Building
``` python src/make.py ```
Paths are resolved relative to the repo root, so the script can be run from
anywhere. Edit files in `src/`, run the script.

Sections listed in `unpublished` in `make.py` are skipped and emitted empty
(currently: printlab and links). HTML comments are stripped from the built output.
