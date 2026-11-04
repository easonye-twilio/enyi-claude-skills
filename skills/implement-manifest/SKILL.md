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

Every bucket in the manifest ends the run in one of these states, and the manifest file
is updated to match. No bucket is silently skipped.

- `done` with a draft PR URL.
- `failed` with the reason.
- **Blocked**: never dispatched, because it is `Autonomous: no` or because a bucket it
  depends on (directly or through the stack) is not `done`. Its manifest `Status` stays
  `pending`; the final report shows `blocked: <reason>` (`needs foreground run`, or
  `blocked by <bucket>`). A blocked bucket is a result, not an omission.
- **Unresolved**: left `dispatched` because liveness or the PR could not be checked
  (Orca not ready, `gh` failed), reported with that reason. Never guess past it.

The turn ends with a per-bucket table and the review results.

`Status` takes exactly these values (the `ALLOWED` set in `scripts/manifest.py`):
`pending`, `dispatched`, `done`, `failed`, `unknown`. A worker's `STATUS: succeeded` is
not a bucket status: it becomes `done` only after step 8 verification passes, and
`STATUS: failed` becomes `failed` once the re-dispatch cap is spent (step 8). `unknown`
is only found in older manifests; this skill does not write it. Treat it like a `failed`
bucket: list it and ask before retrying.

Safe failure: preserve the worktree and report the bucket as `failed` or `unknown`.
Never delete a worktree to clear an error.

`<plugin-root>` below means the directory two levels above this skill's base directory
(it holds `scripts/`, `profiles/` and `references/`). Always substitute it as an absolute
path: a worker's cwd is its worktree, so a relative path would not resolve there.

## 1. Load the manifest

Take a path, or a slug resolved against `~/.claude/manifests/<repo-name>/`. If
several exist and none was named, list them and ask.

Parse buckets, dependencies, branch bases, per-bucket models, ticket keys,
`Autonomous`, `Guidance`, and `Architecture`. Buckets already `done` are skipped, except a `done` bucket whose `Validated` is `fail`
(re-entry, below). If every bucket is `done` and none is in re-entry, say so and stop.

**Older manifests** may lack `Profile:`, `Run:`, `Worktree:`, `Dispatch:`, or numbered
checks. Infer the profile from the git remote's repo name (the exact-match rule in
`/validate-manifest` step 1; ask on none or several), treat a missing `Run:` as "no reattach
information", and treat free-text `Acceptance` as one unstructured check — say so in
the report rather than pretending it was itemized. Older fields often carry prose
after the value (`Status: done (2026-10-08, …)`, `Autonomous: no. <reason>`); the
first word is the value. Ignore sections the skill doesn't own (status logs, rollout
steps); never rewrite them.

**`gh` and every git command that talks to the remote (`fetch`, `push`, `ls-remote`)
fail inside the sandbox** (TLS certificate error), so run them with
`dangerouslyDisableSandbox`. A failed call tells you nothing about the remote: only a
`gh` call that succeeded and returned no rows means "no PR", and a failed `git fetch` is
a stop condition, not a warning (a stale `origin/<ref>` silently gives a wrong base).

**`Worktree:` holds an Orca worktree id (`<repoId>::<path>`) on the Orca backend and an
absolute path on the fallback backend.** Either way, find a bucket's worktree by its
branch with `git worktree list`, and never create a second worktree for a branch.

**Resume `dispatched` buckets before dispatching anything.** A `dispatched` bucket was
in flight when a previous coordinator stopped. The worktree and the Orca run may both be
gone; the branch and PR are what survive. A worker opens its PR *before* it runs
`/deepreview-branch`, so a PR proves the work started, not that it finished. For each
bucket, in this order:

1. **Is a worker still running?** Decide per bucket, not per manifest: a run can mix
   backends. (Commands are in `../../references/orca-backend.md`.)
   - The bucket has a `Dispatch:` id → it was an Orca worker. With Orca ready, reuse the
     manifest's `Run:`, never create a new one (it would orphan live workers), and
     `worker-list --run <runId>` for that id. A live worker → rejoin the wait loop and
     stop here for this bucket. If the Run no longer exists, say so and ask before
     creating a new one. With Orca not ready, liveness is unknown: leave the bucket
     `dispatched`, tell the user to start Orca, and do not look at the PR or re-dispatch.
   - `Dispatch: pending` → the Orca backend claimed the bucket and the coordinator
     stopped before recording the dispatch id, so a worker may be running unrecorded.
     Handle it like the case above (Orca not ready → leave it `dispatched`), but find the
     worker in the Run's `worker-list` by task title (`--task-title` is the bucket
     title), counting only live workers (earlier attempts reuse the title). One live
     match → write its `Dispatch:` and rejoin the wait loop. Several → stop and ask. None
     → not running.
   - `Dispatch: —`, or no `Dispatch:` field (older manifests) → it was an in-process
     agent, which does not survive a coordinator restart; treat the worker as not running.
     Whatever `Worktree:` holds, `Dispatch:` alone says which backend claimed the bucket.
