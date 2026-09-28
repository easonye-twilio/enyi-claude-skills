---
name: tickets-to-manifest
description: >-
  Turn a set of Jira tickets into an implementation manifest: dependency-ordered
  PR buckets with per-bucket scope, branch base, and acceptance criteria. Use when
  the user invokes /tickets-to-manifest, hands over several ticket keys or URLs and
  asks how to sequence or split the work, or asks which tickets block which. Produces
  the manifest that /implement-manifest consumes. Planning only — writes no code.
---

# Tickets to manifest

Turns a pile of tickets into an execution plan: which work can run in parallel,
what blocks what, and how it buckets into PRs.

## Outcome

A manifest file at `~/.claude/manifests/<repo-name>/<slug>.md` whose buckets are
mutually consistent: every ticket appears in exactly one bucket, every declared
dependency points at a bucket defined earlier in the file, and every bucket has
acceptance criteria concrete enough that a worker can self-verify. Nothing is
implemented. The turn ends with the manifest path and an explicit approval ask.

## Mode

Run in **auto mode**, not plan mode — the manifest is a written artifact and plan
mode blocks writes until exit. Safety comes from the approval gate at the end, not
from the mode.

## 1. Resolve the tickets

Accepts ticket keys (`MEMORY-123`), Jira URLs, or a mix. Strip URLs to keys.

Fetch each with `jira-inator:jira-query`. Pull summary, description, acceptance
criteria, story points, existing issue links, and current status. Existing
`Blocks`/`Relates` links are evidence — reconcile them against what you infer from
the code rather than trusting either alone.

Note any ticket already `Done` or already in progress on a branch; ask whether to
exclude it before you bucket.

## 2. Explore in parallel (token-efficient)

Fan out read-only subagents, one per ticket, to answer only: *which files and
modules does this ticket touch?* Set `model` explicitly — this is enumeration, not
reasoning:

```
Agent(subagent_type: "Explore", model: "haiku",
      description: "Scope MEMORY-123",
      prompt: "<ticket summary + description>. Find the files, components, and
               modules this change would touch in <repo>. Search breadth: medium.
               Report ONLY: a file/dir list, the public API surface involved, and
               existing tests covering it. No recommendations, no code, under 200 words.")
```

Launch all of them in a single message so they run concurrently. The point is that
their search output never enters your context — only the file lists come back.

Reserve `sonnet` for a ticket whose scope is genuinely ambiguous. Do not use opus
here; scoping is not the deliverable.

## 2b. Check for repo-provided implementation guidance

Some repos ship skills that own how a change is built. Look in
`.claude/skills/` for one matching each bucket's kind. Do not hardcode skill
names — discover them, and record what you found.

If a bucket's work is covered by such a skill, the worker must be routed through
it rather than improvising. Record the exact invocation in the manifest's
`Guidance:` field.

**In `one-console` specifically**, page and UI work is owned by `/implement-page`
(which itself invokes `/implement-ui-pattern` when given a Figma URL). Route to
`/implement-page`, not `/implement-ui-pattern` — the latter is only correct for a
pattern-only ticket with no page assembly.

These skills have **interactive gates that an unattended worker cannot clear**.
Resolving them here, in the foreground, is the point of this step:

- `/implement-ui-pattern` Step 2 short-circuits when every pattern already exists
  in console-ds (no 🔄 variations, no ❌ missing). That early-exit is exactly the
  autonomous/interactive boundary.
- Any 🔄 or ❌ pattern triggers a Design Systems review checkpoint whose required
  option is "document requirements and exit." No coordinator can approve a new
  console-ds pattern, so no `ask`/`reply` round-trip resolves it.
- `/implement-page` Step 1.5.4 **always** gates on `AskUserQuestion` before Step 2,
  even on the pre-specified migration path.

So for each UI bucket, do the gap analysis now. Have the scoping subagent run the
same read-only searches that skill prescribes — `ls libs/console-ds/src/`,
`ls libs/ds-react/src/{atoms,molecules,organisms}`, grep for the pattern type —
against the ticket's Figma decomposition. Do not invoke the skill to do this; you
do not own its steps and replaying them here would drift.

Then classify:

- **All patterns exist** → `Autonomous: yes`. Capture the Step 1.5 architectural
  decisions (page structure, route URLs, data-layer reuse, code to reuse vs.
  write) into the manifest's `Architecture:` block and get the user to approve
  them at the step 6 gate. That approval is what lets the worker skip the
  `AskUserQuestion`.
- **Any 🔄 or ❌ pattern** → `Autonomous: no`, with the reason. These are *not
  dispatched*. They run in the foreground with you.

A bucket with no Figma URL cannot use `/implement-ui-pattern` at all — that skill
hard-requires one. Either attach the mockup or mark the bucket `Autonomous: no`.

