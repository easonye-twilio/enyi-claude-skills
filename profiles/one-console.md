# Profile: one-console

Repos: one-console

## Hermetic checks (worker, parallel)

Prefix every Nx command with `NX_DAEMON=false NX_TUI=false` — N worktrees contending
on one daemon produces flaky, confusing failures.

- typecheck, lint (the design-system rules live here), and unit tests for affected projects
- `/design-analysis` where it applies — programmatic PASS/FAIL, not visual
- the suppression check (run as in `implement-manifest` step 6; see Suppressions)

E2E is not run locally. CI runs it per PR.

## Suppressions

Globs: `*.ts` `*.tsx` `*.js` `*.jsx` `*.mjs` `*.mts` `*.cts`
Patterns: `eslint-disable` `ts-expect-error` `@ts-ignore`

Worker rule (copy into the task spec):

HARD CONSTRAINT — suppressions are a failure, not a workaround. Do not add an
eslint-disable, ts-expect-error, ts-ignore, or any other suppression to make a
design-system rule pass. Do not add a `className` to escape a design-system limitation.
If the design system cannot express what the design needs, that is a finding to report,
not something to code around. Stop and `ask` the coordinator.

## Validation kinds (shared resource, serial)

Route by what the diff touched; a diff that touches both gets both:

- **storybook** — any lib or module that has stories. The truth is the `stories` globs in
  `apps/storybook/.storybook/main.ts`: `libs/{console-ds,ds-react,ds-icons,ui-primitives,
  ui-icons,forms-core,common-frontend-ui,common-frontend-utils,identity-components,
  talia-shared,account-upgrade,workbench}/src` and `console-app-modules/**/src/**/*.stories.*`.
  Re-read that file rather than trusting this list. Port 9001. Components render in
  isolation and need no login.
- **app** — `console-app-modules/**`, `apps/console-core`, and any other lib or app the
  running console renders without stories (for example `libs/common-frontend`). Port
  5173, logged in.
- Neither (types, config, GraphQL schema, build tooling) → no browser; the bucket is
  `Validated: n/a`. A UI diff must never land here just because its path is not named above.

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

- `lsof -i :5173` / `lsof -i :9001` — a server already listening may have been started from
  another checkout or commit. Reuse it only after confirming its working directory is
  inside the bucket's worktree (`lsof -a -p <pid> -d cwd`; Nx often runs from `apps/...`);
  otherwise stop it if you started it, or ask.
- `test -f libs/common-e2e/.env.dev` / `.env.stage` for the environment you will hit.
  Check presence only; never print contents.

## Gotchas

- **One authenticated session and one tab at a time.** Concurrent logins as the same
  user invalidate each other and look like app bugs. Close every tab you opened for a
  bucket before moving to the next; close the last one before reporting.
- **Screenshots: keep `orca` bare, and keep the payload out of context.** `orca screenshot
  … | jq …` is fine; adding `| base64 -d > file` puts the command back in the sandbox,
  where it fails with `stale_bootstrap`. First look at the shape without the payload:
  `orca screenshot --json | jq -c '.result | del(.data)'`. If it carries a file `path`,
  `cp` that file into the evidence directory in a second command. If the image only
  comes back inline in `result.data` (older CLIs; there is no `--out` flag), saving it
  means pushing megabytes of base64 through the Write tool and risks a truncated PNG:
  do that only for the shots that matter, then `base64 -d` it in a separate command and
  confirm with `file <png>` that it reports PNG image data (size alone does not catch a
  corrupt file). Otherwise record what you saw in `Evidence` and say no image was saved.
- No visual-regression tooling exists, so every browser `pass` is an agent's judgment,
  not a test. Say so in the report.

## Evidence

Screenshots per path walked, plus console errors observed (or "none").

## Teardown

Close tabs. Leave a dev server running only if it was running before you started.