2. **Not running → look for the PR:**
   `gh pr list --head <branch> --state all --json url,isDraft,state` (`--state all`: a
   merged or closed PR must show up too).
   - The call failed → unknown. Leave the bucket `dispatched` and say why.
   - Several PRs can come back for one branch. Use the open one if there is one,
     otherwise the most recent `MERGED`; treat `CLOSED` only when it is the sole result.
   - A `MERGED` PR → record `done` with the PR URL and note that it merged outside this run.
     A `CLOSED` one → record `failed` ("PR closed unmerged") and tell the user.
   - An open PR whose description carries a report block titled `Attempt <n>` with `n`
     equal to the bucket's current `Redispatches` plus `Fixes` (use only that block:
     earlier attempts are stale), `STATUS: succeeded`, and a `CHECKS:` record covering every acceptance ID
     → run the step 8 verification on it; record `done` only if it passes.
   - An open PR without such a record, or no PR at all → the worker did not finish. Reuse
     the worktree holding `<branch>` and re-dispatch there (step 9); do not start over.
     If neither the branch nor a worktree exists (a crash between the claim and the first
     push), this is a fresh first dispatch: follow the backend's normal path.
     A resume-driven re-dispatch (the worker died with no report) does not increment
     `Redispatches` or `Fixes`.

**Re-entry: `failed` and `done` + `Validated: fail` buckets.** A `failed` bucket is never
retried silently. A bucket with `Validated: fail` — `failed` (set by `/validate-manifest`)
or `done` (how older runs recorded it) — is a validation fix: re-dispatch it (step 9)
with the failure from `Evidence` as the change, unless `Fixes` has already reached 2;
then record `Status: failed` and `Validated: unverified` ("fix cap reached") so this
rule stops matching, and tell the user. `/validate-manifest` marks `fail` only on the
bucket that owns the failure, so a bucket blocked by another's failure is not here. Any
other `failed` bucket: list it and ask the user whether to retry.

**Write state as it happens, not at the end.** Re-read the manifest and edit only the
field you are changing — never rewrite the whole file; `/validate-manifest` may be
editing it from another session.
Use `<plugin-root>/scripts/manifest.py set <manifest> <bucket> <field> <value>` for
each change (the Bash sandbox cannot write under `~/.claude/manifests`: if it reports
`Operation not permitted`, run it with `dangerouslyDisableSandbox`) and `<plugin-root>/scripts/manifest.py status <manifest>` to read state back; it rewrites one
field and leaves every other line alone.

**`Autonomous: no` buckets are never dispatched.** They carry an interactive gate
no worker and no coordinator can clear — typically a Design Systems review for a
new or extended console-ds pattern. List them for the user to run in the
foreground, and treat their dependents as blocked until the user says otherwise.
Say this up front, not after the fan-out.

The same goes for `pending` dependents of a `failed` or `unknown` bucket: never dispatch
them, and report them as blocked (see Outcome). They stay `pending`. A dependent already
`dispatched` is left to finish; one already `done` keeps its state, and the report notes
it sits on a failed parent.

## 2. Ticket status

Transition each bucket's ticket(s) via the `jira-inator:jira-ticket-updater`
skill, silently — no confirmation needed:

- **In Progress** right before that bucket is dispatched.
- **In Review** once its worker's report has passed verification (step 8) and the PR URL
  is known — not when the worker merely reports done.

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