**Why this gap analysis is the load-bearing step.** An agent that needs a pattern
the design system does not have will reach for a `className` and an
`eslint-disable` to get unblocked — which passes locally and then breaks the PR
pipeline on the DS-suppressions gate. The cause is a missing pattern, not a
careless agent, so catching it here is the actual fix. Every ❌ you find now is a
suppression that never gets written.

Do not paper over a gap by widening a bucket's scope or loosening its constraints.
Record it, mark the bucket non-autonomous, and surface it as a design-system gap
the user needs to resolve with the DS team.

## 3. Derive the dependency graph

Two buckets conflict if they touch the same files, or if one introduces a symbol,
migration, or API the other consumes. File overlap alone is the strongest signal
and comes straight from step 2.

Encode **only real ordering**. A dependency you add "to be safe" serializes work
for no benefit. Prefer wide parallel waves over chains; flag any chain deeper than
3 as a decomposition smell worth revisiting with the user.

## 4. Bucket into PRs

**The bucket is the unit of dispatch and the unit of PR.** One bucket → one
worktree → one worker → one draft PR. Consolidation is decided here, at planning
time, not cleaned up afterward.

Bucket by review coherence, not ticket count:
- Small tickets touching the same module → one bucket, one PR.
- A ticket large enough to stand alone → its own bucket.
- Never split one ticket across buckets. If a ticket genuinely needs two PRs, say
  so and offer to split the ticket itself via `jira-inator:jira-subtask-manager`.

Consult `pr-optimizer:analyze` on any bucket that looks oversized rather than
eyeballing it. Do not reimplement split heuristics.

**Dependent buckets stack.** A bucket that depends on bucket A bases its branch on
A's branch, and its PR targets A's branch — not `main`. Record both.

Assign a model per bucket: `sonnet`/`high` by default; `opus` only where the
reasoning is the hard part (subtle refactors, concurrency, security-sensitive
paths). Justify any opus assignment in one clause.

## 5. Write the manifest

Path: `~/.claude/manifests/<repo-name>/<slug>.md`. Repo *name*, not path — so it
resolves identically from the main checkout and from any worktree. Create the
directory if absent. This lives outside the repo deliberately: no gitignore
management, no risk of committing it.

```markdown
# Manifest: <slug>
Repo: <repo-name>
Base: main
Created: <YYYY-MM-DD>
Tickets: MEMORY-123, MEMORY-124, MEMORY-130

## Bucket A — <PR title>
- Tickets: MEMORY-123, MEMORY-124
- Depends on: none
- Branch: <user>/<slug>-a
- PR base: main
- Model: sonnet / high
- Autonomous: yes
- Guidance: /implement-page <figma-url>     # or "none"
- Target: <exact files, dirs, or modules in scope>
- Change: <the concrete result to produce>
- Constraints: <invariants, do-not-touch boundaries, repo lint rules>
- Acceptance: <the command or evidence that proves completion>
- Architecture: <pre-approved Step 1.5 decisions — page structure, route URLs,
  data-layer reuse, reuse-vs-write. Omit when Guidance is none.>
- Status: pending
- Validated: pending          # or n/a when nothing is user-visible
- PR: —

## Bucket B — <PR title>
- Tickets: MEMORY-130
- Depends on: Bucket A
- Branch: <user>/<slug>-b
- PR base: <user>/<slug>-a
- Model: opus / high  (subtle: <one-clause reason>)
- ...
```

**`Acceptance` must be hermetic** — typecheck, lint, unit tests, a programmatic
design check. Never write acceptance a worker cannot reach: no Storybook, no dev
server, no browser, no authenticated session, no E2E. Those need shared resources
and a single login, so they belong to the coordinator's serial pass. An acceptance
criterion that says "verify visually in Storybook" is a bucket that can never
self-report success.

`Target` / `Change` / `Constraints` / `Acceptance` are the task-spec contract —
they become the worker's prompt verbatim, so vagueness here is vagueness there.
"Update the frontend" is a failure; "Replace moment.js with date-fns in
`libs/common-frontend/src/utils/date.ts`, preserving output format" is not.

`Status` and `PR` are mutable — `/implement-manifest` writes them back so a run can
resume.

## 6. Stop and ask

Report: bucket count, the wave structure (what runs in parallel, what waits), total
story points, and the manifest path. Call out **non-autonomous buckets separately**
with their reason — those need the user in the loop and will not be dispatched.

Where a bucket carries an `Architecture:` block, surface it for approval now. This
is the one chance to catch a wrong architectural call before a worker builds on it;
the worker will treat the block as settled.

Then ask for approval before any implementation. Do not chain into
`/implement-manifest` on your own.

Offer to write the inferred dependencies back to Jira as issue links
(`jira-inator:jira-ticket-linker`) — useful when the plan should be visible to the
team, skippable when it's a local working plan.
