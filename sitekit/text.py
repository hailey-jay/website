"""Text utilities: parsing the data formats, filling templates, shaping prose.

Pure text in, pure text out. Nothing here reads a file, touches an image, or
knows which site it is serving, which is why one set of helpers covers all of
them.

Two record dialects are supported, because the sites disagree and both are
reasonable:

    pipe/block   ---NAME--- blocks, `key: value` fields, `a | b | c` rows
    ini          [header] sections, `key=value` fields, blank line per record

Use whichever the data already is; they do not mix within one file."""
import re

from .errors import BuildError, need

COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def strip_comments(markup):
    """Drop HTML comments, including commented-out drafts.

    Apply to each partial as it is read, before any minified CSS or JS is
    inlined, so a `-->` inside a script or style string is never seen by this
    regex."""
    return COMMENT_RE.sub("", markup)


# ── Templates ────────────────────────────────────────────────
PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def render(template, **fields):
    """Substitute {name} placeholders in a template.

    Deliberately not str.format. Two failure modes that cost real debugging
    time on these sites:

      * a literal brace needs no escaping here, so a template may carry inline
        CSS or JS verbatim. `.format` raises KeyError on the first `{` of a
        style rule.
      * an unrecognised {name} is left alone rather than raising, so a partial
        can mention a placeholder in prose.

    Substitution is a single pass, so inserted content is never itself
    rescanned. Rescanning is how a prose mention of "{css}" once got an entire
    stylesheet spliced into it.

    Values are inserted as-is; escape before passing anything that needs it."""
    return PLACEHOLDER_RE.sub(
        lambda m: str(fields[m.group(1)]) if m.group(1) in fields else m.group(0),
        template,
    )


def repeat(template, records, sep="\n\n", **common):
    """Render `template` once per record dict, joined by `sep`.

    `common` supplies the fields every copy shares; a record may override them.
    Empty renders are dropped, so a record that expands to nothing leaves no
    blank gap behind."""
    out = [render(template, **{**common, **record}).strip() for record in records]
    return sep.join(chunk for chunk in out if chunk)


def placeholders(template):
    """The set of {name} placeholders a template actually contains.

    Pair with `expect_placeholders` to catch the reverse mistake from an
    unfilled slot: a slot that was renamed in the template and silently stopped
    being filled."""
    return set(PLACEHOLDER_RE.findall(template))


def expect_placeholders(template, names, label="template"):
    """Require each of `names` to appear exactly once in `template`.

    A placeholder appearing twice is usually a copy-paste in the shell, and
    both copies get the whole stylesheet."""
    for name in names:
        hits = template.count("{" + name + "}")
        need(hits == 1,
             f"{label}: {{{name}}} appears {hits} time(s), expected exactly 1")


# ── Block and section splitting ──────────────────────────────
def split_on(text, pattern):
    """Split `text` on whole-line delimiters matching `pattern`.

    The text before the first delimiter is keyed ""; each delimiter's captured
    name keys the block that follows it. Naming the pieces means adding one
    cannot silently shift the others."""
    parts = {}
    key = ""
    current = []
    for line in text.splitlines():
        m = pattern.match(line.strip())
        if m:
            parts[key] = "\n".join(current).strip()
            key = m.group(1)
            current = []
        else:
            current.append(line)
    parts[key] = "\n".join(current).strip()
    return parts


# Markup uses §NAME§, data files use ---NAME---. Both are matched strictly: a
# whole line, screaming case, nothing else. Prose contains a literal § for
# section numbers ("§7: Monday 13:30-14:20"), and a loose match would let a line
# of copy open a sub-template and silently truncate the section above it.
SECTION_RE = re.compile(r"^§([A-Z][A-Z0-9_]*)§$")
DATA_RE = re.compile(r"^-{3}([A-Z][A-Z0-9_]*)-{3}$")


def split_sections(raw):
    """Split a partial into its markup and its §NAME§ sub-templates."""
    return split_on(raw, SECTION_RE)


