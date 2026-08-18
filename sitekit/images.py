"""One responsive-image pipeline, merged from three.

What each site knew and the others did not, all of which is now here:

  * EXIF rotation matters. A phone photo saved sideways reports landscape
    dimensions, so emitting them reserves the wrong box and shifts the layout,
    which is the exact problem width/height were added to prevent.
  * A ladder needs a rung at the source width. Deriving only 800 and 1600 from
    a 1522px photo tops the srcset out at 800, which is worse than having
    shipped the original.
  * Source paths in markup are sometimes URL-encoded (`AWMEvent%20001.jpg`) and
    sometimes carry a template token (`{Root}images/x.jpg`). Both have to come
    off before the path touches the disk and go back on before it reaches the
    markup, or the file is silently not found and the photo loses its
    dimensions and its derivatives.
  * Regeneration is gated on mtime, so a no-op build costs a stat() per photo
    rather than a re-encode.
  * Pillow is not always wanted. Without it the pipeline still reads
    dimensions, from file headers, and simply stops generating.

Paths are repo-relative POSIX strings throughout, because that is what the
emitted markup carries.
"""
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote

from .errors import BuildError, need

try:
    from PIL import Image, ImageOps
    HAVE_PILLOW = True
except ImportError:                                  # pragma: no cover
    Image = ImageOps = None
    HAVE_PILLOW = False


