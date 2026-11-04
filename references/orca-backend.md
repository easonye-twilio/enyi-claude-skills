# Orca backend

Detail for `implement-manifest` step 4. Read it only when step 3 picked Orca.

One Run for the whole manifest:

```bash
orca orchestration run-create --objective "<manifest slug>" --json \
  | jq -r '.result.run.id'
```

Write the id to the manifest's `Run:` header immediately:
`<plugin-root>/scripts/manifest.py set <manifest> manifest Run <id>`
(`manifest` as the bucket name addresses header fields; `<plugin-root>` is defined in
`implement-manifest/SKILL.md`).

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
  --agent claude --keep-open --model <bucket model> --effort <bucket effort> --json \
  | jq -c '{task:.result.taskId, dispatch:.result.dispatchId, state:.result.state,
            agent:.result.launch.effective.agent, model:.result.launch.effective.model}'
```

Compare `launch.effective` against what you requested. If they differ, say so —
never report a model from the requested arguments alone.

Right after each dispatch, write the bucket's `Status: dispatched`, `Worktree:`, and
`Dispatch:` to the manifest. This is what lets a later run resume instead of
dispatching the bucket twice.

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
- `worker_done` → validate the payload's `taskId`/`dispatchId` against the bucket you
  expect, then verify the report (step 8). Everything after that depends on the verdict:
  - **Accepted** → write `Status: done`, `PR`, and `Notes` (nits left unfixed) to the
    manifest (and `Validated: pending` if this was a validation fix), transition its ticket(s) to In Review (step 2), and only then
    `orca orchestration worker-release --dispatch <id> --json`.
  - **Rejected, attempts left** → re-dispatch (step 9) into the same terminal. Do not
    move the ticket and do not release: release removes the terminal step 9 reuses.
  - **Rejected, cap reached** → write `Status: failed` with the reason in `Notes` (and
    `Validated: unverified` if it was a validation fix), then release.

Ack, then wait again. A timeout or empty batch is a **checkpoint, not a failure** —
keep waiting. After three consecutive empty waits:

```bash
orca orchestration worker-list --run <runId> --include-remote --json \
  | jq -c '.result.workers[]|{dispatch:.dispatchId, liveness:.projection.liveness,
            next:.projection.nextAction}'
```

Act on `projection.nextAction` when it carries argv. Only positive proof of exit
(`exited` liveness, or a transcript whose last turn sent no `worker_done`)
authorizes stop or abandon — load the orchestration skill's `references/recovery-and-cleanup.md` (not a file in
this plugin) at that point via `orca skills get orchestration --reference ...`, not before.

When a wave settles, unblock dependents and dispatch the next wave.
