# enyi-claude-skills

Claude Code plugin with a ticket-to-PR workflow:

- `tickets-to-manifest` — turn Jira tickets into a dependency-ordered implementation manifest
- `implement-manifest` — execute a manifest across worktrees, one draft PR per bucket
- `validate-manifest` — verify implemented work against real resources (browser, local stack, deploy, logs), per repo profile

Validation profiles live in `profiles/<name>.md`, one per repo family. A profile lists
the repos it covers, their hermetic checks, validation kinds, preflight, gotchas, evidence,
and teardown. Add one when starting work in a repo no profile covers.

Two more directories ship with the skills:

- `scripts/` — deterministic helpers the skills call instead of spelling the work out in prose:
  `manifest.py` (`status`, and `set` to edit a single manifest field in place; stdlib Python 3)
  and `check-suppressions.sh` (fails if a branch adds suppressions matching a profile's
  `## Suppressions` globs and patterns).
- `references/` — detail a skill loads only when it needs it: the Orca and fallback
  execution backends, and one-console UI routing.

Each profile's `## Suppressions` section lists `Globs:` and `Patterns:` (backtick-quoted
tokens; patterns are extended regexes) and the worker rule copied into task specs.

## Install

```sh
claude plugin marketplace add easonye-twilio/enyi-claude-skills
claude plugin install enyi-claude-skills@enyi-claude-skills
```

Skills are invoked as `/enyi-claude-skills:<skill-name>`.

## Update

```sh
claude plugin marketplace update enyi-claude-skills
claude plugin update enyi-claude-skills@enyi-claude-skills
```

Restart Claude Code to apply.

## Releasing changes

Bump `version` in `.claude-plugin/plugin.json` with every change you want installs
to pick up. `claude plugin update` compares versions only, so new commits under an
unchanged version report "already at the latest version".

## Local development

```sh
claude plugin marketplace add ~/dev/src/github.com/enyi-claude-skills
```
