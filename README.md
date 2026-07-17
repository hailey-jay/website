# haileyjay.net
Source for my personal website. Built with a small Python script.

## Structure
+ `src/`: source files (HTML partials, CSS, JS, build script)
+ `src/data/`: content data, kept separate from markup
  + `comics.txt`: three lines per comic (file stem, alt text, caption)
  + `blog/<isodate>-<slug>.html`: one file per post, `key: value` meta lines then the HTML body. Filename sort gives newest-first order. An underscore prefix (`_2026-...`) marks a draft; drafts are skipped by the build.
+ `src/make.py`: builds `index.html` and `rss.xml` from the source files
+ `index.html`, `rss.xml`: built output

## Building
``` python src/make.py ```
Run from the repo root. Edit files in `src/`, run the script.

Sections listed in `unpublished` in `make.py` are still built but emitted empty (currently: printlab). HTML comments are stripped from the built output.
