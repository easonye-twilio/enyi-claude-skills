---
name: validate-manifest
description: >-
  Verify implemented work against real, shared resources and record a verdict per
  bucket — a browser session, a local stack, API calls, a dev deploy, logs and
  metrics, or a manual phone test, depending on the repo's validation profile. Use
  when the user invokes /validate-manifest, or asks to validate, verify, smoke-test,
  browser-check, or check the deploy of work produced by /implement-manifest, or of a
  single branch or PR. Runs one shared resource at a time, serially.
---

# Validate manifest

Verification of implemented work against the real thing: a running app, a deployed
service, a live Twilio number. Hermetic checks already ran in the workers; this skill
owns everything that needs a shared resource.

This is deliberately a separate session from `/implement-manifest`. Validation output
is context-heavy, it gets re-run after review fixes and rebases, some of it has to
wait for real traffic, and a broken login or expired token should never be confused
with a failed implementation.

## Outcome

Every bucket that owes validation carries a recorded verdict — `pass`, `fail` with
what was wrong, `waiting` with the condition, or `unverified` with why — written back
into the manifest, with evidence per check. A verdict is never inferred from the diff;
it comes from something observed.

Safe failure: `unverified` is an honest, acceptable result. A guess is not.

## 1. Load the target and profile

Takes a manifest path or slug (`~/.claude/manifests/<repo-name>/`), or a branch or PR
with no manifest. Being usable outside the manifest flow is the point; this is the
skill you re-run after fixing review notes.

From a manifest, select buckets with `Validated: pending` or `waiting`. Skip `n/a` and
anything already `pass` unless the user asks for a re-run or the branch moved since.
If nothing is selected, say so and stop.

**Profile.** Use the manifest's `Profile:` header. If absent (older manifests, or no
manifest), pick the profile whose `Repos:` line lists this repo's name. Profiles live
at `../../profiles/<name>.md` relative to this skill's base directory. Read only the
one you need.

No matching profile → do not guess how to boot an unfamiliar system. Mark every
selected bucket `unverified` ("no validation profile for <repo>"), and offer to draft
one with the user.

**Checks.** Each bucket's `Validation:` field lists numbered checks (`V1`, `V2`, …),
each `auto`, `manual`, or `wait`. Older manifests have no `Validation:` field; for
those, and for a bare branch/PR, derive checks from the profile's validation kinds and
the diff, and label every one `(derived)` in the record and the report so nobody
mistakes them for checks agreed at planning time.

## 2. Preflight before anything boots

Run the profile's preflight first, all of it, before starting servers or deploying.
Check presence by name only — `[ -n "$VAR" ]`, `test -f`, `command -v`, an auth status
command. Never print a secret or read a `.env` file.

A failed preflight item makes every check that depends on it `unverified` with the
exact reason ("Harness MCP not authenticated"). Report those up front and run what
remains. Discovering a missing credential halfway through a deploy is the failure
this step exists to prevent.

## 3. One shared resource at a time

Check what is already running and reuse it rather than starting a second instance.
Never parallelize this skill: concurrent logins invalidate each other, two deploys to
one environment race, and a shared Twilio number can only point at one webhook. The
resulting failures look like implementation bugs.

**Validate the stack tip.** Dependent buckets are stacked, so the tip of a stack
already contains every change beneath it — check it out and run all of their checks
in one pass. Independent buckets each need their own checkout, run serially. State the
tradeoff when you take it: a stack-tip pass proves the combination works, not that
each PR stands alone. Call that out for any bucket merging on its own schedule.

## 4. Run the checks

Follow the profile for how each validation kind is run and where its gotchas are.

- **`auto`** — run it, capture the evidence the profile names, compare against the
  check's expected result. Pass or fail is the comparison, not your impression.
- **`manual`** — the check needs a human (calling a phone number, approving a
  billable deploy). List exact steps, ask the user to perform them, and record what
  they report. Never mark a manual check `pass` on your own.
- **`wait`** — the check needs a condition that hasn't happened yet (real traffic, a
  deploy finishing, a burst window). Record the condition and set the bucket
  `Validated: waiting`. Do not poll or schedule; re-running this skill picks it up.

A bucket is `pass` only when every check passed; any `fail` makes it `fail`; otherwise
an outstanding `wait` makes it `waiting`, and anything that could not run makes it
`unverified`.

Evidence goes in `~/.claude/manifests/<repo-name>/<slug>/evidence/<bucket-key>/` under
a manifest — never in the working tree. With no manifest, write it to the session
scratchpad.

**Teardown is part of the outcome.** Whatever the profile says to tear down, tear down
before recording the verdict. A resource left behind is a `fail` even if every check
passed.

## 5. Record verdicts

Re-read the manifest, then edit only these lines of each bucket — never rewrite the
file, since another session may have changed it:

```
- Validated: pass | fail | waiting | unverified
- Evidence: V1 pass — <what was observed, path>; V2 waiting — <condition>; ...
- Notes: <what broke, or what could not be reached and why>
```

Then overwrite the manifest's `## Handoff` section: what was validated, what is
waiting and on what, and the exact command to resume.

For a `fail`, route the fix back to the bucket's branch rather than patching it here —
this session's job is the verdict, not the repair. `/implement-manifest` owns
re-dispatch.

## 6. Report

One table: bucket, checks run, verdict, evidence path.

Then, plainly: what could not be verified and why, what is waiting and on what, and
which verdicts are judgments rather than tests (the profile says where no automated
oracle exists — browser `pass` in one-console, manual phone tests in tac-sdk).
