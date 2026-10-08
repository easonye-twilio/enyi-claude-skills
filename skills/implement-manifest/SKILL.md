---
name: implement-manifest
description: >-
  Execute an implementation manifest: dispatch each PR bucket to its own worktree
  in dependency order, stack dependent branches, open a draft PR per bucket, and
  review each with /deepreview-branch. Use when the user invokes /implement-manifest,
  or asks to execute/run a manifest produced by /tickets-to-manifest. Uses Orca
  orchestration when available and falls back to in-process worktree subagents.
---

# Implement manifest

Executes a manifest bucket by bucket. One bucket → one worktree → one worker →
one draft PR.

## Outcome

Every bucket in the manifest reaches a terminal state — `done` with a draft PR URL,
or `failed` with the reason — and the manifest file is updated to match. No bucket
is silently skipped. The turn ends with a per-bucket table and the review results.

Safe failure: preserve the worktree and report the bucket as `failed` or `unknown`.
Never delete a worktree to clear an error.

## 1. Load the manifest

Take a path, or a slug resolved against `~/.claude/manifests/<repo-name>/`. If
several exist and none was named, list them and ask.

Parse buckets, dependencies, branch bases, per-bucket models, ticket keys,
`Autonomous`, `Guidance`, and `Architecture`. Buckets already `done` are skipped —
this is what makes a run resumable. If every bucket is `done`, say so and stop.

**`Autonomous: no` buckets are never dispatched.** They carry an interactive gate
no worker and no coordinator can clear — typically a Design Systems review for a
new or extended console-ds pattern. List them for the user to run in the
foreground, and treat their dependents as blocked until the user says otherwise.
Say this up front, not after the fan-out.

## 2. Ticket status

Transition each bucket's ticket(s) via the `jira-inator:jira-ticket-updater`
skill, silently — no confirmation needed:

- **In Progress** right before that bucket is dispatched.
- **In Review** once its worker reports done and the PR URL is known.

## 3. Pick the execution backend

```bash
orca status --json | jq -r '.result.runtime.state // "absent"'
```

- `ready` → **Orca backend** (step 4).
- anything else → **fallback backend** (step 5). Say which one you picked and why,
  in one line. Do not try to start the Orca app unless the user asks.

The rest of the skill is backend-agnostic: same buckets, same task specs, same
acceptance. Only dispatch and result-collection differ.

## 4. Orca backend

One Run for the whole manifest:

```bash
orca orchestration run-create --objective "<manifest slug>" --json \
  | jq -r '.result.run.id'
```

**Always `jq`-filter orca output.** Raw receipts carry capability lists, prompt
metadata, and effect blocks you do not need; unfiltered they are the single largest
avoidable cost in this skill.

**Keep every `orca` command bare: `orca … | jq …` and nothing else.** Under the
Claude Code sandbox, the CLI can't see the Orca app's process, so it reports
`stale_bootstrap` and refuses to connect. Listing `orca:*` and `jq:*` in
`sandbox.excludedCommands` fixes this, but only when the whole command matches
those patterns. Adding a redirect (`2>/dev/null`), chaining with `&&`/`;`, or
piping to any tool other than `jq` puts the command back in the sandbox. Expect
`check --wait` to print keepalive heartbeats on stderr; they are harmless, so
don't redirect them away. If `orca status` returns `stale_bootstrap` while the
app is open, suspect this before deciding Orca is down.

**Before the first dispatch, confirm the repo's own guardrails are live in a worker
session.** A repo may enforce constraints with `PreToolUse` hooks from its project
`.claude/settings.json` — those are the real defense against a worker coding around
a rule, and they are worth far more than any instruction in a task spec. A fresh
worktree is a new project directory, so verify the hooks actually fire there rather
than assuming they were inherited. If they are not active, say so before fanning
out: without them you are relying on worker compliance alone.

