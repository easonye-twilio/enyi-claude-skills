---
name: standup
description: Builds your daily standup digest — collects what you actually did since the last weekday across Jira, GitHub (PRs you authored AND reviewed), Slack, local git commits, and your calendar, then synthesizes it into Yesterday / Today / Blockers and writes it into your Obsidian daily note. Use this whenever the user mentions standup, a daily update, "what did I do yesterday", "prep my update", catching up before a scrum call, or wants a summary of their own recent work activity — including when they just say "standup" with no other context.
---

# Standup Digest

Turn a day of scattered activity into three bullet lists you can read aloud at standup.

Collection is the easy part; there are usually 40+ raw events and a useful standup update is
three to five bullets. The work is **compression with provenance**: cluster by ticket or theme,
drop the noise, and keep an anchor (ticket key, PR URL, commit sha, Slack permalink) on every
line so you can jump to the thing if someone asks.

## The lookback window

"Yesterday" means **since the last weekday**, so a Monday run covers Friday rather than Sunday.
`scripts/collect.sh` computes this date and prints it in `window.since`. Use that same date for
the Jira, Slack, and calendar queries — a mismatched window is how Friday's work goes missing
from a Monday update.

The window runs from `since 00:00` to now, which deliberately includes anything done this
morning before standup.

## Step 1 — Run the collector

```bash
<skill-dir>/scripts/collect.sh
```

`<skill-dir>` is this skill's base directory; substitute it as an absolute path.

Invoke it directly rather than as `bash collect.sh`. Sandbox exclusions match on the program
being run, so the direct form can be excluded as `collect.sh` while the `bash ...` form cannot
— see the sandbox note below.

It emits one JSON object with the deterministic sources: the window, local git commits across
every checkout under `~/dev/src/github.com/*/*` and worktree under `~/dev/wt/*`, and three
GitHub PR searches (authored, reviewed, commented).

Pass `--since YYYY-MM-DD` to override the window, e.g. after time off.

**A failed source is reported, not silently emptied.** Check the `errors` array before reading
the data. An empty `prs_authored` with an error present means "GitHub was unreachable," which is
a completely different fact from "you opened no PRs" — say so in the digest rather than
presenting a quiet day.

**Sandbox note:** inside the Bash sandbox, `gh` cannot verify the proxy's TLS certificate, so
every GitHub search fails with `tls: failed to verify certificate` and the digest silently loses
most of its content. Seeing those errors in the `errors` array means the collector ran sandboxed
— rerun it with `dangerouslyDisableSandbox: true` rather than reporting an empty day.

The durable fix is a sandbox exclusion for `collect.sh` (settings `sandbox.excludedCommands`,
where `gh:*` and `git:*` already live), which is why the script is invoked directly rather than
through `bash`. Once that entry exists the daily run stops prompting.

## Step 2 — Fill in the sources the shell can't reach

Jira, Slack, and the calendar live behind MCP tools. Query them with the `since` date from
step 1. Run these concurrently; they are independent.

| Source | Query | Why it earns its place |
|---|---|---|
| Jira | `jira-inator:jira-search` with `assignee = currentUser() AND updated >= "<since>"` | status transitions are the spine of the update |
| Slack | `slack_search_public_and_private` with `from:<@U03RB2QHSV6> after:<since-1d>` | decisions and unblocks that never touch a PR |
| Slack mentions | search the bare string `<@U03RB2QHSV6>` | threads waiting on you — these are usually blockers |
| Calendar | `list_events` for the window | meetings are context, and "I was in interviews all afternoon" is a legitimate standup line |

Slack's `after:` is date-exclusive, so pass the day *before* `since` to include `since` itself.

If a source returns nothing, that is a real and reportable result. Do not backfill a plausible
accomplishment from memory of the repo or from an older ticket — a digest that invents work is
worse than a short one, because you will say it out loud to your team.

## Step 3 — Synthesize

