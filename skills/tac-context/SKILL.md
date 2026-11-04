---
name: tac-context
description: Load Twilio Agent Connect (TAC) architecture context before designing or changing code in agent-connect-domain, twilio-agent-connect-* SDK repos, or anything touching Agent Connect. Use it when planning or implementing TAC work (new tables, APIs, infra, SDK features), when choosing patterns from sibling domains (maestro-domain, memora-domain), or when the user mentions TAC, Agent Connect or Project Nexus.
---

# TAC context

The source list lives in `~/.claude/references/tac/INDEX.md`. Read it first. Do not copy its contents into this skill.

## Scope

Load only what the task needs:
- If the user passes a scope (`$ARGUMENTS`, e.g. "infra patterns only" or "ESOD + PRD"), stay within it.
- With no scope, pick the minimum set from this table and state it in one line, e.g. "Using: ESOD 07 §Storage, maestro-domain infra". The user can then widen or narrow it.

| Task shape | Sources |
|---|---|
| Infra / IaC / tables / CI | agent-connect-domain, maestro-domain, memora-domain, plus ESOD 07 for data-model constraints and IPD for platform setup (search it with `search-internal-product-docs`) |
| API / domain logic | ESOD 07, plus the Blueprint for phasing and open decisions |
| Product behavior / scope questions | PRD, plus the Blueprint |
| SDK feature | The relevant SDK repo, ESOD 07 for the API contract, and its sibling SDKs for parity |

Never read a whole snapshot. `rg` for the relevant headings first. The Blueprint is about 3,000 lines.

## How to use the sources

1. **Architecture first.** Before proposing a design, read the parts of the TAC design doc (ESOD 07) that apply to the task. If the task touches requirements or scope, also read the PRD and Blueprint snapshots in `~/.claude/references/tac/snapshots/`. Read only the relevant sections, not whole documents.
2. **Patterns from sibling domains.** For infrastructure and code patterns such as DynamoDB tables, IaC, service layout, config and CI:
   - Look at how `maestro-domain` and `memora-domain` do it, using `rg` and `fd` on the paths in the index.
   - Treat a pattern used in both as a team convention. If they differ, point out the difference and ask the user.
   - Follow the conventions agent-connect-domain already has before copying from a sibling.
3. **Reconcile.** If a sibling's pattern conflicts with TAC architecture or requirements, TAC wins. Call out the conflict explicitly.
4. **Cite.** When a decision rests on one of these sources, name it, e.g. "per ESOD 07 §Data model" or "matches maestro-domain/infra/…".

## Staleness

- If a snapshot is missing, or the user says the docs changed, suggest running `/tac-sync`.
- Snapshots record their sync date in a header. Mention it if a snapshot is more than 2 weeks old.
- Before relying on a repo's patterns, consider a `git -C <path> pull --ff-only`. Ask first if the repo has local changes.
- URL sources that have no snapshot are fetched live: GitHub through `gh`, artifacts with the Artifact read action, Google Docs with Drive read_file_content.
