# Profile: cn-domain

Repos: memora-domain, maestro-domain, agent-connect-domain

Cloud-native domain repos built on the shared foundation Makefile. Read the repo's own
CLAUDE.md first where one exists — it wins over this file.

## Hermetic checks (worker, parallel)

**memora-domain** (Go):
- `go vet ./...`
- `make fmtchk`
- `golangci-lint run`
- `make test` — scope with `CN_INCLUDE_ONLY_MAKEFILE_PATHS="services/<x>" make test`
- `make terraform-fmt-check` when `.tf` files changed (`make terraform-fmt` rewrites files; use it only to fix a failure)
- Specs: `make lint` and `make breaking` in `specs/` when protos changed

**maestro-domain** (Java + Go):
- There is no root `pom.xml`. Run Java checks per module, from the module directory
  (e.g. `services/conversations-service`): `mvn spotless:check`, `mvn checkstyle:check`,
  `mvn test`
- Go services: per-service `make test`, plus `make verify` where the service defines it
  (voice-adapter, messaging-adapter); check the service Makefile first
- `make lint-openapi` exists only in `services/conversations-service`; run it there when
  OpenAPI changed

**agent-connect-domain** (Go):
- `make test` (runs `go test ./...` inside the Dockerfile build stage)

## Suppressions

Globs: `*.go` `*.java`
Patterns: `//nolint` `@SuppressWarnings` `// CHECKSTYLE:OFF`

Worker rule (copy into the task spec):

Do not add `//nolint`, `@SuppressWarnings`, or `// CHECKSTYLE:OFF` to make a linter pass.
If a rule cannot be satisfied, report it as a finding and `ask` the coordinator rather
than suppressing it.

## Validation kinds (shared resource, serial)

| Kind | memora-domain | maestro-domain | agent-connect-domain |
|---|---|---|---|
| local-stack | `make up` (compose + LocalStack) | `make local` (stops any running local environment first) | not yet available |
| api | `scripts/api-tests/*.sh <local\|dev\|stage\|prod>` | `ijhttp -e local -v requests/http-client.env.json requests/<file>.http` (`local` only: `authToken` exists only for `local` and there is no private env file, so `dev`/`stage` calls cannot authenticate; mark those `unverified`) | not yet available |
| component | Temporal `MemoraDomainTestSuite` via `services/common/test-worker` | `services/test-worker` | not yet available |
| dev-deploy | `dev-deploy` PR label → Buildkite → Harness; track with the repo's `dev-deploy` skill. **`manual`**: the label changes the shared dev environment, and `make dev-deploy` is a break-glass path | CI-only. **`manual`**: `make git-create-and-push-dev-branch` force-pushes the dev branch; never run it locally | none — no dev-only path; `main` deploys to every environment |
| deploy-status | Harness MCP, `beacon deploys <svc> --env <env> --since 1d` | Harness MCP | Harness MCP; ECS service status |
| observe | Grafana MCP (metrics), ClickHouse `otel_twlo.otel_logs` (logs) | Grafana MCP, ClickHouse | CloudWatch / ClickHouse logs for the service |

Prefer the Grafana MCP over WebFetch for dashboards and queries.

**Merging is never a validation step.** In agent-connect-domain the orchestrator deploys
`main` to dev, stage, and prod, so a merge is a production release, not a check.

## Preflight

Check presence by name only — `[ -n "$VAR" ]`, `test -f <path>`, `command -v <tool>`.
Never print a value and never read `.env` files.

- AWS SSO: `aws sts get-caller-identity --profile <profile>` (memora: `memora-dev`)
- Twilio creds for `api` checks: `TWILIO_ACCOUNT_SID_<ENV>`, `TWILIO_AUTH_TOKEN_<ENV>`
- Grafana MCP authenticated (re-auth with `/mcp` when expired)
- Harness MCP authenticated, or `beacon` installed — otherwise deploy completion can
  only be inferred from the running version, and the verdict must say so
- Temporal Cloud access for `component` checks on dev

## Gotchas

- **ClickHouse query shape.** Wide queries time out on the prod datasource. Use the
  fast shape and keep the window narrow:
  `WHERE TimestampTime >= now() - INTERVAL 10 MINUTE AND ServiceName = '<svc>' AND
  ServiceVersion LIKE '<ver>%' AND Body = '<exact message>'`. Use the `ServiceVersion`
  column, not `ResourceAttributes[...]`; avoid `Body LIKE '%…%'`.
- **Always filter `DeploymentEnv`.** The prod datasource also holds ephemeral-stack logs.
- **Traffic timing.** Some behavior only appears under real load (memora's :00/:30
  bursts); dev does not reproduce it. Write those as `wait` checks, not `auto`.
- **agent-connect-domain ingress is VPC-only.** Deployed services cannot be curled from
  a laptop; verify through Harness/ECS status and logs.
- `gh`, `git push`, and calls to the specific hosts a check needs (Harness, Grafana,
  ClickHouse, the target environment) hit a TLS cert error inside the sandbox. Retry
  those with `dangerouslyDisableSandbox` once they fail; do not disable the sandbox for
  other commands up front.
- Check live state (Jira, PR, deploy) before trusting the manifest — it can be stale.
- Env-var/override PRs are separate from code PRs.

## Evidence

Query text plus the result rows or numbers it returned, deploy execution URLs, and the
running version observed. A screenshot is optional, never required.

## Teardown

`make down` for a local stack you started. Deployed dev changes stay; record what was
deployed.
