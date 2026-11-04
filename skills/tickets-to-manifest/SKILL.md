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
dependency points at a bucket defined earlier in the file, and every bucket's
acceptance and validation are numbered checks that can fail — each a command or
observation with an expected result. Nothing is implemented. The turn ends with the
manifest path and an explicit approval ask.

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

## 1b. Pick the validation profile

Profiles live at `../../profiles/<name>.md` relative to this skill's base directory.
Use the one whose `Repos:` line lists this repo's name, and read it now: its hermetic
checks are what `Acceptance` is written from, and its validation kinds are what
`Validation` is written from. Record it in the manifest's `Profile:` header.

No matching profile → say so, and offer to draft one with the user before bucketing.
Without one, `Acceptance` falls back to the repo's CI commands, `Validation` is
`none`, and `Validated` stays `pending`. `/validate-manifest` selects `pending`
buckets, finds no profile, and records each as `unverified` with the reason — so the
gap is reported downstream instead of silently skipped.

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

**In `one-console`, for any page or UI bucket**, read
`../../references/one-console-ui-routing.md` (relative to this skill's base directory)
before classifying it. It covers routing to `/implement-page`, the interactive gates an
unattended worker cannot clear, and the design-system gap analysis that decides
`Autonomous: yes` vs `no`.

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
Profile: <profile name>
Base: main
Created: <YYYY-MM-DD>
Tickets: MEMORY-123, MEMORY-124, MEMORY-130
Run: —

## Bucket A — <PR title>
- Tickets: MEMORY-123, MEMORY-124
- Depends on: none
- Branch: <user>/<slug>-a
- PR base: main
- Model: sonnet / high
- Autonomous: yes
- Guidance: /implement-page <figma-url>
- Target: <exact files, dirs, or modules in scope>
- Change: <the concrete result to produce>
- Constraints: <invariants, do-not-touch boundaries, repo lint rules>
- Acceptance:
  - A1: `<command>` → <expected result>  (covers MEMORY-123 AC1)
  - A2: `<command>` → <expected result>  (covers MEMORY-124 AC2)
- Mutation-check: no
- Judgment: <items a reviewer decides, not a command — or "none">
- Validation:
  - V1 (auto): <observation> → <expected result>  (covers MEMORY-123 AC3)
  - V2 (manual): <steps for the user> → <expected result>
  - V3 (wait): <condition> then <observation> → <expected result>
- Architecture: <pre-approved Step 1.5 decisions — page structure, route URLs,
  data-layer reuse, reuse-vs-write. Omit when Guidance is none.>
- Status: pending
- Worktree: —
- Dispatch: —
- PR: —
- Notes: —
- Validated: pending
- Evidence: —

## Bucket B — <PR title>
- Tickets: MEMORY-130
- Depends on: Bucket A
- Branch: <user>/<slug>-b
- PR base: <user>/<slug>-a
- Model: opus / high  (subtle: <one-clause reason>)
- ...

## Handoff
- Updated: <YYYY-MM-DD>
- State: <one or two lines>
- Next: <the exact command or step to resume>
```

Field values are passed to workers verbatim, so never put `#` comments inside them.
`Guidance` is `none` when no repo skill applies. `Mutation-check` is `yes` or `no`.
`Validated` is `pending`, or `n/a` when a profile exists and the bucket has no `Validation`
checks. With no profile, `Validation: none` means "not planned", not "nothing to validate":
`Validated` stays `pending`.

**Every check must be able to fail.** A check is a command or observation plus the
result that counts as passing — an exit code, a test name that must pass, a value
that must appear. "Tests pass" is not a check; "`go test ./services/x/...` exits 0
and includes `TestSingleFlightCoalesces`" is. Each ticket acceptance criterion maps to
at least one A- or V-check; say which in `(covers …)`. An AC with no check is a gap
to raise at step 6, not to paper over.

**`Acceptance` must be hermetic** — the profile's hermetic checks, plus tests that
prove the change. Never write acceptance a worker cannot reach: no Storybook, no dev
server, no browser, no authenticated session, no deploy, no E2E. Those need shared
resources and belong in `Validation`, which `/validate-manifest` runs serially. An
acceptance check that says "verify visually in Storybook" is a bucket that can never
self-report success.

**`Validation`** checks come from the profile's validation kinds. Mark each `auto`
(the skill runs it), `manual` (a human must — calling a number, approving a billable
deploy), or `wait` (needs real traffic or a deploy to land). A bucket with nothing
user-visible or deployable has no `Validation` and is `Validated: n/a` (profile present only; see step 1b for the no-profile case).

**`Judgment`** holds what no command can decide — "reviewer judges the benchmark
delta", "second-engineer review", open design questions. Keeping them here keeps
`Acceptance` falsifiable instead of diluting it. It is not part of the worker's task
spec: step 6 surfaces every non-`none` item to the user, who owns the decision at PR
review.

**`Mutation-check: yes`** makes the worker break the code each new test covers,
watch the test fail, then restore it. It costs worker time, so set it where a test
that passes vacuously would be expensive — concurrency, security-sensitive paths,
anything hard to observe later.

`Target` / `Change` / `Constraints` / `Acceptance` are the task-spec contract —
they become the worker's prompt verbatim, so vagueness here is vagueness there.
"Update the frontend" is a failure; "Replace moment.js with date-fns in
`libs/common-frontend/src/utils/date.ts`, preserving output format" is not.

`Run`, `Status`, `Worktree`, `Dispatch`, `PR`, `Notes`, `Validated`, `Evidence`, and
`## Handoff` are mutable — the implement and validate skills write them as they go so
any run can resume.

## 6. Stop and ask

Report: bucket count, the wave structure (what runs in parallel, what waits), total
story points, and the manifest path. Call out **non-autonomous buckets separately**
with their reason — those need the user in the loop and will not be dispatched.

List every bucket's `Judgment` items that are not `none` — nothing automated reads
them, so the user must agree to own them now.

List any ticket AC with no covering check, and every `manual` or `wait` validation
check — those are the user's time later, so they should agree to them now.

Where a bucket carries an `Architecture:` block, surface it for approval now. This
is the one chance to catch a wrong architectural call before a worker builds on it;
the worker will treat the block as settled.

Then ask for approval before any implementation. Do not chain into
`/implement-manifest` on your own.

Offer to write the inferred dependencies back to Jira as issue links
(`jira-inator:jira-ticket-linker`) — useful when the plan should be visible to the
team, skippable when it's a local working plan.
