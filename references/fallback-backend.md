# Fallback backend (no Orca)

Detail for `implement-manifest` step 5. Read it only when step 3 did not find Orca ready.

Same buckets, in-process. Transition ticket(s) to In Progress (step 2), then for each
ready bucket:

1. **Create the worktree yourself, from the PR base.** Do not use the `Agent` tool's
   `isolation: "worktree"`: it branches from the coordinator's HEAD with an auto-generated
   branch name, so a stacked bucket would not sit on its parent, and a later resume could
   not find the branch.

   Put worktrees inside the repo, in `.worktrees/`, so the sandbox lets workers write
   there (it only allows writes under the working directory). Keep them out of `git status`
   by adding `.worktrees/` to `.git/info/exclude`.

   ```bash
   git worktree prune                # forget worktrees whose directory was deleted
   git fetch origin <pr-base>        # needs dangerouslyDisableSandbox; stop if it fails
   git worktree add --no-track -b <branch> .worktrees/<branch with "/" replaced by "-"> origin/<pr-base>
   ```

   Run these from `git rev-parse --show-toplevel`, and write the exclude entry to
   `$(git rev-parse --git-common-dir)/info/exclude`. The worktrees are still visible to
   tools that ignore git excludes (in one-console, add `.worktrees` to `.nxignore`, or the
   project graph sees duplicate projects). Two branch names that differ only in `/` versus
   `-` would collide on the path; stop if the path exists for another branch.

   `--no-track` matters: without it the new branch's upstream is `origin/<pr-base>`, and a
   bare `git push` or `git pull` would target the base (`main`, or the parent bucket's
   branch). `<branch>` and `<pr-base>` come from the manifest; a stacked bucket's
   `<pr-base>` is its parent's branch, so start it only after the parent has pushed.

   If the branch already exists (a resumed run whose worktree was removed), never recreate
   it from the base. `git fetch origin <branch>` first (sandbox disabled; stop if it
   fails), then check `git show-ref --verify --quiet refs/heads/<branch>`: a local branch →
   `git worktree add <path> <branch>`; only on the remote →
   `git worktree add --no-track -b <branch> <path> origin/<branch>`. If both exist, use the
   one that is ahead. If neither the branch nor a worktree exists (a crash before the first
   push), this is a fresh first dispatch.
2. **Claim the bucket** before launching. Write `Worktree: <absolute path>` and
   `Dispatch: —` first (this clears any id or `pending` left from an earlier Orca run, or
   resume would treat the bucket as an Orca worker), and `Status: dispatched` last, so a
   crash mid-claim leaves the bucket `pending`. Use `manifest.py set`, see step 1.
3. **Dispatch with `Agent`, no `isolation`,** and set `model` explicitly per bucket. Start
   the prompt with the worktree contract, then the step 6 task spec:

   ```
   Agent(subagent_type: "general-purpose", model: "sonnet",
         description: "<bucket title>",
         prompt: "Your worktree is <absolute path>, on branch <branch>. Your working
                  directory is NOT that worktree. Run every shell command as
                  `cd <absolute path> && ...` (the directory does not persist between
                  calls), give file tools absolute paths inside it, and never touch any
                  other checkout. Push with `git push -u origin <branch>`, open the PR
                  with `gh pr create --head <branch> ...`, and run the suppression check
                  with the branch argument. `git fetch`, `git push` and `gh` fail inside
                  the sandbox (TLS error): run them with the sandbox disabled. You have no
                  `ask` command and no Orca: where the spec says to ask, or to send
                  `worker_done`, instead stop and end your message with `STATUS: failed
                  — needs decision: <question>`. Run the review as
                  `/enyi-claude-skills:deepreview-branch origin/<pr-base> --worktree
                  <absolute path>`: it does not inherit your `cd`. Tell any other
                  sub-agent to run git as `git -C <absolute path>` for the same reason.\n\n
                  <same task spec as step 6>")
   ```

Launch an entire wave in one message so buckets run concurrently. As each result
arrives, verify it (step 8), write `Status`, `PR`, and `Notes`, and transition its
tickets to In Review (step 2). Then proceed to the next wave. Everything else — task
spec, PR handling, review — is unchanged.

**Limits.** A bucket's `Agent` does not survive a coordinator restart and writes no
`Dispatch:`, so a resumed run (step 1) treats it as not running and finds its work through
the branch, its worktree, and the PR. A finished `Agent` cannot be messaged; re-dispatch
(step 9) starts a new one in the same worktree. Run one coordinator per manifest: a
second session cannot see the first one's `Agent`s and would put two workers in one
worktree.
