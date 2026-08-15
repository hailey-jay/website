# haileyjay.net
Source for my personal website. Built with a small Python script.

## Structure
+ `src/`: source files (HTML partials, CSS, JS, build script)
+ `src/data/`: content data, kept separate from markup
  + `comics.txt`: three lines per comic (file stem, alt text, caption)
  + `blog/<isodate>-<slug>.html`: one file per post, `key: value` meta lines then the HTML body. Filename sort gives newest-first order. An underscore prefix (`_2026-...`) marks a draft; drafts are skipped by the build.

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

One image per line, `image | caption | alt`. A bare stem resolves to `images/blog/<slug>/<stem>.webp`; anything with a slash is used as the path as-is. The caption fills the card title or figcaption, the lightbox caption, and (absent a third field) the alt text. The build fails if an image is missing.

Both forms open the lightbox, and the prev/next sequence is scoped to the post, so a post's gallery and its inline figures scroll together in DOM order.

+ `src/make.py`: builds `index.html` and `rss.xml` from the source files
+ `index.html`, `rss.xml`: built output

## Building
``` python src/make.py ```
Run from the repo root. Edit files in `src/`, run the script.

Sections listed in `unpublished` in `make.py` are still built but emitted empty (currently: printlab). HTML comments are stripped from the built output.
