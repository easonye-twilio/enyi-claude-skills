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
| Infra / IaC / tables / CI | cloud-native-monorepo-foundation (platform standards, required) and cloud-native-monorepo-platform (required Terraform modules), then agent-connect-domain, maestro-domain, memora-domain, plus ESOD 07 for data-model constraints and IPD for platform setup (search it with `search-internal-product-docs`) |
| API / domain logic | ESOD 07, plus the Blueprint for phasing and open decisions |
| Product behavior / scope questions | PRD, plus the Blueprint |
| SDK feature | The relevant SDK repo, ESOD 07 for the API contract, and its sibling SDKs for parity |

Never read a whole snapshot. `rg` for the relevant headings first. The Blueprint is a live doc (the "Control-Data APIs tab (final)" artifact), not a snapshot: read only the tab or section the task needs. The Claude Docs `export` (format `markdown`) is too large for context and returns base64 inside JSON, and the tool saves the oversized result to a file. Decode it with `jq -r '.[1].text' <saved file> | jq -r '.data.bytes_b64' | base64 -d > $TMPDIR/blueprint.md`, then `rg -n '^#{1,3} '` for headings and read only the sections you need. The doc is about 1,000 lines. Its tab id is `66375c76-ef01` and its doc id is in `INDEX.md`.

## How to use the sources

1. **Architecture first.** Before proposing a design, read the parts of the TAC design doc (ESOD 07) that apply to the task. If the task touches requirements or scope, also read the PRD snapshot in `~/.claude/references/tac/snapshots/` and the Blueprint (fetched live, see Staleness). Read only the relevant sections, not whole documents.
2. **Patterns from sibling domains.** For infrastructure and code patterns such as DynamoDB tables, IaC, service layout, config and CI:
   - Look at how `maestro-domain` and `memora-domain` do it, using `rg` and `fd` on the paths in the index.
   - Treat a pattern used in both as a team convention. If they differ, point out the difference and ask the user.
   - Follow the conventions agent-connect-domain already has before copying from a sibling.
3. **Reconcile.** If a sibling's pattern conflicts with TAC architecture or requirements, TAC wins. Call out the conflict explicitly. Platform standards are the exception: `cloud-native-monorepo-foundation` and the Terraform modules in `cloud-native-monorepo-platform` are mandatory for CND, so they win over both siblings and local preference. If TAC needs something they don't allow, flag it to the user rather than deviating.
4. **Cite.** When a decision rests on one of these sources, name it, e.g. "per ESOD 07 §Data model" or "matches maestro-domain/infra/…".

## Staleness

- If a snapshot is missing, or the user says the docs changed, suggest running `/tac-sync`.
- Snapshots record their sync date in a header. Mention it if a snapshot is more than 2 weeks old.
- Before relying on a repo's patterns, consider a `git -C <path> pull --ff-only`. Ask first if the repo has local changes.
- URL sources that have no snapshot are fetched live: GitHub through `gh`, artifacts with the Artifact read action (artifacts built from the Claude Docs type, like the Blueprint, hold their content in the Claude Docs service: read them with the Claude Docs `read`/`export` tools instead), Google Docs with Drive read_file_content.
