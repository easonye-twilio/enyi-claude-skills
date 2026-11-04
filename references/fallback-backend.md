# Fallback backend (no Orca)

Detail for `implement-manifest` step 5. Read it only when step 3 did not find Orca ready.

Same buckets, in-process. Transition ticket(s) to In Progress (step 2), then for each
ready bucket:

1. **Create the worktree yourself, from the PR base.** Do not use the `Agent` tool's
   `isolation: "worktree"`: it branches from the coordinator's HEAD with an auto-generated
   branch name, so a stacked bucket would not sit on its parent, and a later resume could
   not find the branch.

   ```bash
   git fetch origin <pr-base>
   git worktree add -b <branch> <worktree-path> origin/<pr-base>
   ```

   `<branch>` and `<pr-base>` come from the manifest (a stacked bucket's `<pr-base>` is
   its parent's branch, so start it only after the parent has pushed). `<worktree-path>`
   is an absolute path outside the repo, for example
   `<repo-root>/../<repo-name>-worktrees/<branch with "/" replaced by "-">`. If the
   sandbox denies the write outside the repo, re-run just that command with
   `dangerouslyDisableSandbox`.
2. **Claim the bucket** before launching: `Status: dispatched` and `Worktree: <absolute
   path>` (use `manifest.py set`, see step 1).
3. **Dispatch with `Agent`, no `isolation`,** and set `model` explicitly per bucket. Start
   the prompt with the worktree contract, then the step 6 task spec:

   ```
   Agent(subagent_type: "general-purpose", model: "sonnet",
         description: "<bucket title>",
         prompt: "Your worktree is <absolute path>, on branch <branch>. Run every shell
                  command as `cd <absolute path> && ...` (the working directory does not
                  persist between calls) and give file tools absolute paths inside it.
                  Never touch any other checkout.\n\n<same task spec as step 6>")
   ```

Launch an entire wave in one message so buckets run concurrently. As each result
arrives, verify it (step 8), write `Status`, `PR`, and `Notes`, and transition its
tickets to In Review (step 2). Then proceed to the next wave. Everything else — task
spec, PR handling, review — is unchanged.

**Limits.** A bucket's `Agent` does not survive a coordinator restart and writes no `Run:`
or `Dispatch:`, so a resumed run (step 1) treats it as not running and finds its work
through the branch, its worktree, and the PR. A finished `Agent` cannot be messaged;
re-dispatch (step 9) starts a new one in the same worktree.
