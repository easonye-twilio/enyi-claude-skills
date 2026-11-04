#!/usr/bin/env bash
# Fail if a branch adds lint/type/style suppressions.
#
#   check-suppressions.sh <profile.md> <base-ref> [<head-ref>]
#
# Reads the `Globs:` and `Patterns:` lines under `## Suppressions` in the profile
# (each value a backtick-quoted token; patterns are extended regexes). Diffs
# <head-ref> (default HEAD) against its merge-base with <base-ref>, considers added
# lines only, and prints each hit as `file:line: text`.
#
# Exit: 0 clean, 1 suppressions added, 2 usage or setup error.
set -euo pipefail

usage() {
  echo "usage: $(basename "$0") <profile.md> <base-ref> [<head-ref>]" >&2
  exit 2
}

[[ $# -ge 2 && $# -le 3 ]] || usage
profile=$1
base=$2
head=${3:-HEAD}

[[ -f $profile ]] || { echo "profile not found: $profile" >&2; exit 2; }

# Backtick-quoted tokens of the `<key>:` entry inside the Suppressions section. An entry
# runs until a blank line or the next `Key:` line, so a long list may wrap.
tokens() {
  awk -v key="$1" '
    function emit(text) {
      while (match(text, /`[^`]+`/)) {
        print substr(text, RSTART + 1, RLENGTH - 2)
        text = substr(text, RSTART + RLENGTH)
      }
    }
    /^## /                  { in_section = ($0 == "## Suppressions"); collecting = 0; next }
    !in_section             { next }
    index($0, key ":") == 1 { collecting = 1; emit(substr($0, length(key) + 2)); next }
    collecting && (/^[[:space:]]*$/ || /^[A-Za-z][A-Za-z ]*:/) { collecting = 0; next }
    collecting              { emit($0) }' "$profile"
}

globs=()
while IFS= read -r token; do globs+=("$token"); done < <(tokens Globs)
patterns=()
while IFS= read -r token; do patterns+=("$token"); done < <(tokens Patterns)

if [[ ${#globs[@]} -eq 0 || ${#patterns[@]} -eq 0 ]]; then
  echo "no Globs/Patterns under '## Suppressions' in $profile" >&2
  exit 2
fi

top=$(git rev-parse --show-toplevel) || { echo "not inside a git repository" >&2; exit 2; }
merge_base=$(git -C "$top" merge-base "$base" "$head") || { echo "no merge-base for $base and $head" >&2; exit 2; }

joined=$(IFS='|'; echo "${patterns[*]}")

hits=$(
  git -C "$top" -c core.quotepath=off diff --no-color --no-ext-diff --no-textconv --no-renames \
      --unified=0 --src-prefix=a/ --dst-prefix=b/ "$merge_base..$head" -- "${globs[@]}" |
    SUPPRESSION_RE=$joined awk '
      # Inside a hunk, trust the header counts: a content line such as "++ x" must not
      # be mistaken for a "+++ file" header.
      old_left > 0 || new_left > 0 {
        kind = substr($0, 1, 1)
        if (kind == "+") {
          if (file != "" && substr($0, 2) ~ ENVIRON["SUPPRESSION_RE"])
            printf "%s:%d: %s\n", file, line, substr($0, 2)
          line++; new_left--
        } else if (kind == "-") old_left--
        else if (kind == " ") { line++; new_left--; old_left-- }
        next
      }
      /^\+\+\+ / {
        file = substr($0, 5); sub(/\t.*$/, "", file)
        file = (file == "/dev/null") ? "" : substr(file, 3)
        next
      }
      /^@@ / {
        old_left = ($2 ~ /,/) ? substr($2, index($2, ",") + 1) + 0 : 1
        new_left = ($3 ~ /,/) ? substr($3, index($3, ",") + 1) + 0 : 1
        line = substr($3, 2) + 0
      }'
)

if [[ -n $hits ]]; then
  echo "Added suppressions (base $base, merge-base ${merge_base:0:10}):" >&2
  echo "$hits"
  exit 1
fi
