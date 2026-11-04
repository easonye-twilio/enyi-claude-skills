# one-console UI routing

Detail for `tickets-to-manifest` step 2b. Read it when the repo is `one-console` and a
bucket involves page or UI work.

**In `one-console` specifically**, page and UI work is owned by `/implement-page`
(which itself invokes `/implement-ui-pattern` when given a Figma URL). Route to
`/implement-page`, not `/implement-ui-pattern` — the latter is only correct for a
pattern-only ticket with no page assembly.

These skills have **interactive gates that an unattended worker cannot clear**.
Resolving them here, in the foreground, is the point of this step:

- `/implement-ui-pattern` Step 2 short-circuits when every pattern already exists
  in console-ds (no 🔄 variations, no ❌ missing). That early-exit is exactly the
  autonomous/interactive boundary.
- Any 🔄 or ❌ pattern triggers a Design Systems review checkpoint whose required
  option is "document requirements and exit." No coordinator can approve a new
  console-ds pattern, so no `ask`/`reply` round-trip resolves it.
- `/implement-page` Step 1.5.4 **always** gates on `AskUserQuestion` before Step 2,
  even on the pre-specified migration path.

So for each UI bucket, do the gap analysis now. Have the scoping subagent run the
same read-only searches that skill prescribes — `ls libs/console-ds/src/`,
`ls libs/ds-react/src/{atoms,molecules,organisms}`, grep for the pattern type —
against the ticket's Figma decomposition. Do not invoke the skill to do this; you
do not own its steps and replaying them here would drift.

Then classify:

- **All patterns exist** → `Autonomous: yes`. Capture the Step 1.5 architectural
  decisions (page structure, route URLs, data-layer reuse, code to reuse vs.
  write) into the manifest's `Architecture:` block and get the user to approve
  them at the step 6 gate. That approval is what lets the worker skip the
  `AskUserQuestion`.
- **Any 🔄 or ❌ pattern** → `Autonomous: no`, with the reason. These are *not
  dispatched*. They run in the foreground with you.

A bucket with no Figma URL cannot use `/implement-ui-pattern` at all — that skill
hard-requires one. Either attach the mockup or mark the bucket `Autonomous: no`.

**Why this gap analysis is the load-bearing step.** An agent that needs a pattern
the design system does not have will reach for a `className` and an
`eslint-disable` to get unblocked — which passes locally and then breaks the PR
pipeline on the DS-suppressions gate. The cause is a missing pattern, not a
careless agent, so catching it here is the actual fix. Every ❌ you find now is a
suppression that never gets written.

Do not paper over a gap by widening a bucket's scope or loosening its constraints.
Record it, mark the bucket non-autonomous, and surface it as a design-system gap
the user needs to resolve with the DS team.
