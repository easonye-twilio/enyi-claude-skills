---
name: validate-manifest
description: >-
  Drive a real browser session against implemented work to verify it visually —
  log into the app, walk the affected UI paths, capture screenshots, and record a
  verdict per bucket. Use when the user invokes /validate-manifest, or asks to
  visually verify, browser-check, or "actually look at" work produced by
  /implement-manifest. Runs one dev server and one authenticated session, serially.
---

# Validate manifest

Visual verification of implemented work, in a real browser, against the real app.

This is deliberately a separate session from `/implement-manifest`. Screenshots and
page snapshots are context-heavy, validation gets re-run after review fixes and
rebases, and a broken login should never be confused with a failed implementation.

## Outcome

Every UI bucket carries a recorded verdict — `pass`, `fail` with what was wrong, or
`unverified` with why — written back into the manifest. Screenshots exist for every
path walked. A verdict is never inferred from the diff; it comes from a rendered
page someone can look at.

Safe failure: `unverified` is an honest, acceptable result. A guess is not.

## 1. Load the target

Takes a manifest path or slug (`~/.claude/manifests/<repo-name>/`), and also works
without one — given a branch or PR, validate that alone. Being usable outside the
manifest flow is the point; this is the skill you re-run after fixing review notes.

From a manifest, select buckets with `Validated: pending`. Skip `n/a` and anything
already `pass` unless the user asks for a re-run or the branch moved since.

If nothing is pending, say so and stop.

## 2. Decide what actually needs a browser

Not every bucket does. Route by what the diff touched:

- **Design-system libs** (in `one-console`: `libs/console-ds`, `libs/ds-react`) →
  Storybook. Components render in isolation and need **no login**.
- **Application modules** (`console-app-modules/**`) → the running app, logged in.
- **Neither** → no browser. Mark `n/a` and move on.

Storybook is only worth starting when the design system actually changed. Do not
boot it for application-only work.

## 3. One server, one session

Check before starting anything — reuse what is already running rather than adding
a second instance:

```bash
lsof -i :5173   # app dev server
lsof -i :9001   # storybook
```

**Exactly one authenticated session at a time.** Concurrent logins as the same user
can invalidate each other, which produces failures that look like app bugs. Never
parallelize this step, and never open a second session to "save time."

For the browser itself, follow the environment rule in CLAUDE.md: inside an Orca
session use Orca's browser CLI (`orca tab list --json`, reusing an open tab before
creating one); otherwise chrome-devtools MCP or `/screenshot-changes`. If a
navigation redirects to a Twilio auth page, resolve the environment from the
redirect hostname and use the matching credentials file, per the documented
two-step login. Do not improvise a login flow or hardcode credentials into
commands.

Extra tabs are the same failure mode as extra logins — close anything you opened
for a bucket as soon as you are done with it (see step 5), so at most one tab is
ever alive at a time.

`orca screenshot --json` does not write a file — it returns the PNG inline as
base64 in `result.data`, and there is no `--out`/`--save-path` flag. Decode it
yourself (e.g. `... | jq -r '.result.data' | base64 -d > <path>.png`) and write
it to the target screenshot path from step 5/6 — don't assume the file exists
just because the command exited 0.

## 4. Validate the stack tip

Dependent buckets are stacked, so **the tip of a stack already contains every
change beneath it** — check out the tip and walk all of their paths in one session
rather than booting the server once per bucket. Independent buckets each need their
own checkout; batch them serially against the same running server where the app
supports a rebuild without a restart.

State the tradeoff when you take it: a stack-tip pass proves the combination
renders, not that each PR stands alone. Call that out for any bucket merging on its
own schedule.

## 5. Walk the paths

Use **`/screenshot-changes`** — it derives affected UI paths from the diff instead
of making you enumerate them, and handles the navigation and interaction steps.
Override its default in-repo `screenshots/<date>-<desc>/` location: when running
under a manifest, tell it to save into
`~/.claude/manifests/<repo-name>/<slug>/screenshots/<bucket-key>/` instead, so
nothing lands in the working tree and there is nothing to gitignore. Without a
manifest (a bare branch/PR target), its default location is fine.

Per bucket, cover:
- the golden path the ticket describes
- the states a diff will not show you: empty, loading, error, long content
- anything the bucket's `Change` field explicitly promised

Check the browser console while you are there. A clean-looking page throwing
errors is a fail, not a pass.

Against a Figma mockup, compare deliberately — spacing, token usage, states — and
report mismatches as findings rather than silently accepting them.

When you are done with a bucket's paths, close every tab you opened for it before
moving to the next bucket — keep exactly one tab alive at a time, per step 3.

## 6. Record verdicts

Write back into the manifest per bucket:

```
- Validated: pass | fail | unverified
- Evidence: <screenshot paths under manifests/<slug>/screenshots/<bucket-key>/, paths walked>
- Notes: <what broke, or what could not be reached and why>
```

For a `fail`, dispatch the fix back to the bucket's branch rather than patching it
here — this session's job is the verdict, not the repair. `/implement-manifest`
owns re-dispatch.

## 7. Report

Close the last remaining browser tab before reporting — no tab should stay open
once validation is done.

One table: bucket, what was checked, verdict, screenshot path.

Then, plainly: what you could not verify and why. This repo has no
visual-regression tooling, so every `pass` here is a judgment an agent made, not a
test that passed — say so rather than implying coverage that does not exist.
