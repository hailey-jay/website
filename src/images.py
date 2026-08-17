"""Image measurement and thumbnail generation.

The only part of the build that opens an image file, so it is also the
only part that needs Pillow. Paths are repo-relative strings throughout,
because that is what the emitted markup carries."""
from pathlib import Path

from PIL import Image

# Anchored to the repo root rather than the working directory, so the
# build can be run from anywhere.
root = Path(__file__).resolve().parent.parent

def get_size(path):
    with Image.open(path) as im:
        return im.size

# ── Thumbnails ───────────────────────────────────────────────
# Gallery originals are 1024-1600px but are displayed at ~200px in a
# grid and capped at 640px in the lightbox, so the grid was pulling
# half-megabyte photos to fill a thumbnail. A downscaled copy is
# generated per image and offered first; the original stays in the
# srcset for wide viewports and remains what the lightbox opens.
THUMB_WIDTH = 640

def thumb_for(path):
    """Return (relative path, width, height) of `path`'s thumbnail.

    Images already at or under THUMB_WIDTH are their own thumbnail.
    Regenerated only when the source is newer, so repeat builds are
    cheap and the output stays byte-stable."""
    src_file = root / path
    w, h = get_size(src_file)
    if w <= THUMB_WIDTH:
        return path, w, h

    # Mirror the source tree under images/thumbs/, minus a leading
    # "images/" so blog photos land at images/thumbs/blog/... rather
    # than images/thumbs/images/blog/...
    stem = path.rsplit(".", 1)[0]
    if stem.startswith("images/"):
        stem = stem[len("images/"):]
    out_rel = f"images/thumbs/{stem}.webp"
    out_file = root / out_rel
    tw = THUMB_WIDTH
    th = round(h * THUMB_WIDTH / w)

    if not out_file.exists() or out_file.stat().st_mtime < src_file.stat().st_mtime:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src_file) as im:
            im.resize((tw, th), Image.LANCZOS).save(out_file, "WEBP", quality=82, method=6)
    return out_rel, tw, th

def img_attrs(path, sizes):
    """src/srcset/sizes/width/height for a gallery image."""
    w, h = get_size(root / path)
    thumb, tw, _ = thumb_for(path)
    if thumb == path:
        return f'src="{path}" width="{w}" height="{h}"'
    return (f'src="{thumb}" srcset="{thumb} {tw}w, {path} {w}w" '
            f'sizes="{sizes}" width="{w}" height="{h}"')

# Grid cards sit in a ~640px main column at three-up, and go roughly
# half-width once the sidebar collapses.
GRID_SIZES   = "(max-width: 640px) 45vw, 210px"
FIGURE_SIZES = "(max-width: 480px) 100vw, 420px"
