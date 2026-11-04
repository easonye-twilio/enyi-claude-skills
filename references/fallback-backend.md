# Fallback backend (no Orca)

Detail for `implement-manifest` step 5. Read it only when step 3 did not find Orca ready.

Same buckets, in-process. Transition ticket(s) to In Progress (step 2), then
create worktrees with git, dispatch with `Agent` using `isolation: "worktree"`,
and set `model` explicitly per bucket:

```
Agent(subagent_type: "general-purpose", model: "sonnet",
      isolation: "worktree",
      description: "<bucket title>",
      prompt: "<same task spec as step 6>")
```

Before launching, write each bucket's `Status: dispatched` to the manifest; once an
`Agent` returns, write the worktree path it reports to `Worktree:`. The branch name is
what a later resume relies on, since `isolation: "worktree"` worktrees can be cleaned
up automatically.

Launch an entire wave in one message so buckets run concurrently. As each result
arrives, verify it (step 8), write `Status`, `PR`, and `Notes`, and transition its
tickets to In Review (step 2). Then proceed to the next wave. Everything else — task
spec, PR handling, review — is unchanged.
