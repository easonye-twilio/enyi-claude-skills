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
- `make terraform-fmt` when `.tf` files changed
- Specs: `make lint` and `make breaking` in `specs/` when protos changed

**maestro-domain** (Java + Go):
- Java: `mvn spotless:check`, `mvn checkstyle:check`, `mvn test`
- Go services: per-service `make verify test`
- `make lint-openapi` when OpenAPI changed

**agent-connect-domain** (Go):
- `make test` (runs `go test ./...` inside the Dockerfile build stage)

## Validation kinds (shared resource, serial)

| Kind | memora-domain | maestro-domain | agent-connect-domain |
|---|---|---|---|
| local-stack | `make up` (compose + LocalStack) | `make local` | not yet available |
| api | `scripts/api-tests/*.sh <local\|dev\|stage\|prod>` | `ijhttp -e <env> -v requests/http-client.env.json requests/<file>.http` | not yet available |
| component | Temporal `MemoraDomainTestSuite` via `services/common/test-worker` | `services/test-worker` | not yet available |
| dev-deploy | `dev-deploy` PR label → Buildkite → Harness; track with the repo's `dev-deploy` skill | CI-only (`make git-create-and-push-dev-branch` force-pushes; never run locally) | none — no dev-only path; `main` deploys to every environment |
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
- `gh` and other network commands need `dangerouslyDisableSandbox` (TLS cert error
  inside the sandbox).
- Check live state (Jira, PR, deploy) before trusting the manifest — it can be stale.
- Env-var/override PRs are separate from code PRs.

## Evidence

Query text plus the result rows or numbers it returned, deploy execution URLs, and the
running version observed. A screenshot is optional, never required.

## Teardown

`make down` for a local stack you started. Deployed dev changes stay; record what was
deployed.
