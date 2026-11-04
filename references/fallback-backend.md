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
   git fetch origin <pr-base>        # needs dangerouslyDisableSandbox; stop if it fails
   git worktree add --no-track -b <branch> .worktrees/<branch with "/" replaced by "-"> origin/<pr-base>
   ```

   `--no-track` matters: without it the new branch's upstream is `origin/<pr-base>`, and a
   bare `git push` or `git pull` would target the base (`main`, or the parent bucket's
   branch). `<branch>` and `<pr-base>` come from the manifest; a stacked bucket's
   `<pr-base>` is its parent's branch, so start it only after the parent has pushed.

   If the branch already exists (a resumed run whose worktree was removed), never recreate
   it from the base: use `git worktree add <path> <branch>` for a local branch, or
   `git worktree add --no-track -b <branch> <path> origin/<branch>` for one that exists
   only on the remote.
2. **Claim the bucket** before launching: `Status: dispatched` and `Worktree: <absolute
   path>` (use `manifest.py set`, see step 1).
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
                  with the branch argument. Run the review as
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
(step 9) starts a new one in the same worktree.