Cluster everything by ticket key or theme first, then write the bullets. One bullet per *thread
of work*, not per event: four commits, a PR, and two Slack messages about the same ticket are one
bullet, not seven.

**Yesterday** — what actually moved. Keep authored work and review work in separate groups;
reviewing five PRs is real contribution but reads as a lie if it's mixed in with work you wrote.

Be skeptical of the review list specifically. `--updated` catches *any* recent activity on a PR,
including somebody else's comment on something you reviewed and forgot about weeks ago, so a
run can easily return eight "reviewed" PRs for two days of actual review. Cross-check
`updatedAt` against the window and against the PR's state: a PR merged well before `since` that
merely got a comment yesterday is not review work you did. When you can't tell whether you
acted in-window, say "commented on" rather than "reviewed," and prefer under-claiming — you are
about to say this to the people who were on those PRs with you.

**Today** — a projection, not a query result. Derive it from tickets still In Progress, PRs
awaiting your action, and anything left mid-flight yesterday. Mark it as a draft; the user
knows their day better than the data does.

**Blockers** — only from concrete signals: PRs with changes requested, tickets in a Blocked
status, your own Slack questions that nobody answered, failing CI. If there's no signal, write
`None` and move on. An invented blocker wastes the team's time.

Use this structure:

```markdown
## Yesterday's Accomplishments
- **TICKET-123** — shipped the highlight + pend-on-close behavior; PR open for review ([#16771](url))
- Reviewed 3 PRs on one-console: [#16643](url), [#16676](url), [#16524](url)

## Today's Goals
- Address review feedback on #16771
- TICKET-456: reopen the 4 remaining PRs

## Blockers/Issues
- None

## Notes
- 2 meetings yesterday: sprint planning, 1:1

---
*Generated: <timestamp> · window: since <since>*
```

The headings are the skeleton, not a quota — a section with nothing real in it gets `None`
rather than filler. `## Notes` is for context that isn't an accomplishment or a plan: meetings
that ate the day, someone being out, a decision made in a thread.

## Step 4 — Write it to the vault

One file per standup, named for the day, in the vault's standup folder:

```
/Users/easonye/Documents/Twilio_Notes/Daily Standup/YYYY-MM-DD.md
```

Note the underscore in `Twilio_Notes` — this is the real vault path from Obsidian's own
registry, and a plausible-looking `Twilio Notes` with a space silently writes nowhere useful.

Use the exact section structure from step 3: `## Yesterday's Accomplishments`,
`## Today's Goals`, `## Blockers/Issues`, `## Notes`, then a `---` rule and a
`*Generated: <timestamp> · window: since <since>*` footer.

**Rerunning the same day must not clobber the user's own edits.** They may open the note,
rewrite a bullet, and ask for a refresh an hour later. So when today's file already exists,
replace the content under the three generated headings and leave `## Notes` — and anything they
added by hand — untouched. If their edits under a generated heading would be lost, say what
you're about to overwrite before you do it.

Finally, **print the digest to the terminal too**, always, regardless of whether the file wrote
cleanly. The user is about to speak, not to open Obsidian.

**If the write fails** with `Operation not permitted`, there are two possible causes and they
have different fixes, so don't guess:

- **The Claude sandbox.** Writes to `~/Documents` need the vault path in settings
  `sandbox.filesystem.allowWrite`. Until that entry exists, write with
  `dangerouslyDisableSandbox: true`. Sandboxed *reads* of the vault already work, so a failure
  that affects only the write is this one.
- **macOS privacy protection (TCC).** Orca needs Documents access under System Settings →
  Privacy & Security → Files and Folders. TCC is evaluated at process start, so a fresh grant
  only takes effect in a new session. A read that fails too points here.

Either way, don't fail quietly: write the file to `~/standup/YYYY-MM-DD.md` so the day isn't
lost, print the digest, and say which of the two gates blocked it.
