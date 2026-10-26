# haileyjay.net
Source for my personal website.
Built with a small Python script.

## Structure
+ `src/`: source files (HTML partials, CSS, JS, build script)
+ `src/shared.html`: sub-templates used by more than one section (the gallery card, the grid that holds cards, and the inline figure; the tutorial uses the last two as posts do)
+ `src/sagitta/`: the shell, partials, and stylesheet for the standalone Sagitta pages (see below)
+ `src/data/`: content data, kept separate from markup
  + `about.txt`: the identity fields, the meta lines under the name, bio, and Lately note
  + `comics.txt`: one `stem | caption | alt` row per comic
  + `sagitta/landing.txt`: the Sagitta landing page's copy
  + `sagitta/tutorial.html`: the Sagitta walkthrough, front matter then body, like a post
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

An optional `colour: #rrggbb` line gives the post its own colour: its rules, its date, its underline and date in the blog list, and the backdrop while it is open.
Without one, the post takes the Blog section's ochre.

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

+ `src/make.py`: builds `index.html`, `rss.xml`, `sitemap.xml`, and `images/thumbs/` from the source files, and calls `src/sagitta_pages.py` for the Sagitta pages
+ `src/common.py`: the parts both builds share (the repo-root anchoring, the image pipeline, the `[gallery]`/`[image]` directives, front matter, and the KaTeX head)
+ `src/sagitta_pages.py`: builds the Sagitta pages (see below)
+ `sitekit/`: a vendored copy of the shared build library (upstream commit `fa89364`), used by all four of my site repos.
  Text and data-format parsing, template filling, markup validation, the image pipeline, asset bundling, minification, and the post-build checker all live there.
  Everything that knows this site is haileyjay.net stays in `src/`: RSS, the `[gallery]`/`[image]` directives, draft-by-filename, comics, and the about page.
+ `katex/`: a vendored copy of KaTeX 0.19.0, served as-is; see `katex/README.md`
+ `scripts/check.py`, `scripts/verify.py`: the two checks, behind `make check` and `make verify`
+ `scripts/app.py`: copies the Sagitta editor into `sagitta/app/`, behind `make app`
+ `index.html`, `sagitta/index.html`, `sagitta/tutorial/index.html`, `rss.xml`, `sitemap.xml`, `images/thumbs/`: built output
+ `sagitta/app/`: the Sagitta editor, copied in from its own repo and served as-is

