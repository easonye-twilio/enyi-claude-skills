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
import contextlib
import fcntl
import os
import re
import sys
import tempfile

BUCKET_RE = re.compile(r"^## Bucket (\S+)")
HEADING_RE = re.compile(r"^## ")
FIELD_RE = re.compile(r"^- ([A-Za-z][A-Za-z -]*?):[ \t]*(.*?)\s*$")
HEADER_RE = re.compile(r"^([A-Za-z][A-Za-z -]*?):[ \t]*(.*?)\s*$")
FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")

MUTABLE = ("Status", "Validated", "Validated-at", "Redispatches", "Evidence", "PR", "Notes", "Worktree", "Dispatch", "Run")
ALLOWED = {
    "Status": {"pending", "dispatched", "done", "failed", "unknown"},
    "Validated": {"pending", "pass", "fail", "waiting", "unverified", "n/a"},
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
    words = value.split()
    return words[0].strip("`").rstrip(",;.") if words else ""


def fence_kinds(lines):
    """Classify each line: '.' plain, 'o' fence open, 'i' inside a fence, 'c' fence close.

    A fence closes only on the same character, at least as long as the opener.
    """
    kinds = []
    fence = None
    for line in lines:
        text = strip_eol(line)
        if fence is None:
            match = FENCE_OPEN_RE.match(text)
            if match:
                fence = (match.group(1)[0], len(match.group(1)))
                kinds.append("o")
            else:
                kinds.append(".")
        elif re.match(rf" {{0,3}}{re.escape(fence[0])}{{{fence[1]},}}\s*$", text):
            fence = None
            kinds.append("c")
        else:
            kinds.append("i")
    return kinds


def sections(lines):
    """Return (header_range, {bucket_id: (start, end)}) using half-open line ranges."""
    kinds = fence_kinds(lines)
    headings = [i for i, line in enumerate(lines) if kinds[i] == "." and HEADING_RE.match(line)]
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
    kinds = fence_kinds(lines)
    first = None
    for index in range(start, end):
        line = strip_eol(lines[index])
        if kinds[index] != ".":
            if kinds[index] == "o" and first is not None and not line.startswith((" ", "\t")):
                return first, index
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


def insertion_point(lines, start, end, pattern):
    """Line index after the last top-level field of [start, end), or after the heading."""
    kinds = fence_kinds(lines)
    last_field = None
    for index in range(start, end):
        if kinds[index] == "." and pattern.match(strip_eol(lines[index])):
            last_field = index
    if last_field is None:
        return trim_trailing_blanks(lines, start, end)
    _, block_end = find_field(lines, start, end, pattern.match(strip_eol(lines[last_field])).group(1), pattern)
    return trim_trailing_blanks(lines, last_field, block_end)


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


@contextlib.contextmanager
def locked(path):
    """Serialize read-modify-write cycles across processes via a lock on the directory."""
    fd = os.open(os.path.dirname(path), os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def cmd_set(path, bucket, name, value):
    canonical = next((f for f in MUTABLE if f.lower() == name.lower()), None)
    if canonical is None:
        die(f"field must be one of {', '.join(MUTABLE)}", 2)
    if "\n" in value or "\r" in value:
        die("value must be a single line", 2)
    allowed = ALLOWED.get(canonical)
    if allowed and first_word(value).lower() not in allowed:
        die(f"{canonical} must start with one of: {', '.join(sorted(allowed))}", 2)

    path = os.path.realpath(path)
    with locked(path):
        apply_set(path, bucket, canonical, value)
    print(f"{bucket} {canonical}: {value.strip()}")


def apply_set(path, bucket, canonical, value):
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
        insert_at = insertion_point(lines, start, end, pattern)
        if insert_at > 0 and not lines[insert_at - 1].endswith("\n"):
            lines[insert_at - 1] += eol
        lines.insert(insert_at, new_line)

    fd, temp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".manifest-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.writelines(lines)
        os.chmod(temp, os.stat(path).st_mode & 0o7777)
        os.replace(temp, path)
    except BaseException:
        os.unlink(temp)
        raise


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