# ── Dimensions without Pillow ────────────────────────────────
def header_size(path):
    """(width, height) for PNG / JPEG / WebP by header parsing, or None.

    The fallback when Pillow is absent. Does not honour EXIF orientation -
    nothing that reads only headers can - so a site relying on this and serving
    camera photos will get portrait shots measured as landscape. Install Pillow
    if that matters."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", data[16:24])

        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            chunk = data[12:16]
            if chunk == b"VP8 ":
                w, h = struct.unpack("<HH", data[26:30])
                return (w & 0x3FFF, h & 0x3FFF)
            if chunk == b"VP8L":
                bits = struct.unpack("<I", data[21:25])[0]
                return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
            if chunk == b"VP8X":
                return (int.from_bytes(data[24:27], "little") + 1,
                        int.from_bytes(data[27:30], "little") + 1)
            return None

        if data[:2] == b"\xff\xd8":
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                              0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return (w, h)
                i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    except (struct.error, IndexError):
        return None
    return None


# ── Output-path policies ─────────────────────────────────────
# A derivative's path is the one thing the three sites genuinely disagreed
# about, so it is a callable (rel_path, width) -> rel_path rather than a flag.
def mirrored(dest, strip="", width_suffix=False, ext="webp"):
    """Mirror the source tree under `dest`.

        mirrored("images/thumbs", strip="images/")
            images/blog/x.jpg      -> images/thumbs/blog/x.webp
        mirrored("photo-gallery/_derived", strip="photo-gallery/",
                 width_suffix=True)
            photo-gallery/09/x.jpg -> photo-gallery/_derived/09/x-800.webp

    `strip` keeps a leading directory from appearing twice in the output path.
    `width_suffix` is for ladders; without it every rung would collide."""
    def out(rel, width):
        stem = rel[len(strip):] if strip and rel.startswith(strip) else rel
        stem = stem.rsplit(".", 1)[0]
        tail = f"-{width}" if width_suffix else ""
        return f"{dest.rstrip('/')}/{stem}{tail}.{ext}"
    return out


def sibling(dirname, width_suffix=False, ext="webp"):
    """Put derivatives in a subdirectory next to the original.

        sibling("thumb")
            images/people/x.jpeg -> images/people/thumb/x.webp
    """
    def out(rel, width):
        p = Path(rel)
        tail = f"-{width}" if width_suffix else ""
        return (p.parent / dirname / f"{p.stem}{tail}.{ext}").as_posix()
    return out


# ── The pipeline ─────────────────────────────────────────────
# A leading {Root}/{root} token or a ../ run is a prefix the markup wants back
# and the filesystem must not see.
PREFIX_RE = re.compile(r"^(\{[Rr]oot\}|(?:\.\./)+)")


@dataclass
class Pipeline:
    """Configured per site, then asked for markup attributes per image.

        pipe = Pipeline(root=REPO, widths=(640,),
                        out=mirrored("images/thumbs", strip="images/"))
        pipe.attrs("images/blog/x.jpg", GRID_SIZES)

    root        repo root; every rel path is resolved against it
    widths      ladder rungs to derive, narrowest first
    out         (rel, width) -> rel output path; None disables derivatives
    min_width   sources narrower than this are served as-is
    applies     (rel) -> bool, to confine derivation to one tree
    keep_original  keep the source as the widest srcset candidate. False when
                the derivatives fully cover the display sizes and the original
                is a multi-megabyte archive copy nobody should be served.
    generate    False uses derivatives that already exist and never writes one,
                for a site whose derivatives are made out of band.
    """
    root: Path
    widths: tuple = (640,)
    out: object = None
    min_width: int = 0
    quality: int = 82
    method: int = 6
    applies: object = None
    keep_original: bool = True
    generate: bool = True
    strict: bool = True

    _dims: dict = field(default_factory=dict, repr=False)
    _derivs: dict = field(default_factory=dict, repr=False)
    _made: int = field(default=0, repr=False)

    def __post_init__(self):
        self.root = Path(self.root)
        if self.generate and self.out is not None:
            need(HAVE_PILLOW,
                 "Generating derivatives needs Pillow (pip install pillow). "
                 "Set generate=False to use only derivatives that already exist.")

    # ── path handling ────────────────────────────────────────
    @staticmethod
    def split_prefix(site_path):
        """('{Root}' or '../' run or '', repo-relative decoded path)."""
        m = PREFIX_RE.match(site_path)
        prefix, rest = ((m.group(0), site_path[m.end():]) if m
                        else ("", site_path))
        return prefix, unquote(rest)

    @staticmethod
    def as_url(path):
        """A filesystem path back into a URL, re-escaping spaces and friends."""
        return quote(str(path), safe="/-_.~()")

    # ── measurement ──────────────────────────────────────────
    def size(self, site_path):
        """(width, height) as the browser will see it, EXIF rotation applied.

        None if unreadable. Cached: a gallery asks for the same photo from the
        grid, the carousel, and the lightbox."""
        _, rel = self.split_prefix(site_path)
        if rel in self._dims:
            return self._dims[rel]
        path = self.root / rel
        dims = None
        if HAVE_PILLOW:
            try:
                with Image.open(path) as im:
                    dims = ImageOps.exif_transpose(im).size
            except (OSError, ValueError):
                dims = None
        else:
            dims = header_size(path)
        self._dims[rel] = dims
        return dims

    def dims_attr(self, site_path):
        """` width="W" height="H"`, or '' if the file cannot be read.

        Callers still get a valid <img>, just without the hint that lets the
        browser reserve its space before the image loads."""
        dims = self.size(site_path)
        return f' width="{dims[0]}" height="{dims[1]}"' if dims else ""

    def require(self, site_path, label=""):
        """Fail the build if the image is missing. A renamed photo otherwise
        shows up as a hole on the live site and nowhere else."""
        _, rel = self.split_prefix(site_path)
        need((self.root / rel).is_file(),
             f"image not found: {rel}" + (f" ({label})" if label else ""))
        return site_path

    # ── derivation ───────────────────────────────────────────
    def _rungs(self, width):
        """Ladder rungs this source can actually fill, plus one at its own
        width when it lands between rungs."""
        below = {w for w in self.widths if w < width}
        return sorted(below | {min(width, max(self.widths))})

    def _write(self, source, dst, width):
        if dst.exists() and dst.stat().st_mtime >= source.stat().st_mtime:
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as im:
            im = ImageOps.exif_transpose(im)
            if dst.suffix.lower() in (".webp", ".jpg", ".jpeg"):
                im = im.convert("RGB")
            im.thumbnail((width, 10 ** 6), Image.LANCZOS)
            im.save(dst, quality=self.quality, method=self.method)
        self._made += 1

    def derivatives(self, site_path):
        """[(site-relative derivative path, width)], narrowest first.

        Empty for anything the policy excludes, anything already small, and
        anything unreadable; callers then fall back to the original."""
        _, rel = self.split_prefix(site_path)
        if rel in self._derivs:
            return self._derivs[rel]

        out = []
        dims = self.size(site_path)
        eligible = (self.out is not None and dims is not None
                    and dims[0] >= self.min_width
                    and (self.applies is None or self.applies(rel)))
        if eligible:
            for w in self._rungs(dims[0]):
                dst_rel = self.out(rel, w)
                dst = self.root / dst_rel
                if self.generate:
                    self._write(self.root / rel, dst, w)
                if dst.is_file():
                    out.append((self.as_url(dst_rel), w))
        self._derivs[rel] = out
        return out

    # ── markup ───────────────────────────────────────────────
    def attrs(self, site_path, sizes, full=False):
        """`src=… srcset=… sizes=… width=… height=…` for one image.

        Degrades to a plain src plus dimensions when there are no derivatives,
        so a small image or an un-derived tree still gets valid markup.

        `full` adds data-full pointing at the widest candidate, for images a
        lightbox can open: on a phone the <img> will have loaded the narrowest
        rung, which is too small to fill a screen."""
        prefix, _ = self.split_prefix(site_path)
        derivs = self.derivatives(site_path)
        dims = self.dims_attr(site_path)
        if not derivs:
            return f'src="{site_path}"{dims}'

        candidates = [(f"{prefix}{p}", w) for p, w in derivs]
        source_w = self.size(site_path)[0]
        if self.keep_original and not any(w >= source_w for _, w in candidates):
            candidates.append((site_path, source_w))

        srcset = ", ".join(f"{p} {w}w" for p, w in candidates)
        widest = candidates[-1][0]
        # src is the *narrowest* candidate: it is what a browser without srcset
        # support fetches, and those are the ones least able to afford the
        # large one.
        data_full = f' data-full="{widest}"' if full else ""
        return (f'src="{candidates[0][0]}" srcset="{srcset}" '
                f'sizes="{sizes}"{data_full}{dims}')

    @property
    def written(self):
        """How many derivatives this build actually re-encoded."""
        return self._made


__all__ = ["Pipeline", "mirrored", "sibling", "header_size", "HAVE_PILLOW"]
