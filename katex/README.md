# KaTeX, vendored

KaTeX 0.19.0, from the npm tarball `katex-0.19.0.tgz`, its sha512 checked against the registry on 2026-10-15.
Served as-is; nothing here is built.

- `katex.min.js` and `katex.min.css`: `dist/`, unchanged.
- `auto-render.min.js`: `dist/contrib/auto-render.min.js`, unchanged.
- `fonts/`: the `.woff2` files only.
  The stylesheet also lists `.woff` and `.ttf` fallbacks, which a browser that reads woff2 never fetches.
- `LICENSE`: KaTeX's MIT licence.

`src/make.py` links these into a page only when its prose holds `\(` or `\[` outside `<pre>` and `<code>`.
To upgrade, replace the files from a newer tarball and change the version above.
