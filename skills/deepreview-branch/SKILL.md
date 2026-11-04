---
name: deepreview-branch
description: Deep code review of all changes on the current branch vs a base branch. Runs 3 parallel reviewers for better coverage. Outputs to chat only — never posts to GitHub.
allowed_tools:
  - Read
  - Grep
  - Glob
  - Bash
  - Task
---

# Deep Code Review - Branch vs Base

Review all changes introduced by the current branch, or the branch in a given worktree (vs a base branch), for bugs that will crash production or create security vulnerabilities. Runs 3 independent reviewers in parallel to catch more issues. **Results are displayed in chat only — nothing is posted to GitHub.**

## Step 1: Parse arguments

Arguments: `[<base-branch>] [--worktree <path>]`.

- **Base branch**: optional positional argument (e.g. `/deepreview-branch develop` or `/deepreview-branch origin/my-feature`). Defaults to `main`. Store it as BASE_BRANCH.
- **`--worktree <path>`**: optional. Review the branch checked out in that git worktree instead of the current directory. Store it as WORKTREE.

If `--worktree` is given:

- Verify it with `git -C <WORKTREE> rev-parse --show-toplevel`; stop and tell the user if it is not a git worktree.
- Run every git command in this skill as `git -C <WORKTREE> ...`.
- Tell each reviewer agent to read files from `<WORKTREE>` (absolute paths) and to run any git command with `git -C <WORKTREE>`. The current directory holds a different branch, so reviewers must not read it.

Without `--worktree`, run git in the current directory as usual.

## Step 2: Get the diff

Find the merge-base between BASE_BRANCH and HEAD, then diff from there. In the commands below, `git` means `git -C <WORKTREE>` when WORKTREE is set:

```bash
git merge-base <BASE_BRANCH> HEAD
```

Then get the full branch diff:

```bash
git diff <MERGE_BASE>...HEAD
```

If the diff is empty, inform the user there are no changes on this branch relative to BASE_BRANCH and stop.

Store the diff output — you'll pass it to the review agents.

Also collect branch context to include in the review (with WORKTREE, add its path and `git -C <WORKTREE> branch --show-current`):

```bash
git log --oneline <MERGE_BASE>..HEAD
```

## Step 3: Spawn 3 parallel bug-finding agents

Use the Task tool to spawn 3 independent bug-finders. Each will analyze the same code but may catch different issues.

**CRITICAL: Use the Task tool with these EXACT parameters. Do NOT use superpowers:code-reviewer or any Skill tool.**

**IMPORTANT: Model Inheritance**
The agents will inherit the model from the parent session. For best results, run deepreview from an Opus session:
```bash
claude --model us.anthropic.claude-opus-4-6
```

**Send ONE message with THREE Task tool calls:**

For each agent:
- `subagent_type`: `general-purpose`
- `description`: `Bug hunter pass [1/2/3]`
- `prompt`: Use the bug-finder prompt below, with the diff and branch context inserted (and, if WORKTREE is set, the worktree-path instruction from Step 1)

### Bug-Finder Prompt (use for all 3 agents)

```
You are a bug hunter. Find bugs that will crash production.

## Branch Context

{{BRANCH_CONTEXT}}

## Critical Checks

### NPE Hunting (MOST IMPORTANT)

For every object dereference (foo.method() or foo.field) in the diff, trace the variable's lifecycle:

1. Where is it declared? Is it null by default?
2. Where is it assigned? What method sets it?
3. Where is it set to null? Look for cleanup methods, error handlers, close()
4. Can another thread null it? Is there a race?

When you find an NPE risk, show the full trace:
- "Variable X is declared null at line A, assigned in method B at line C, set to null in method D at line E, but dereferenced at line F without null check. Race condition: [explain]"

### Resource Leak Hunting

For every resource opened (connection, stream, file, cursor):
- Is there a corresponding close in finally or try-with-resources?
- Can an exception cause the resource to leak?

### Security Issue Hunting

For every external input (request params, headers, API responses, database reads):
- Trace where it flows
- Does it reach a dangerous sink (SQL, HTML, shell, logs, file paths) without sanitization?

Also check for hardcoded secrets, sensitive data being logged, missing auth checks.

### Race Condition Hunting

For shared mutable state:
- Multiple threads accessing without synchronization?
- Check-then-act patterns with gaps?

### Control Flow Analysis

Look for:
- Missing return statements after cleanup/error handling
- Early exits that skip necessary cleanup
- Unreachable code after conditionals

### Architectural Issues

Look for:
- Inconsistent patterns (e.g., mixing two different APIs for the same purpose)
- Removed wrappers or utilities without clear justification

## Output

Return your findings as a JSON array. Each finding is an object:

```json
[
  {
    "severity": "critical|high|medium",
    "path": "exact/file/path.ts",
    "line": 45,
    "title": "Short title (5-10 words)",
    "body": "Detailed explanation. Show variable lifecycle traces for NPEs.",
    "suggestion": "Concrete fix with code if applicable."
  }
]
```

Rules:
- `severity` is required: `critical` (crashes/security), `high` (fix soon), `medium` (fix later)
- `path` and `line` are required when the issue maps to a specific diff location
- `path` must match the diff path exactly
- `line` is the line number in the NEW version of the file (right side of diff)
- For issues spanning multiple lines, also include `start_line`
- For general/architectural issues without a specific line, omit `path` and `line`
- After the JSON block, add a brief text summary (1-2 sentences)

## Key Principles

- Trace, don't scan - actually trace variable lifecycles and data flows
- Show your work - show the full lifecycle trace for NPE risks
- Be specific - include file:line and quote actual code
- Focus on crashes and vulnerabilities, not style

## Code to Review

{{DIFF}}
```

## Step 4: Combine and present results

After all 3 agents complete:

1. Present each bug-finder's findings (label them Pass 1, 2, 3)
2. Note which issues were found by multiple passes (higher confidence)
3. Highlight issues found by only one pass (might be edge cases others missed)
4. Create a combined priority list

Format the output:
```
Deep Code Review — <current branch> vs <BASE_BRANCH>
<N commits reviewed>

🔴 CRITICAL - Must fix before shipping
  - {findings}

🟠 HIGH - Fix soon
  - {findings}

🟡 MEDIUM - Fix later
  - {findings}

---
Pass 1 found X issues
Pass 2 found Y issues
Pass 3 found Z issues

{Consensus analysis}
```

If no issues are found across all 3 passes, report that clearly.
