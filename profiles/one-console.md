# Profile: one-console

Repos: one-console

## Hermetic checks (worker, parallel)

Prefix every Nx command with `NX_DAEMON=false NX_TUI=false` — N worktrees contending
on one daemon produces flaky, confusing failures.

- typecheck, lint (the design-system rules live here), and unit tests for affected projects
- `/design-analysis` where it applies — programmatic PASS/FAIL, not visual
- the added-suppression grep from `implement-manifest` step 6

E2E is not run locally. CI runs it per PR.

## Validation kinds (shared resource, serial)

Route by what the diff touched:

- **storybook** — `libs/console-ds`, `libs/ds-react`. Port 9001. Components render in
  isolation and need no login. Only worth starting when the design system changed.
- **app** — `console-app-modules/**`. Port 5173, logged in.
- Neither → no browser; the bucket is `Validated: n/a`.

Browser tooling, dev-server reuse, and the two-step Twilio login: read
`~/.claude/references/one-console-browser.md`. Do not improvise a login flow or
hardcode credentials into commands.

Walk paths with `/screenshot-changes`; it derives affected UI paths from the diff.
Under a manifest, tell it to save into the evidence directory rather than its default
in-repo `screenshots/` location.

Per bucket cover the golden path, the states a diff will not show (empty, loading,
error, long content), and anything `Change` promised. Check the browser console — a
clean-looking page throwing errors is a fail. Against a Figma mockup, compare spacing,
token usage, and states deliberately and report mismatches as findings.

## Preflight

- `lsof -i :5173` / `lsof -i :9001` — reuse a running server rather than starting a second
- `test -f libs/common-e2e/.env.dev` / `.env.stage` for the environment you will hit.
  Check presence only; never print contents.

## Gotchas

- **One authenticated session and one tab at a time.** Concurrent logins as the same
  user invalidate each other and look like app bugs. Close every tab you opened for a
  bucket before moving to the next; close the last one before reporting.
- `orca screenshot --json` returns the PNG inline as base64 in `result.data`; there is
  no `--out` flag. Decode it yourself
  (`... | jq -r '.result.data' | base64 -d > <path>.png`) and don't assume the file
  exists because the command exited 0.
- No visual-regression tooling exists, so every browser `pass` is an agent's judgment,
  not a test. Say so in the report.

## Evidence

Screenshots per path walked, plus console errors observed (or "none").

## Teardown

Close tabs. Leave a dev server running only if it was running before you started.
