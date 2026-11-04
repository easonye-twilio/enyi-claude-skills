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

# Backtick-quoted tokens on the first `<key>:` line inside the Suppressions section.
tokens() {
  awk -v key="$1" '
    /^## /          { in_section = ($0 == "## Suppressions"); next }
    in_section && index($0, key ":") == 1 {
      line = substr($0, length(key) + 2)
      while (match(line, /`[^`]+`/)) {
        print substr(line, RSTART + 1, RLENGTH - 2)
        line = substr(line, RSTART + RLENGTH)
      }
      exit
    }' "$profile"
}

globs=()
while IFS= read -r token; do globs+=("$token"); done < <(tokens Globs)
patterns=()
while IFS= read -r token; do patterns+=("$token"); done < <(tokens Patterns)

if [[ ${#globs[@]} -eq 0 || ${#patterns[@]} -eq 0 ]]; then
  echo "no Globs/Patterns under '## Suppressions' in $profile" >&2
  exit 2
fi

merge_base=$(git merge-base "$base" "$head") || { echo "no merge-base for $base and $head" >&2; exit 2; }

joined=$(IFS='|'; echo "${patterns[*]}")

hits=$(
  git diff --no-color --unified=0 "$merge_base..$head" -- "${globs[@]}" |
    SUPPRESSION_RE=$joined awk '
      /^\+\+\+ /   { file = ($2 == "/dev/null") ? "" : substr($2, 3); next }
      /^@@ /       { split($3, range, ","); line = substr(range[1], 2) + 0; next }
      /^\+/        {
        if (file != "" && substr($0, 2) ~ ENVIRON["SUPPRESSION_RE"])
          printf "%s:%d: %s\n", file, line, substr($0, 2)
        line++
      }'
)

if [[ -n $hits ]]; then
  echo "Added suppressions (base $base, merge-base ${merge_base:0:10}):" >&2
  echo "$hits"
  exit 1
fi