In `one-console` this is `PreToolUse → no-custom-styles.ts`, which refuses edits
that add custom styling to `console-app-modules/**/*.tsx`. It blocks only *added*
violations, so it will not fight unrelated work in legacy files.

For each bucket whose dependencies are satisfied, transition its ticket(s) to In
Progress (step 2), then create the worktree and dispatch:

```bash
# Worktree. --base-branch is the PR base from the manifest: main, or the parent
# bucket's branch when stacking.
orca worktree create --repo id:<repoId> --name <bucket-branch-name> \
  --base-branch <pr-base> --no-parent --json \
  | jq -r '.result.worktree.id'

# Dispatch. Note: --setup is REJECTED on an existing worktree selector, so it is
# only ever passed at create time.
orca orchestration worker-start --run <runId> \
  --spec "<task spec, step 6>" \
  --task-title "<bucket title>" \
  --worktree "<worktreeId>" \
  --agent claude --model <bucket model> --effort <bucket effort> --json \
  | jq -c '{task:.result.taskId, dispatch:.result.dispatchId, state:.result.state,
            agent:.result.launch.effective.agent, model:.result.launch.effective.model}'
```

Compare `launch.effective` against what you requested. If they differ, say so —
never report a model from the requested arguments alone.

Launch the entire ready wave before waiting. Then one rolling wait:

```bash
orca orchestration check --wait --types "worker_done,escalation,question" \
  --timeout-ms 900000 --json \
  | jq -c '{delivery:.result.deliveryId, timedOut:.result.timedOut,
            msgs:[.result.messages[]|{from:.from_handle, type:.type,
                  subject:.subject, body:.body, payload:.payload}]}'
```

This loop is self-contained: a timeout or empty batch means keep calling `check
--wait` again, not end the turn. Do not wrap `/implement-manifest` in `/loop` —
that would end the turn and re-enter the skill from step 1 instead of resuming
this wait.

Process **every** message in the batch before acking:
- `question` → `orca orchestration reply --id <msgId> --body "<answer>" --json`
- `escalation` → decide, then reply or mark the bucket failed
- `worker_done` → validate the payload's `taskId`/`dispatchId` against the bucket
  you expect, record outcome and PR URL, transition its ticket(s) to In Review
  (step 2), then `orca orchestration worker-release --dispatch <id> --json`

Ack, then wait again. A timeout or empty batch is a **checkpoint, not a failure** —
keep waiting. After three consecutive empty waits:

```bash
orca orchestration worker-list --run <runId> --include-remote --json \
  | jq -c '.result.workers[]|{dispatch:.dispatchId, liveness:.projection.liveness,
            next:.projection.nextAction}'
```

Act on `projection.nextAction` when it carries argv. Only positive proof of exit
(`exited` liveness, or a transcript whose last turn sent no `worker_done`)
authorizes stop or abandon — load `references/recovery-and-cleanup.md` at that
point via `orca skills get orchestration --reference ...`, not before.

When a wave settles, unblock dependents and dispatch the next wave.

## 5. Fallback backend (no Orca)

Same buckets, in-process. Transition ticket(s) to In Progress (step 2), then
create worktrees with git, dispatch with `Agent` using `isolation: "worktree"`,
and set `model` explicitly per bucket:

```
Agent(subagent_type: "general-purpose", model: "sonnet",
      isolation: "worktree",
      description: "<bucket title>",
      prompt: "<same task spec as step 6>")
```

Launch an entire wave in one message so buckets run concurrently. Collect results
(transitioning tickets to In Review once each PR URL is known, per step 2),
update the manifest, proceed to the next wave. Everything else — task spec, PR
handling, review — is unchanged.

## 6. The task spec

Every worker gets the same five fields, verbatim from the manifest, plus the
protocol block. This is the whole contract; it is why worker output never needs to
flood back into the parent.

