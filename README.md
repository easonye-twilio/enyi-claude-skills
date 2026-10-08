# enyi-claude-skills

Claude Code plugin with a ticket-to-PR workflow:

- `tickets-to-manifest` — turn Jira tickets into a dependency-ordered implementation manifest
- `implement-manifest` — execute a manifest across worktrees, one draft PR per bucket
- `validate-manifest` — verify implemented work visually in a real browser

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
