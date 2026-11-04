#!/usr/bin/env python3
"""Read and edit the mutable fields of an implementation manifest.

  manifest.py status <manifest>
  manifest.py set <manifest> <bucket> <field> <value>

A bucket is a `## Bucket <id> ...` section. Its fields are top-level `- Name: value`
lines; indented lines and blank lines after a field belong to it. Every other section
(status logs, rollout steps, handoff) is left byte-for-byte untouched, and `set`
rewrites only the one field it was asked to change.

Use the bucket name `manifest` to read or write a header field such as `Run`.
Older manifests carry prose after a field's value ("done (2026-10-08, ...)"); the
first word is the value.
"""
import os
import re
import sys
import tempfile

BUCKET_RE = re.compile(r"^## Bucket (\S+)")
HEADING_RE = re.compile(r"^## ")
FIELD_RE = re.compile(r"^- ([A-Za-z][A-Za-z -]*?):[ \t]*(.*?)\s*$")
HEADER_RE = re.compile(r"^([A-Za-z][A-Za-z -]*?):[ \t]*(.*?)\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")

MUTABLE = ("Status", "Validated", "PR", "Notes", "Worktree", "Dispatch", "Run")
ALLOWED = {
    "Status": {"pending", "dispatched", "done", "failed", "unknown"},
    "Validated": {"pending", "pass", "fail", "n/a"},
}
STATUS_COLUMNS = ("Status", "Validated", "PR", "Worktree", "Dispatch")


def die(message, code=1):
    print(f"manifest.py: {message}", file=sys.stderr)
    sys.exit(code)


def read_lines(path):
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            return handle.read().splitlines(keepends=True)
    except OSError as exc:
        die(f"cannot read {path}: {exc.strerror}")


def strip_eol(line):
    return line.rstrip("\r\n")


def first_word(value):
    cleaned = value.strip().strip("`")
    return cleaned.split()[0].rstrip(",;.") if cleaned else ""


def sections(lines):
    """Return (header_range, {bucket_id: (start, end)}) using half-open line ranges."""
    headings = []
    fenced = False
    for index, line in enumerate(lines):
        if FENCE_RE.match(line):
            fenced = not fenced
        elif not fenced and HEADING_RE.match(line):
            headings.append(index)
    header_end = headings[0] if headings else len(lines)
    buckets = {}
    for position, start in enumerate(headings):
        match = BUCKET_RE.match(lines[start])
        if not match:
            continue
        end = headings[position + 1] if position + 1 < len(headings) else len(lines)
        bucket_id = match.group(1).rstrip(":.,—-")
        key = bucket_id.lower()
        if key in buckets:
            die(f"duplicate bucket heading: {bucket_id}")
        buckets[key] = (bucket_id, start, end)
    return (0, header_end), buckets


def find_field(lines, start, end, name, pattern):
    """Locate a field's line range [first, last) inside [start, end)."""
    fenced = False
    first = None
    for index in range(start, end):
        line = strip_eol(lines[index])
        if FENCE_RE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = pattern.match(line)
        if first is None:
            if match and match.group(1).lower() == name.lower():
                first = index
            continue
        if line.startswith((" ", "\t")) or not line.strip():
            continue
        return first, index
    return (first, end) if first is not None else (None, None)


def trim_trailing_blanks(lines, first, last):
    while last > first + 1 and not lines[last - 1].strip():
        last -= 1
    return last


def field_value(lines, start, end, name, pattern):
    first, _ = find_field(lines, start, end, name, pattern)
    if first is None:
        return None
    return pattern.match(strip_eol(lines[first])).group(2)


def cmd_status(path):
    lines = read_lines(path)
    (hs, he), buckets = sections(lines)
    if not buckets:
        die("no `## Bucket` sections found")
    run = field_value(lines, hs, he, "Run", HEADER_RE)
    if run:
        print(f"Run: {first_word(run)}")
    for bucket_id, start, end in buckets.values():
        cells = []
        for name in STATUS_COLUMNS:
            value = field_value(lines, start, end, name, FIELD_RE)
            if value is None:
                continue
            word = first_word(value)
            if name in ("PR", "Worktree", "Dispatch") and word in ("", "—", "-", "none"):
                continue
            cells.append(word if name == "Status" else f"{name.lower()}={word}")
        print(f"{bucket_id}  " + "  ".join(cells or ["(no mutable fields)"]))


def cmd_set(path, bucket, name, value):
    canonical = next((f for f in MUTABLE if f.lower() == name.lower()), None)
    if canonical is None:
        die(f"field must be one of {', '.join(MUTABLE)}", 2)
    if "\n" in value or "\r" in value:
        die("value must be a single line", 2)
    allowed = ALLOWED.get(canonical)
    if allowed and first_word(value).lower() not in allowed:
        die(f"{canonical} must start with one of: {', '.join(sorted(allowed))}", 2)

    lines = read_lines(path)
    (hs, he), buckets = sections(lines)
    if bucket.lower() == "manifest":
        start, end, pattern, template = hs, he, HEADER_RE, "{}: {}"
    else:
        if bucket.lower() not in buckets:
            known = ", ".join(b[0] for b in buckets.values()) or "none"
            die(f"unknown bucket {bucket!r} (known: {known})", 2)
        _, start, end = buckets[bucket.lower()]
        pattern, template = FIELD_RE, "- {}: {}"

    eol = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    new_line = template.format(canonical, value.strip()) + eol
    first, last = find_field(lines, start, end, canonical, pattern)
    if first is not None:
        last = trim_trailing_blanks(lines, first, last)
        lines[first:last] = [new_line]
    else:
        insert_at = trim_trailing_blanks(lines, start, end)
        lines.insert(insert_at, new_line)

    directory = os.path.dirname(os.path.abspath(path))
    fd, temp = tempfile.mkstemp(dir=directory, prefix=".manifest-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.writelines(lines)
        os.chmod(temp, os.stat(path).st_mode & 0o7777)
        os.replace(temp, path)
    except BaseException:
        os.unlink(temp)
        raise
    print(f"{bucket} {canonical}: {value.strip()}")


def main(argv):
    if len(argv) == 3 and argv[1] == "status":
        cmd_status(argv[2])
    elif len(argv) == 6 and argv[1] == "set":
        cmd_set(*argv[2:])
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