```
Target:      <from manifest>
Change:      <from manifest>
Constraints: <from manifest>
Ownership:   This worktree only. Do not edit files outside the listed targets.
Acceptance:  <from manifest>

<IF the bucket has Guidance:>
This repo owns how this work is built. Follow <Guidance> and do not improvise
an approach it covers.

The architectural decisions below were settled and approved by the user at
manifest time. Treat them as final. Where that skill asks you to confirm
architecture interactively, use these instead of prompting — you have no
user to prompt and any question tool you open will hang unanswered.

<Architecture block from manifest>

If you hit a decision this block does not cover, use your preamble's `ask`
command to reach the coordinator. Never open a local question UI.
</IF>

Do not start dev servers, Storybook, or anything else that binds a port —
other workers are running in parallel and will collide. Visual verification
is the coordinator's job, not yours.

HARD CONSTRAINT — suppressions are a failure, not a workaround:
Do not add an eslint-disable, ts-expect-error, ts-ignore, or any other
suppression to make a design-system rule pass. Do not add a `className` to
escape a design-system limitation. If the design system cannot express what
the design needs, that is a finding to report — NOT something to code around.
Stop and `ask` the coordinator.

Before opening the PR, verify you introduced no new suppressions:

  git diff $(git merge-base origin/main HEAD)..HEAD -- '*.tsx' '*.jsx' '*.ts' \
    | grep '^+' | grep -nE 'eslint-disable|ts-expect-error|@ts-ignore'

Any hit on an ADDED line is a blocking failure. Report `failed` with the rule
you could not satisfy and why. A bucket that lands with a suppression breaks
the PR pipeline and is worth less than one that stops and asks.

Branch is already checked out and based on <pr-base>. When acceptance passes:
  1. Commit following this repo's conventional-commit style; reference the
     ticket key(s) <keys> in the subject or footer.
  2. Push the branch.
  3. Open a DRAFT PR with `gh pr create --draft --base <pr-base>`, using the
     repo's .github/PULL_REQUEST_TEMPLATE.md. Title references <keys>. The
     description opens with a <=3-sentence paragraph covering what this does
     and why, before any bullets.
  4. Run `/deepreview-branch` against <pr-base> from inside this worktree. Fix
     every blocking correctness finding yourself and re-run the Tier 1
     acceptance checks above before moving on. Leave non-blocking nits
     unfixed — list them in your report instead of fixing them unasked.
  5. Report back.

You may use the in-process Agent tool for your own sub-tasks. You may NOT start
Orca workers — nesting depth is capped and it will fail.

Run every `orca` command (ask, send, worker_done) on its own, optionally piped to
`jq`, with no redirects and no `&&`/`;` chaining. Anything else runs it inside the
sandbox, where it reports "Orca is not running" even though Orca is up. If a send
still fails, put the full report in the PR description and say so in your last
message. The coordinator falls back to reading the PR.

Report in <=3 sentences: outcome (succeeded/failed), the PR URL, the acceptance
evidence, and any non-blocking review nits you left unfixed. Do NOT paste diffs,
logs, review transcripts, or file contents.
If you could not self-fix a blocking finding, say so explicitly rather than
reporting success — that is what authorizes a coordinator re-dispatch (step 9).
If blocked on a decision only the coordinator can make, ask rather than guessing.
```

The last two lines are the token-efficiency mechanism. Worker tool output never
reaches the coordinator; only this summary does. Keep it that way.

## 7. Validation

Validation splits on whether a check needs a **shared resource**. Hermetic checks
run in the worker, in parallel. Anything needing a port, a browser, or an
authenticated session runs here, serially, exactly once.

### Tier 1 — in the worker, parallel

Headless: no ports, no auth, no browser. This is the bucket's `Acceptance`:

- typecheck
- lint (the design-system rules live here)
- unit tests for affected projects
- `/design-analysis` where the repo provides it — programmatic PASS/FAIL, not visual
- the added-suppression grep from step 6

