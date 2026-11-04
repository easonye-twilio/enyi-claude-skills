#!/usr/bin/env bash
# Collects the deterministic half of a standup digest: the lookback window,
# local git commits, and GitHub PR activity (authored, reviewed, commented).
# Emits a single JSON object on stdout. Jira, Slack and Calendar are left to
# the model, since those live behind MCP tools rather than the shell.
#
# Usage: collect.sh [--since YYYY-MM-DD]

set -uo pipefail

GH_LOGIN="easonye-twilio"
GIT_AUTHOR_MATCH="easonye"
REPO_GLOBS=("$HOME/dev/src/github.com/"*/* "$HOME/dev/wt/"*)

# --- Lookback window -------------------------------------------------------
# "Since the last weekday" so a Monday run covers Friday's work. Note the
# explicit if/elif rather than a case statement: macOS ships bash 3.2, which
# miscounts a case arm's ")" as closing an enclosing $( ), and this script is
# routinely run inside one.
since=""
if [ "${1:-}" = "--since" ] && [ -n "${2:-}" ]; then
  since="$2"
else
  dow=$(date +%u)   # 1=Mon .. 7=Sun
  if [ "$dow" = "1" ]; then
    back=3          # Monday -> Friday
  elif [ "$dow" = "7" ]; then
    back=2          # Sunday -> Friday
  else
    back=1
  fi
  since=$(date -v-"${back}"d +%Y-%m-%d)
fi

now=$(date +"%Y-%m-%dT%H:%M:%S%z")
today=$(date +%Y-%m-%d)

# --- Local git commits -----------------------------------------------------
# Scanned across every checkout and worktree because plenty of real work is
# committed locally before it ever becomes a PR. --all catches feature branches
# that are not currently checked out. The author is matched as a substring
# because the configured email differs between segmentio and twilio repos.
git_json="[]"
for repo in "${REPO_GLOBS[@]}"; do
  if [ ! -e "$repo/.git" ]; then continue; fi
  name=$(basename "$repo")
  commits=$(git -C "$repo" log --all --no-merges \
    --author="$GIT_AUTHOR_MATCH" \
    --since="$since 00:00" \
    --date=short \
    --format='%h%x1f%ad%x1f%s%x1e' 2>/dev/null)
  if [ -z "$commits" ]; then continue; fi
  repo_json=$(printf '%s' "$commits" | tr '\036' '\n' | grep -v '^$' |
    jq -R -s --arg repo "$name" --arg path "$repo" '
      split("\n") | map(select(length > 0)) | map(split("")) |
      map({repo: $repo, path: $path, sha: .[0], date: .[1], subject: .[2]})
    ')
  git_json=$(jq -n --argjson a "$git_json" --argjson b "$repo_json" '$a + $b')
done

# A worktree under ~/dev/wt shares history with its parent checkout, so the
# same commit is found twice. Deduplicate by sha, keeping the first sighting.
git_json=$(printf '%s' "$git_json" | jq 'unique_by(.sha) | sort_by(.date) | reverse')

# --- GitHub PR activity ----------------------------------------------------
# Three separate searches because GitHub has no single "I touched this" filter.
# Reviewed and commented PRs are collected deliberately: review work is real
# work and is the thing people most often forget to mention at standup.
#
# A failed search is recorded in "errors" rather than quietly becoming an empty
# list. This matters more than it looks: GitHub calls fail transiently (TLS,
# proxy, rate limit), and an empty list is indistinguishable from "you did
# nothing yesterday" once it reaches the digest. The consumer needs to be able
# to say "GitHub was unreachable" instead of inventing a quiet day.
# Each search returns an envelope {ok, data, error} rather than a bare array,
# because the call happens in a command-substitution subshell and so cannot
# append to a shared error list.
GH_FIELDS="number,title,url,state,repository,updatedAt,isDraft,author"

gh_search() {
  local filter="$1" out rc
  out=$(gh search prs "$filter" "$GH_LOGIN" --updated ">=$since" --limit 40 --json "$GH_FIELDS" 2>&1)
  rc=$?
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | jq -e 'type == "array"' >/dev/null 2>&1; then
    printf '%s' "$out" | jq '{ok: true, data: ., error: null}'
  else
    printf '%s' "$out" | tr '\n' ' ' | cut -c1-300 |
      jq -R -s '{ok: false, data: [], error: .}'
  fi
}

env_authored=$(gh_search --author)
env_reviewed=$(gh_search --reviewed-by)
env_commented=$(gh_search --commenter)

authored=$(printf '%s' "$env_authored" | jq '.data')
reviewed=$(printf '%s' "$env_reviewed" | jq '.data')
commented=$(printf '%s' "$env_commented" | jq '.data')

# Collected so the digest can report an unreachable source as unreachable.
errors=$(jq -n \
  --argjson a "$env_authored" --argjson r "$env_reviewed" --argjson c "$env_commented" '
  [{source: "github:authored"} + $a, {source: "github:reviewed"} + $r, {source: "github:commented"} + $c]
  | map(select(.ok == false) | {source, error})')

# A PR you authored will also surface as one you commented on; drop that
# overlap so the digest does not list the same PR under two headings.
# Piped rather than fed by here-string: a here-string needs a writable temp
# file, which is not guaranteed in every sandbox this may run under.
drop_own() {
  printf '%s' "$1" | jq --argjson own "$2" \
    'map(select(.url as $u | $own | index($u) | not))'
}

own_urls=$(printf '%s' "$authored" | jq -r '[.[].url]')
reviewed=$(drop_own "$reviewed" "$own_urls")
commented=$(drop_own "$commented" "$own_urls")

# Leaving a review almost always leaves a comment too, so "commented" is
# mostly a copy of "reviewed". Subtract it, and what remains is the genuinely
# distinct case: a PR you weighed in on without being a reviewer.
reviewed_urls=$(printf '%s' "$reviewed" | jq -r '[.[].url]')
commented=$(drop_own "$commented" "$reviewed_urls")

jq -n \
  --arg since "$since" \
  --arg now "$now" \
  --arg today "$today" \
  --arg login "$GH_LOGIN" \
  --argjson git "$git_json" \
  --argjson authored "$authored" \
  --argjson reviewed "$reviewed" \
  --argjson commented "$commented" \
  --argjson errors "$errors" \
  '{
     window: {since: $since, collected_at: $now, today: $today},
     github_login: $login,
     commits: $git,
     prs_authored: $authored,
     prs_reviewed: $reviewed,
     prs_commented: $commented,
     errors: $errors
   }'