Read `../../references/orca-backend.md` (relative to this skill's base directory)
and follow it. It covers run creation, guardrail checks, worktree and worker
dispatch, the wait loop, and stall recovery. Keep every `orca` command bare:
`orca … | jq …` and nothing else.

## 5. Fallback backend (no Orca)

Read `../../references/fallback-backend.md` (relative to this skill's base directory)
and follow it. It covers worktree creation with git from the PR base, `Agent` dispatch
into that worktree, and result collection.

## 6. The task spec

Substitute `<plugin-root>` (defined at the top) as an absolute path in the spec below.

Every worker gets the same five fields, verbatim from the manifest, plus the
protocol block. The coordinator adds nothing of its own to the manifest's fields (profile
rules were already applied when the manifest was planned; see Tier 1). This is the whole
contract; it is why worker output never needs to flood back into the parent.

```
Target:      <from manifest>
Change:      <from manifest>
Constraints: <from manifest>
Ownership:   This worktree only. Do not edit files outside the listed targets.
Attempt:     <the bucket's Redispatches plus Fixes, 0 on the first dispatch>
Acceptance:  <numbered checks from manifest>

Each acceptance check is a command and the result that counts as passing. Run every
one and record, per check ID, pass or fail with the evidence: exit code, test count,
the named test that passed. A check you could not run is a fail, not a skip.

<IF Mutation-check: yes>
For each new test that covers the change: break the code it covers, run the test
and confirm it FAILS, then restore the code, confirm the test passes again, and
confirm `git diff` shows no leftover mutation. A test that never fails proves
nothing. Report the mutation evidence under the check it supports.
</IF>

<IF the bucket has Guidance, i.e. it is set and not `none`:>
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

<The profile's `## Suppressions` worker rule, verbatim. If the profile has no such
section, omit this rule and step 2 below, and tell the user the check is not configured.>

Branch is already checked out and based on <pr-base>. When acceptance passes:
  1. Commit following this repo's conventional-commit style; reference the
     ticket key(s) <keys> in the subject or footer.
  2. Verify you introduced no new suppressions. The check reads committed changes,
     so it runs after the commit:
       <plugin-root>/scripts/check-suppressions.sh <plugin-root>/profiles/<name>.md origin/<pr-base>
     Exit 1 means a hit on an added line: a blocking failure. Remove it and amend, or
     report `failed` with the rule you could not satisfy and why. A bucket that lands
     with a suppression is worth less than one that stops and asks. Exit 2 is a setup
     error: report it in STATUS rather than skipping the check. Re-run it after any
     fix in step 5.
  3. Push the branch.
  4. Open a DRAFT PR with `gh pr create --draft --base <pr-base>`, using the
     repo's .github/PULL_REQUEST_TEMPLATE.md. Title references <keys>. The
     description opens with a <=3-sentence paragraph covering what this does
     and why, before any bullets.
  5. Run `/enyi-claude-skills:deepreview-branch origin/<pr-base>` from inside this
     worktree. Fix every blocking correctness finding yourself and re-run the Tier 1
     acceptance checks above before moving on. Commit each fix, re-run the suppression
     check, and push, so the remote branch carries the reviewed code (a dependent
     bucket and `/validate-manifest` both read it). Leave non-blocking nits unfixed —
     list them in your report instead of fixing them unasked.
  6. Append the report block below (STATUS/PR/CHECKS/NITS) to the PR description under
     the heading `Attempt <n>` (<n> is the Attempt value in your task), so a coordinator
     that lost your message can still verify the work. Then report back.

`git fetch`, `git push` and `gh` fail inside the sandbox (TLS certificate error): run them
with the sandbox disabled.

You may use the in-process Agent tool for your own sub-tasks. You may NOT start
Orca workers — nesting depth is capped and it will fail.

Run every `orca` command (ask, send, worker_done) on its own, optionally piped to
`jq`, with no redirects and no `&&`/`;` chaining. Anything else runs it inside the
sandbox, where it reports "Orca is not running" even though Orca is up. If a send
still fails, put the full report in the PR description and say so in your last
message. The coordinator falls back to reading the PR.

Report in exactly this shape, one line each, and nothing else:
  STATUS: succeeded | failed — <one-clause reason if failed>
  PR: <url>
  CHECKS: A1 pass (<evidence>); A2 pass (<evidence>); ...
  NITS: <non-blocking review nits left unfixed, or "none">
Do NOT paste diffs, logs, review transcripts, or file contents. Anything longer
belongs in the PR description.
If you could not self-fix a blocking finding, report STATUS: failed and say so —
that is what authorizes a coordinator re-dispatch (step 9).
If blocked on a decision only the coordinator can make, ask rather than guessing.
```

The report format is the token-efficiency mechanism. Worker tool output never
reaches the coordinator; only these four lines do. Keep it that way.

## 7. Validation

Validation splits on whether a check needs a **shared resource**. Hermetic checks
run in the worker, in parallel. Anything needing a port, a browser, or an
authenticated session runs here, serially, exactly once.

### Tier 1 — in the worker, parallel

Headless: no ports, no auth, no browser, no deploy. This is the bucket's numbered
`Acceptance`, written at planning time from the profile's hermetic checks
(`../../profiles/<name>.md` relative to this skill's base directory). Repo-specific
rules in that section — e.g. disabling a shared build daemon — are applied at planning:
`/tickets-to-manifest` copies profile-wide rules into `Constraints` and bakes per-command
ones into `Acceptance`. Older manifests predate that. Before the first dispatch, read the
profile's hermetic section once; if a profile-wide rule is missing from a bucket's
`Constraints` and `Acceptance`, ask the user whether to add it to the manifest. Never
patch the spec silently, since workers get the manifest's text verbatim. The only profile
text copied into the spec at dispatch is the `## Suppressions` worker rule.

**E2E is not run locally.** CI runs it per PR. Running it again here is slow,
needs the app and auth, and tells you nothing the pipeline will not.

### Tier 2 — not this skill

Everything needing a shared resource — a browser, a dev server, a login, a deploy,
live API calls, real traffic — is the bucket's `Validation`, run by
**`/validate-manifest`** in a separate session. Those checks need one resource at a
time and get re-run after review fixes and rebases, which does not fit inside an
implementation run whose context is already spent on dispatch and review.

Do not start a dev server, log in, deploy, or drive a browser from this skill.

Every bucket with `Validation` checks stays `Validated: pending`; a bucket without
any is `Validated: n/a`, unless the manifest has no profile: then it stays `pending`
and `/validate-manifest` records it as `unverified`.

## 8. Review

Deep review already happened inside the worker's own worktree, as part of step 6
— it ran `/deepreview-branch`, fixed blocking findings, and re-verified before
reporting. Do not re-run `/deepreview-branch` yourself here; that would pull the
full review transcript back into the coordinator's context, which is exactly what
running it in-worktree was for.

**Verify the report rather than redoing the work.** Read the `CHECKS:` line against
the bucket's acceptance list: every check ID must appear with `pass` and concrete
evidence. A missing ID, a `fail`, or evidence that is only an assertion ("tests
pass") means the bucket is not done — re-dispatch (step 9). Do not re-run the checks
yourself; that is the work the evidence exists to save.

**Re-dispatch only when it can change the outcome.** Each bucket gets at most **2**
re-dispatches, counted in its own `Redispatches` field (never in `Notes`: other writes
replace that whole field and would reset the count; never reset it on success). Past the
cap, or when the same check fails the same way twice, record `failed` with the reason
and stop — do not loop.
Some report shapes can never pass, and re-dispatching them just burns the cap:
- An older manifest with unstructured `Acceptance` (step 1) has no check IDs: accept a
  single `CHECKS` entry with concrete evidence.
- A check the worker's sandbox cannot run (it needs a port, a login, or a deploy) is a
  planning mistake: record `failed`, and tell the user the check belongs in `Validation`.
- Judge a check by the result its text names, not by the exit code alone: "no matches
  expected" passes on a clean diff even though `grep` exits 1.

A few claims are cheap to check and costly to get wrong, so check them directly:

```bash
gh pr view <url> --json isDraft,baseRefName --jq '{isDraft, baseRefName}'
```

The PR must still be a draft and target the manifest's `PR base`. A worker that
marked its PR ready or targeted `main` instead of its parent broke the spec — fix the
PR state and record it in `Notes`.

Independently re-check each PR for suppressions the worker may have added and not
reported — do not take its word for it. From any checkout of the repo, using the
bucket's profile:

```bash
<plugin-root>/scripts/check-suppressions.sh <plugin-root>/profiles/<name>.md origin/<pr-base> <branch>
```

Exit 1 means the
bucket added a suppression: treat it as blocking regardless of what the worker
reported, and surface the underlying limitation to the user — a rule the code could
not satisfy without suppression is worth knowing about, not just a bad diff. Exit 2 is a
setup problem (profile missing or without `## Suppressions`, base ref not fetched), not
a finding: fix the setup or tell the user the check could not run; do not re-dispatch.

Triage what the worker reported:
- Non-blocking nits it listed → present them to the user; do not fix unasked.
- A worker that reports it could not self-fix a blocking finding, or a suppression
  hit from the suppression check above → re-dispatch to that bucket's worker (step 9).

A review authorizes synthesis, not coordinator file edits. Route fixes back to the
bucket's worker rather than editing the worktree yourself.

## 9. Re-dispatching to a bucket's worker

One mechanism covers every case where something decided after a bucket's initial
dispatch needs to reach its worker: a review finding it couldn't self-fix, a
change agreed in a parent-session discussion with the user, or a cross-bucket
dependency that surfaced late. Never edit the worktree yourself from the
coordinator — route the change to the owning bucket's worker instead.

Before launching, claim the bucket: increment `Redispatches` (a review or verification
re-dispatch) or `Fixes` (a validation fix), never both, write `Dispatch: pending` (Orca)
or `Dispatch: —` (fallback) so the old, settled id is not mistaken for the new worker,
and then `Status: dispatched`. A crash after this point is caught by the step 1 liveness
check instead of starting a second worker over the first. Write the new `Dispatch:` id as
soon as it is known.

State the change plainly — what changed and why — and append the step 6 protocol block
(the worker's protocol block already tells it not to improvise past what it's given). The
new worker gets a fresh `STATUS`/`PR`/`CHECKS`/`NITS` report, verified by step 8 again.
When that verification passes for a validation fix, set `Status: done` and
`Validated: pending`: the code changed, so the old verdict no longer stands. If the fixed
bucket has `done` dependents, set their `Validated` to `pending` too and tell the user
their branches need a rebase onto the fixed one; stack-tip validation of a child that
lacks the parent's fix proves nothing.

- **Orca backend**: always pass the manifest's own `--run <Run:>` (without it a new coordinator
  gets a new Run, and the wait loop and step 10 never see the worker). `worker-start`
  creates the task from `--spec`, so no task id is needed:
  `orca orchestration worker-start --run <runId> --spec "<change + protocol block>"
  --task-title "<bucket title>" --worktree <worktreeId>` plus either
  `--terminal <handle>` or `--agent claude --keep-open --model <m> --effort <e>`. Workers are started
  with `--keep-open` and released only after their report passes
  (`../../references/orca-backend.md`), so the terminal normally still exists: recover the
  handle with `worker-show --dispatch <id> --json`. If the start is refused or the
  terminal is gone (an exited worker, a resumed run), use the `--agent` form and a fresh
  terminal starts in the same worktree; `worker-release` the old dispatch first, since its
  terminal is not reused. When `Worktree:` holds a path (a bucket first run on the fallback
  backend), pass `--worktree path:<path>` instead of an id. A dispatch whose terminal was
  reused is superseded (see step 10).
- **Fallback backend**: start a new `Agent` the same way as the first dispatch
  (`../../references/fallback-backend.md`), pointed at the existing worktree path. A
  finished `Agent` cannot be sent a follow-up, so every re-dispatch is a new `Agent`.

## 10. Settle and report

Per settled worker, do exactly one thing before acking: reuse the terminal, retain
it (`worker-retain`), or release it (`worker-release`). Release is post-settlement
cleanup — a `worker_done` whose report **passed step 8 verification** authorizes it,
nothing else does. A rejected report keeps its terminal, because step 9 reuses it.

Ignore dispatch ids that are no longer any bucket's `Dispatch:` (superseded by a
re-dispatch on the same terminal; reusing a settled worker's terminal cancels its
automatic release). Workers started with `--keep-open` are not auto-released and are not
`reclaimable`, so also check `--terminal-state retained` the same way, and release what
you do not need. Do not end the turn while either returns other rows:

```bash
orca orchestration worker-list --run <runId> --terminal-state reclaimable --json \
  | jq -r '.result.workers[].dispatchId'
```

Run it again with `--terminal-state retained`.

Every bucket's `Status`, `PR`, and `Notes` should already be written (steps 4–5).
Confirm none is still `dispatched` without a reason, then overwrite the manifest's
`## Handoff` section: one or two lines of state and the exact next step. Overwrite,
don't append — history lives in the bucket fields and PRs, not in a growing log. An
older manifest may have no `## Handoff`: add one at the end of the file (`Updated`,
`State`, `Next` lines, as `/tickets-to-manifest` writes it) rather than skipping the step.

Final report — one table, no narration:

| Bucket | Tickets | Status | PR | Review |
|--------|---------|--------|----|--------|

Status is the manifest value, or `blocked: <reason>` for a bucket never dispatched.

Then state what needs the user: PRs to mark ready, blocking review findings, failed
buckets, and every blocked bucket with what unblocks it (the `Autonomous: no` ones are
waiting on the user). Leave worktrees
in place unless the user asks to clean them up.

Close by pointing at **`/validate-manifest <slug>`** for the buckets left
`Validated: pending`, and say plainly that nothing beyond hermetic checks was
verified in this session.