Disable shared build daemons in workers; N worktrees contending on one daemon
produces flaky, confusing failures. In `one-console`, prefix with
`NX_DAEMON=false NX_TUI=false`.

**E2E is not run locally.** CI runs it per PR. Running it again here is slow,
needs the app and auth, and tells you nothing the pipeline will not.

### Tier 2 — not this skill

Browser and Storybook validation are **`/validate-manifest`**, a separate session.
They need one dev server, one login, and one browser, and they get re-run after
review fixes and rebases — none of which fits inside an implementation run whose
context is already spent on dispatch and review.

Do not start a dev server, log in, or drive a browser from this skill. Finish
implementation, then tell the user validation is the next step and hand them the
manifest path.

Mark every UI bucket `Validated: pending` in the manifest so the next session knows
what it owes. A bucket whose changes are not user-visible can be marked
`Validated: n/a` with a one-clause reason.

## 8. Review

Deep review already happened inside the worker's own worktree, as part of step 6
— it ran `/deepreview-branch`, fixed blocking findings, and re-verified before
reporting. Do not re-run `/deepreview-branch` yourself here; that would pull the
full review transcript back into the coordinator's context, which is exactly what
running it in-worktree was for.

Independently re-check each PR for suppressions the worker may have added and not
reported — do not take its word for it:

```bash
git diff $(git merge-base origin/main <branch>)..<branch> \
  | grep '^+' | grep -nE 'eslint-disable|ts-expect-error|@ts-ignore'
```

A hit means the bucket worked around a design-system rule instead of asking. Treat
it as blocking regardless of what the worker reported, and surface the underlying
limitation to the user — that is a design-system gap worth knowing about, not just
a bad diff.

Triage what the worker reported:
- Non-blocking nits it listed → present them to the user; do not fix unasked.
- A worker that reports it could not self-fix a blocking finding, or a suppression
  hit from the grep above → re-dispatch to that bucket's worker (step 9).

A review authorizes synthesis, not coordinator file edits. Route fixes back to the
bucket's worker rather than editing the worktree yourself.

## 9. Re-dispatching to a bucket's worker

One mechanism covers every case where something decided after a bucket's initial
dispatch needs to reach its worker: a review finding it couldn't self-fix, a
change agreed in a parent-session discussion with the user, or a cross-bucket
dependency that surfaced late. Never edit the worktree yourself from the
coordinator — route the change to the owning bucket's worker instead.

- **Orca backend**: reuse the proven terminal — `orchestration worker-start
  --task <newTaskId> --terminal <agentTerminalHandle>`. Recover the handle with
  `worker-show --dispatch <id> --json`.
- **Fallback backend**: send a follow-up prompt to the still-running `Agent`
  fork for that bucket, or start a new `Agent` with `isolation: "worktree"`
  pointed at the existing worktree path if the original fork already exited.

State the change plainly — what changed and why. The worker's protocol block
already tells it not to improvise past what it's given.

## 10. Settle and report

Per settled worker, do exactly one thing before acking: reuse the terminal, retain
it (`worker-retain`), or release it (`worker-release`). Release is post-settlement
cleanup — an accepted `worker_done` authorizes it, nothing else does.

Do not end the turn while this returns rows:

```bash
orca orchestration worker-list --run <runId> --terminal-state reclaimable --json \
  | jq -r '.result.workers[].dispatchId'
```

Write final `Status` and `PR` back into the manifest so a later run resumes cleanly.

Final report — one table, no narration:

| Bucket | Tickets | Status | PR | Review |
|--------|---------|--------|----|--------|

Then state what needs the user: PRs to mark ready, blocking review findings, failed
buckets, and every `Autonomous: no` bucket still waiting on them. Leave worktrees
in place unless the user asks to clean them up.

Close by pointing at **`/validate-manifest <slug>`** for the buckets left
`Validated: pending`, and say plainly that nothing was visually verified in this
session.