def split_data(raw):
    """Split a data file into its ---NAME--- blocks."""
    return split_on(raw, DATA_RE)


# ── Fields, records, rows ────────────────────────────────────
def parse_kv(text, label, required=()):
    """Parse a block of `key: value` lines into a dict."""
    fields = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, colon, val = line.partition(":")
        need(colon, f"{label}: line is not 'key: value': {line!r}")
        fields[key.strip()] = val.strip()
    missing = [k for k in required if k not in fields]
    need(not missing, f"{label}: missing {', '.join(missing)}")
    return fields


def parse_records(text, label, required=()):
    """Parse blank-line-separated `key: value` blocks into a list of dicts."""
    return [parse_kv(block, label, required)
            for block in re.split(r"\n[ \t]*\n", text) if block.strip()]


def parse_fields(row, count=None):
    """Split a `a | b | c` row, padding to `count` with empty strings."""
    fields = [f.strip() for f in row.split("|")]
    if count is not None:
        need(len(fields) <= count,
             f"Row has {len(fields)} fields, expected at most {count}: {row!r}")
        fields += [""] * (count - len(fields))
    return fields


def rows_of(text):
    """Yield the non-blank lines of a block of pipe rows."""
    return [line for line in text.splitlines() if line.strip()]


def group_rows(text, label):
    """Group pipe rows under bare heading lines.

    A line with no `|` opens a group and every row after it belongs to that
    group, which is how a filament table gets its diameters and a links list
    its categories."""
    groups = []
    current = None
    for line in rows_of(text):
        line = line.strip()
        if "|" not in line:
            current = (line, [])
            groups.append(current)
        else:
            need(current, f"{label}: row before any heading: {line!r}")
            current[1].append(line)
    return groups


# ── The INI dialect ──────────────────────────────────────────
def parse_ini(text, header_re=r"^\[(.+)\]$", flags=0):
    """Parse an INI-ish body into [(header_groups, [record_dict])].

    `header_re` must capture at least one group; the stripped groups come back
    as a tuple, which is what lets one parser serve headers of different arity:

        [Faculty]                 -> ("Faculty",)
        [year: 2026]              -> ("2026",)      with r'^\\[year:\\s*(.+)\\]$'
        [current: Fall 2026]      -> ("current", "Fall 2026")

    Blank lines separate records within a section."""
    groups, key, records, record = [], None, [], {}

    def flush_record():
        nonlocal record
        if record:
            records.append(record)
            record = {}

    def flush_section():
        nonlocal records
        if key is not None:
            flush_record()
            groups.append((key, records))
            records = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        m = re.match(header_re, line, flags)
        if m:
            flush_section()
            key = tuple(g.strip() for g in m.groups())
            continue
        if line == "":
            flush_record()
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            record[k.strip()] = v.strip()

    flush_section()
    return groups


# ── Prose shaping ────────────────────────────────────────────
def indent(text, pad):
    """Indent every line of `text` after the first by `pad`.

    Templates place their own first line, so only the continuations need
    padding to line up under it."""
    return text.replace("\n", "\n" + pad)


def paragraphs(text, template="<p>{body}</p>"):
    """Wrap blank-line-separated prose in `template`.

    Lets a data file hold body copy without the <p> boilerplate, while still
    allowing inline markup (a link, an <em>) inside a paragraph. Lines within
    one paragraph are joined, so prose can be soft-wrapped in the source."""
    blocks = [b.strip() for b in re.split(r"\n[ \t]*\n", text) if b.strip()]
    return "\n\n".join(
        render(template, body=" ".join(line.strip() for line in b.splitlines()))
        for b in blocks
    )


__all__ = [
    "BuildError", "strip_comments", "render", "repeat", "placeholders",
    "expect_placeholders", "split_on", "split_sections", "split_data",
    "parse_kv", "parse_records", "parse_fields", "rows_of", "group_rows",
    "parse_ini", "indent", "paragraphs",
]
