# Profile: tac-sdk

Repos: twilio-agent-connect-python, twilio-agent-connect-typescript, twilio-agent-connect-aws, twilio-agent-connect-microsoft, twilio-agent-connect-google, twilio-agent-connect-python-em, aws-twilio-agent-connect-python, twilio-agent-connect-aws-deploy, aws-twilio-agent-connect-deploy

Twilio Agent Connect SDKs and cloud integrations. Read the repo's CLAUDE.md first.

## Hermetic checks (worker, parallel)

Use the CI commands, not the Makefile shortcuts — the Makefiles lint and type-check a
different scope than CI in several repos.

**Python repos** — common steps: `uv sync --frozen --all-extras --all-groups` (google:
`uv sync --frozen --all-extras`), `uv run pytest`, `uv build`, then install the wheel into
a fresh venv and import it.

| Repo | Lint / format | Type-check |
|---|---|---|
| python | `uv run ruff check .`, `uv run ruff format --check .` | `MYPYPATH=src uv run mypy src/tac getting_started` |
| aws | `uv run ruff check .`, `uv run ruff format --check .` | `MYPYPATH=src uv run mypy src/tac_aws getting_started` |
| microsoft | `uv run ruff check src getting_started tests deploy` (+ `format --check`, same paths) | `MYPYPATH=src uv run mypy --explicit-package-bases src/tac_microsoft getting_started deploy` |
| google | `uv run ruff check src/tac_google getting_started tests` (+ `format --check`, same paths) | `MYPYPATH=src uv run mypy src/tac_google getting_started` |

google supports Python 3.10–3.11 only.

**typescript**: `npm ci`, `npm run lint`, `npm run format:check`, `npm run typecheck`,
`npm test`, `npm run build`. Examples `getting_started/examples/openai` and `chat` are
also linted and type-checked in CI.

The repos' `test_integration.py` / `integration.test.ts` are **mocked**. They are
hermetic checks, not evidence of live behavior.

## Suppressions

Globs: `*.py` `*.ts` `*.tsx` `*.js` `*.jsx` `*.mjs` `*.mts` `*.cts`
Patterns: `# noqa` `# type: ignore` `eslint-disable` `@ts-ignore` `ts-expect-error`

Worker rule (copy into the task spec):

Do not add `# noqa`, `# type: ignore`, `eslint-disable`, `@ts-ignore`, or `ts-expect-error` to make a
linter or type-checker pass. If a rule cannot be satisfied, report it as a finding and
`ask` the coordinator rather than suppressing it.

## Validation kinds (shared resource, serial)

No repo has a live integration or E2E test. Real-resource validation is mostly manual.

- **example** (`manual`) — run a `getting_started` example behind `ngrok http 8000`,
  point the Twilio number and Conversation Configuration webhooks at it, then call or
  text the number. Proof: the agent responds, and the logs show the expected path.
- **deploy** (`manual` unless the user says otherwise; creates billable resources and
  rewires the Twilio number):
  - aws: `make deploy` (CDK) in `deploy/agentcore_aws_lambda`; outputs list webhook URLs
  - microsoft: `make deploy`, then `make configure-twilio` (the only repo that wires
    Twilio automatically). The deploy targets live in
    `deploy/agent_framework_hosted_agents`, not at the repo root
  - google: `make deploy-all` in `deploy/agent_platform/adk`
- **agent-probe** (`auto` once deployed) — google only:
  `deploy/agent_platform/adk/agent/invoke_adk.py` queries the deployed agent directly,
  without Twilio.
- **observe** — CloudWatch log groups (aws), `azd ai agent monitor --session-id <id>`
  (microsoft), `gcloud run services logs read <svc> --project <p> --region <r>` (google),
  or the python `getting_started/examples/features/dashboard` viewer.

For a `manual` check, list exact steps for the user and record the result they
report. Do not pretend to perform it.

## Preflight

Presence by name only; never print values.

- Twilio: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_API_KEY`,
  `TWILIO_API_SECRET`, `TWILIO_PHONE_NUMBER`, `TWILIO_CONVERSATION_CONFIGURATION_ID`
- `command -v ngrok` for `example`
- Cloud auth: `aws sts get-caller-identity` (aws), `az account show` (microsoft), `gcloud auth list` (google)

## Gotchas

- **Integrations pin the core SDK to a PyPI range** (`twilio-agent-connect>=2.x,<3`).
  Validating against an unreleased core change needs a local editable override, which
  `uv sync --frozen` refuses. Record which core version was actually installed.
- CI authenticates through Twilio-internal Artifactory OIDC; locally, public PyPI/npm is
  used instead. A resolution difference is not necessarily your change.
- Python and TypeScript keep 1:1 parity, and each repo has a sync skill for porting
  changes. A parity change should share acceptance checks across both buckets.
- Webhooks must be HTTP POST. Voice is keyed off the number; SMS is keyed off the
  Conversation Configuration.

## Evidence

Command output (exit code, test counts), the installed SDK version, log excerpts with
timestamps, and the user's report for `manual` checks.

## Teardown

Part of the outcome — a resource left deployed is a `fail`, even if every check passed.

- aws: `make destroy` in `deploy/agentcore_aws_lambda` (there is no root target)
- microsoft: `make down` in `deploy/agent_framework_hosted_agents`. It asks for
  confirmation; with no input it prints "Aborted." and **exits 0 while every resource
  stays up**. Have the user run it, or run it where they can answer the prompt, and
  confirm afterwards that the resources are gone (`azd show`, or list the resource
  group). Never pipe `yes` into it or add `--force --purge`: that destroys and purges
  without asking. An exit code of 0 is not evidence of teardown here.
- google: no documented teardown; delete the Cloud Run service, the secret, and the
  reasoning engine by hand, and list them in the evidence
- Restore the Twilio number and Conversation Configuration webhooks to what they were
  before, and record both the old and new values.
