"""Text utilities shared by every section: parsing the data formats,
filling templates, and checking markup.

Pure text in, pure text out. Nothing here knows which section it is
serving, reads a file, or touches an image, which is why one set of
helpers covers all of them."""
import re

COMMENT_RE = re.compile(r"<!--.*?-->", re.S)

def strip_comments(markup):
    """Drop HTML comments, including commented-out blog drafts.

    Applied to each partial as it is read, before the minified CSS and
    JS are inlined, so a --> inside a script or style string is never
    seen by this regex."""
    return COMMENT_RE.sub("", markup)

# ── Markup validation ────────────────────────────────────────
# An unclosed tag is invisible in the built page (the parser closes
# it for you, usually in the wrong place) but corrupts the RSS body
# and swallows following prose into a link. Cheaper to catch here.
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr"}
TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>")

def check_balance(markup, label):
    """Assert that every non-void element in `markup` is closed, in order."""
    stack = []
    for closing, name, self_closing in TAG_RE.findall(markup):
        name = name.lower()
        if name in VOID or self_closing:
            continue
        if not closing:
            stack.append(name)
        else:
            assert stack, f"{label}: stray </{name}>"
            assert stack[-1] == name, \
                f"{label}: </{name}> closes <{stack[-1]}>"
            stack.pop()
    assert not stack, f"{label}: unclosed <{stack[-1]}>"

PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

def render(template, **fields):
    """Substitute {name} placeholders in a template.

    Unlike str.format, a literal brace needs no escaping and an
    unrecognised {name} is left alone, so a partial can carry inline
    JS or CSS verbatim. Values are inserted as-is; escape before
    passing anything that needs it."""
    return PLACEHOLDER_RE.sub(
        lambda m: str(fields[m.group(1)]) if m.group(1) in fields else m.group(0),
        template,
    )

def repeat(template, records, sep="\n\n", **common):
    """Render `template` once per record dict, joined by `sep`.

    `common` supplies the fields every copy shares; a record may
    override them. Empty renders are dropped, so a record that expands
    to nothing leaves no blank gap behind."""
    out = [render(template, **{**common, **record}).strip() for record in records]
    return sep.join(chunk for chunk in out if chunk)

# ── Content formats ──────────────────────────────────────────
# Four shapes cover every section: delimited blocks, `key: value`
# fields, blank-line-separated records of those fields, and pipe rows.
# They are defined once here and shared, so a section's data file reads
# the same whichever section it belongs to.

def split_on(text, pattern):
    """Split `text` on whole-line delimiters matching `pattern`.

    The text before the first delimiter is keyed ""; each delimiter's
    captured name keys the block that follows it. Naming the pieces
    means adding one cannot silently shift the others."""
    parts   = {}
    key     = ""
    current = []
    for line in text.splitlines():
        m = pattern.match(line.strip())
        if m:
            parts[key] = "\n".join(current).strip()
            key        = m.group(1)
            current    = []
        else:
            current.append(line)
    parts[key] = "\n".join(current).strip()
    return parts

# Markup uses §NAME§, data files use ---NAME---. Both are matched
# strictly: a whole line, screaming case, nothing else. Prose contains a
# literal § for section numbers ("§7: Monday 13:30-14:20"), and a loose
# match would let a line of copy open a sub-template and silently
# truncate the section above it.
SECTION_RE = re.compile(r"^§([A-Z][A-Z0-9_]*)§$")
DATA_RE    = re.compile(r"^-{3}([A-Z][A-Z0-9_]*)-{3}$")

def split_sections(raw):
    """Split a partial into its markup and its §NAME§ sub-templates."""
    return split_on(raw, SECTION_RE)

def split_data(raw):
    """Split a data file into its ---NAME--- blocks."""
    return split_on(raw, DATA_RE)

def parse_kv(text, label, required=()):
    """Parse a block of `key: value` lines into a dict."""
    fields = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, colon, val = line.partition(":")
        assert colon, f"{label}: line is not 'key: value': {line!r}"
        fields[key.strip()] = val.strip()
    missing = [k for k in required if k not in fields]
    assert not missing, f"{label}: missing {', '.join(missing)}"
    return fields

def parse_records(text, label, required=()):
    """Parse blank-line-separated `key: value` blocks into a list of dicts."""
    return [parse_kv(block, label, required)
            for block in re.split(r"\n[ \t]*\n", text) if block.strip()]

def parse_fields(row, count=None):
    """Split a `a | b | c` row, padding to `count` with empty strings."""
    fields = [f.strip() for f in row.split("|")]
    if count is not None:
        assert len(fields) <= count, \
            f"Row has {len(fields)} fields, expected at most {count}: {row!r}"
        fields += [""] * (count - len(fields))
    return fields

def rows_of(text):
    """Yield the non-blank lines of a block of pipe rows."""
    return [line for line in text.splitlines() if line.strip()]

def group_rows(text, label):
    """Group pipe rows under bare heading lines.

    A line with no `|` opens a group and every row after it belongs to
    that group, which is how the filament table gets its diameters and
    the links list its categories."""
    groups  = []
    current = None
    for line in rows_of(text):
        line = line.strip()
        if "|" not in line:
            current = (line, [])
            groups.append(current)
        else:
            assert current, f"{label}: row before any heading: {line!r}"
            current[1].append(line)
    return groups

def indent(text, pad):
    """Indent every line of `text` after the first by `pad`.

    Templates place their own first line, so only the continuations
    need padding to line up under it."""
    return text.replace("\n", "\n" + pad)

def paragraphs(text, template="<p>{body}</p>"):
    """Wrap blank-line-separated prose in `template`.

    Lets a data file hold body copy without the <p> boilerplate, while
    still allowing inline markup (a link, an <em>) inside a paragraph.
    Lines within one paragraph are joined, so prose can be wrapped to a
    comfortable width in the source."""
    blocks = [b.strip() for b in re.split(r"\n[ \t]*\n", text) if b.strip()]
    return "\n\n".join(
        render(template, body=" ".join(line.strip() for line in b.splitlines()))
        for b in blocks
    )
