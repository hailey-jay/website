"""Post-build checks over the assembled pages.

The complement to sitekit.markup: that validates source before it is emitted,
this parses what was actually written. Each check is here because the failure
it catches is silent otherwise.

  * broken local links and images - a renamed photo or poster fails silently
    and shows up only as a hole on the live site
  * duplicate ids - a build that expands one fragment into two page sections
    puts two id="recentposts" in one document
  * missing alt / width / height / loading - the hints the build adds
    everywhere; an author-written <img> that slips past them regresses.
    `loading="eager"` counts as answered: an above-the-fold image should not
    be lazy, it should be deliberate.
  * per-page image weight - one gallery once referenced 101 MB of photo and
    nothing said a word

The external link scan is separate because it needs the network and is slow.
"""
import collections
import os
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse

DEFAULT_BUDGET = 25 * 1024 * 1024

SKIP_SCHEMES = ("http://", "https://", "mailto:", "tel:", "#", "data:",
                "javascript:")


class Scan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.imgs = []
        self.refs = []      # (tag, attr, url)
        self.ids = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "img":
            self.imgs.append(a)
        for attr in ("src", "href"):
            if a.get(attr):
                self.refs.append((tag, attr, a[attr]))


def _scan(path):
    s = Scan()
    with open(path, encoding="utf-8") as f:
        s.feed(f.read())
    return s


def _local_targets(a):
    """Every local URL an <img> points at: src plus each srcset candidate."""
    out = [a.get("src", "")]
    for part in a.get("srcset", "").split(","):
        part = part.strip()
        if part:
            out.append(part.rsplit(" ", 1)[0])
    return [u for u in out if u]


def check_page(path, problems, budget=DEFAULT_BUDGET, require=("alt", "dims", "loading")):
    """Append this page's problems to `problems`; return its image weight."""
    base = os.path.dirname(path)
    s = _scan(path)

    for tag, attr, url in s.refs:
        if url.startswith(SKIP_SCHEMES):
            continue
        target = os.path.normpath(
            os.path.join(base, unquote(urlparse(url).path)))
        if not os.path.exists(target):
            problems.append(f"{path}: <{tag} {attr}> -> missing {url}")

    dupes = [i for i, n in collections.Counter(s.ids).items() if n > 1]
    for i in sorted(dupes):
        problems.append(f'{path}: duplicate id "{i}"')

    weight = 0
    for a in s.imgs:
        src = a.get("src", "")
        # An <img> with no src is a placeholder a script fills in (a lightbox
        # target), and an <img> marked data-check="skip" is an author saying
        # they know. Neither has attributes worth auditing.
        if not src or a.get("data-check") == "skip":
            continue
        if not src.startswith(("http", "data:")):
            for u in _local_targets(a):
                t = os.path.normpath(os.path.join(base, unquote(u)))
                if not os.path.exists(t):
                    problems.append(f"{path}: srcset candidate missing {u}")
            main = os.path.normpath(os.path.join(base, unquote(src)))
            if os.path.exists(main):
                weight += os.path.getsize(main)
        if "alt" in require and "alt" not in a:
            problems.append(f"{path}: <img> with no alt: {src}")
        if "dims" in require and ("width" not in a or "height" not in a):
            problems.append(f"{path}: <img> with no dimensions: {src}")
        # Not every image should be lazy: the one above the fold wants to be
        # fetched immediately, and lazy-loading it delays the largest
        # contentful paint rather than helping it. `loading="eager"` is how an
        # author says so, and it satisfies this check; a missing attribute is
        # the accident it is looking for.
        if "loading" in require and "loading" not in a:
            problems.append(f"{path}: <img> with no loading attribute: {src}")

    if budget and weight > budget:
        problems.append(
            f"{path}: references {weight / 1e6:.1f} MB of image, over the "
            f"{budget / 1e6:.0f} MB budget")
    return weight


def check_links(pages, expected_redirects=frozenset(), timeout=25, verbose=True):
    """Every off-site URL, once. Reports anything that is not a 2xx, and any
    redirect: today's redirect is next year's 404, so they are worth a look
    even when they work. Put the ones you mean to keep in
    `expected_redirects` so the scan can stay a clean pass and therefore
    actually get run."""
    import urllib.error
    import urllib.request

    urls = set()
    for path in pages:
        for _tag, _attr, url in _scan(path).refs:
            if url.startswith(("http://", "https://")):
                urls.add(url)

    problems = []
    for url in sorted(urls):
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (sitekit link check)"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if (r.geturl().rstrip("/") != url.rstrip("/")
                        and url not in expected_redirects):
                    problems.append(f"redirects: {url}\n      -> {r.geturl()}")
                elif verbose:
                    print(f"  ok   {url}")
        except urllib.error.HTTPError as e:
            # 403 is usually a bot filter rather than a dead page; it is
            # reported as something to eyeball, not treated as different.
            problems.append(f"HTTP {e.code}: {url}")
        except Exception as e:
            problems.append(f"{type(e).__name__}: {url} ({e})")
    return problems


def run(pages, budget=DEFAULT_BUDGET, require=("alt", "dims", "loading"),
        links=False, expected_redirects=frozenset(), verbose=True):
    """Check every page and print a report. Returns a process exit code."""
    if links:
        if verbose:
            print("Checking external links (network)...")
        problems = check_links(pages, expected_redirects, verbose=verbose)
    else:
        problems = []
        for path in pages:
            w = check_page(path, problems, budget=budget, require=require)
            if verbose:
                print(f"  {path:40} {w / 1e6:7.2f} MB of image")

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems:
            print(f"    {p}")
        return 1
    print("\nall checks passed")
    return 0


__all__ = ["run", "check_page", "check_links", "Scan", "DEFAULT_BUDGET"]