## The Sagitta pages
The site proper is one document whose sections are hash fragments, and the sidebar tabs are all facets of me.
[Sagitta](https://github.com/hailey-jay/sagitta) is not one of those: it has its own navigation, its own manual, and the editor itself served from `sagitta/app/`, so it is built as real files under `/sagitta/` with a shell of its own.
The sidebar links out to it under `Projects` rather than adding a tab.

+ `sagitta/index.html`: the landing page, from `src/sagitta/landing.html` and `src/data/sagitta/landing.txt`
+ `sagitta/tutorial/index.html`: the walkthrough, from `src/sagitta/tutorial.html` and `src/data/sagitta/tutorial.html`
+ `sagitta/app/`: the editor

`sagitta_pages` in `sagitta_pages.py` lists them. Each page knows two prefixes, and both the shell and the partials use them rather than hard-coding a depth:

+ `{up}` reaches the site root, for assets: `../` for the landing page, `../../` for the tutorial.
+ `{base}` reaches `/sagitta/`, for links within the group: `./` and `../`.

Both pages inline `src/main.css` and `src/main.js` in full, so the typography, the theme toggle, and the figure lightbox are the site's and stay in step with it; `src/sagitta/sagitta.css` adds only the page chrome, prefixed `sg-`.
Relative `url()` references in the inlined stylesheet are rewritten with `{up}`, because an inlined stylesheet resolves them against the document rather than against itself.
No bare `<section>` is used on these pages: `main.css` hides those until the single-page router marks one active.

The walkthrough body takes the same `[image ...]` directives a post does, with bare stems resolving against `images/sagitta/`, which also holds the landing page's hero and examples.
Those files are `.png` screenshots, so the rows name the extension; a stem without one is still taken as `.webp`.

`make app` copies the editor in.
Sagitta is a static page with relative paths and no bundler, so hosting it is a file copy: `scripts/app.py` brings over `index.html`, the stylesheets, `src/`, `web/`, `fonts/`, `icons/`, the manifest, the service worker, and the licences, and prunes anything that has left the source.
The desktop shell's own half (`electron/`), the test suites, and the packaging output stay behind.
The copy is tracked here, because the repo is what Cloudflare serves.

The editor runs in a browser on its own: `web/host.js` stands in for the desktop shell, the manifest lets a browser install it as an app, and the service worker keeps it working offline.
Both the manifest and the service worker use relative paths, so they are correct under `/sagitta/app/`.
Chromium opens and saves the diagram file in place; Firefox reads a copy and saves by downloading one.

The same sync copies the editor's `icon.svg` to `images/sagitta.svg`, which is what this site uses for Sagitta: the two pages' favicon, the landing page's wordmark, and the sidebar entry.
One copy, kept in step with the app rather than drawn again.
It also writes `sagitta/app/VERSION` from the clone's `package.json`, which is where the landing page's version comes from, so the page cannot advertise a version other than the one it serves.

## Data formats
Three shapes cover every section, and they are parsed by shared helpers in `sitekit.text` rather than per-section code:

+ `---NAME---` on its own line splits a data file into blocks (`split_data`).
  Screaming case only, so a line of prose cannot open one.
  Markup uses `§NAME§` for the same job (`split_sections`).
+ `key: value` lines are fields (`parse_kv`).
  A line with no colon is an error, as is a missing required field.
+ `a | b | c` lines are rows (`parse_fields`).
  Too many fields is an error.

Prose in a data file needs no `<p>` wrap: blank-line-separated blocks are wrapped by the build, and a block may be soft-wrapped across lines.
Inline markup inside a paragraph (a link, an `<em>`) is passed through as written.

## Templates
Partials are split on `§NAME§` marker lines, and `{name}` placeholders are filled by `render()` in `sitekit.text`.
Braces that are not a known placeholder are left alone, so a partial can contain inline CSS or JS verbatim.

Every emitted section is checked for unclosed tags before it is wrapped, which covers the markup a data file contributes.
An unclosed `<a>` in a bio paragraph is invisible in the built page but swallows the prose after it, so the build fails instead.

Every failure the build reports is a `BuildError` with a sentence, not an assertion, so `python -O src/make.py` still stops instead of emitting corrupt output.
`src/*.html` is checked against the section list too, so a new partial cannot be silently ignored, and a nav link into a section listed in `unpublished` is an error rather than a link to a `<section>` that is not there.

`src/about.html` keeps the photo's `srcset` and its 148x185 display size: those are layout, and swapping the photo means regenerating both widths anyway.
The alt text and caption are in `about.txt`.

Partials carry no `style` attributes; styling lives in `src/main.css`.
The shared pieces are `.section-intro` and `.section-note` for the paragraphs under a heading, `.eyebrow` for a small uppercase label, `.quick-links`, `.plain-list` for an unbulleted nested list, and `.reason-list` for a bulleted one.
The exceptions are `src/cv.html` and `src/papers.html`, which are generated by `make install` in the separate CV repo.

## Typography
Source files are UTF-8, the page and the feed both declare UTF-8, and every read and write in the build pins `encoding="utf-8"`.
A literal `–`, `’`, `§`, `−`, or `←` passes through to the output untouched, so type the character.

Two kinds of entity are still written as entities:

+ `&nbsp;`, since a non-breaking space is invisible in source.
+ `&amp;`, `&lt;`, and `&gt;`, which are required escapes rather than typography.

`src/cv.html` is generated outside this repo and still uses entities; leave it alone.

Maths is TeX between `\(` `\)` (inline) or `\[` `\]` (display), rendered by KaTeX in the reader's browser.
A page links KaTeX only when its prose holds one of those delimiters outside `<pre>` and `<code>`, so a page without maths loads none of it.
There is no `$` delimiter.
Alt text and captions in `[image ...]` directives are not rendered, so write their maths in words.

`split_sections` treats a line matching `^§[A-Z][A-Z0-9_]*§$` as a delimiter, so `<li><strong>§7:</strong> ...</li>` is safe.
Do not put a bare `§WORD§` on a line of its own in body copy.

## Setup
The build needs Python and three packages:

```
pip install -r requirements.txt
```

`sitekit/` is vendored rather than installed, so there is nothing else to set up here or on the server, and this site pins a version of it by simply not updating the directory.
Changes belong upstream in the sitekit repo and are copied back in.

Regenerating the footer wireframes needs more, including ffmpeg on PATH, and is only occasionally necessary:

```
pip install -r requirements-wireframes.txt
```

## Building
```
make
```
Edit files in `src/`, run the build.
Paths are resolved relative to the repo root, so the underlying `python src/make.py` still runs from anywhere.

`make check` scans the built pages (`index.html` and the two Sagitta pages; not the editor, which is not this build's to audit) for the problems that only show up in the finished page: a local `href` or `src` pointing at nothing, a duplicate id, an `<img>` missing its alt, dimensions, or `loading` hint, and the total weight of image one page pulls.
It also fails if `sagitta/app/` is older than Sagitta's newest release tag; that step needs the network and is skipped offline.

`make verify` rebuilds, then fails if the committed pages, `rss.xml`, or `sitemap.xml` differ from what the source produces, and restores the worktree either way.
The build is deterministic so a clean result means the committed output is current.
Worth running before a push: Cloudflare serves the committed files, so stale output ships silently with no error anywhere.

`make links` checks every off-site URL. It needs the network and is slow, so it is separate from `make check`.

`make serve` hosts the repo at `http://localhost:8000/` for previewing the built pages (`PORT=9000` to move it).
It serves the files on disk, so build first.

`make app` refreshes `sagitta/app/` from a fresh clone of [Sagitta](https://github.com/hailey-jay/sagitta)'s `main`, made in a temporary directory and deleted afterwards.
`SAGITTA` overrides the repo (a URL or a local path) and `SAGITTA_REF` the branch or tag:

```
make app SAGITTA_REF=v0.6.0
```

`make wireframes` regenerates `images/wireframes/`.

Sections listed in `unpublished` in `make.py` are skipped and emitted empty (currently none).
HTML comments are stripped from the built output.

## License
Copyright © 2025-2026 Hailey Jay Garcia.
This repository holds work under five different terms.

+ **Code: GPL-3.0-or-later.**
  `src/make.py`, `src/common.py`, `src/sagitta_pages.py`, `sitekit/`, `scripts/`, `Makefile`, `src/main.css`, `src/main.js`, the HTML partials in `src/` (the templates and markup, not the prose inside them), and the wireframe videos in `images/wireframes/` that `scripts/gen_wireframes.py` renders are free software: you can redistribute and/or modify them under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License or (at your option) any later version.
  They are distributed without any warranty; see [`LICENSE`](LICENSE) for the full text.
+ **Photographs without faces: CC BY 4.0.**
  The photos under `images/blog/` are licensed under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/), along with their thumbnails in `images/thumbs/`, with these exceptions, which are not covered:
  + any image showing a person's face, unless this file names it as licensed (as it does the portrait below);
  + `images/blog/dolomites/strudel.webp`, which shows no face but is reserved anyway.

  Attribute as "Photo by Hailey Jay Garcia, haileyjay.net".
+ **Portrait and rose: CC BY-NC 4.0.**
  `images/hailey-*.webp` and `images/rose.svg` are licensed under [Creative Commons Attribution-NonCommercial 4.0 International](https://creativecommons.org/licenses/by-nc/4.0/).
  Attribute as for the photos above.
+ **The editor: GPL-3.0-or-later, upstream.**
  `sagitta/app/` is a copy of [Sagitta](https://github.com/hailey-jay/sagitta), which is itself a fork of varkor’s [quiver](https://github.com/varkor/quiver).
  It keeps its own terms and its own `LICENSE` and `NOTICE`, and is not relicensed here.
+ **KaTeX: MIT, upstream.**
  `katex/` keeps KaTeX's own `LICENSE` and is not relicensed here.
+ **Fonts: SIL Open Font License 1.1.**
  The EB Garamond files in `fonts/` keep their upstream license and are not relicensed here.
+ **Other people's marks: theirs.**
  The logos in `images/links/` (LSU, AWM, the RTG, and ORCID) belong to their owners and are used only to mark links to them.
  The 88x31 buttons `images/buttons/clairebutton.gif` and `jambutton.png` are Claire's and Jamie's own, shown as they made them.
+ **Everything else: all rights reserved.**
  This includes the writing (blog posts, `src/data/`, and the prose in the partials), the comics, the CV, and the photos excepted above.

The built output (`index.html`, the Sagitta pages, `rss.xml`, and `sitemap.xml`) combines all of the above, and each part keeps its own terms.

## AI assistance
Parts of this repository were written with Claude, an AI model by Anthropic, used as a coding assistant in Claude Code.

+ **Code and documentation:** much of `src/make.py`, `src/common.py`, `src/sagitta_pages.py`, `sitekit/`, `scripts/`, `src/main.css`, `src/main.js`, the makefile, and this README was drafted or refactored with AI assistance.
  I directed, reviewed, and tested all of it, and I am responsible for it.
+ **Content:** the writing, photographs, and comics are my own.
  AI edits to content files were limited to restructuring, repairing markup, and small copy-edits; none of the prose was AI-written.
