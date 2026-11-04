# Profile: cn-domain

Repos: memora-domain, maestro-domain, agent-connect-domain

Cloud-native domain repos built on the shared foundation Makefile. Read the repo's own
CLAUDE.md first where one exists — it wins over this file.

## Hermetic checks (worker, parallel)

**memora-domain** (Go) — there is no root `go.mod` and no root `fmtchk` target. Every
building block is its own module: a service (`services/<svc>` or nested, such as
`services/recall/<svc>`) or a library under `libs/`. For each changed file, find its
nearest `go.mod` and run from that directory:
- `go vet ./...` and `golangci-lint run`
- `make fmtchk` only if that module's own `Makefile` defines it; otherwise `test -z "$(gofmt -l .)"` (`gofmt -l` exits 0 even when it lists files; empty
  output is the pass condition)
- `CN_INCLUDE_ONLY_MAKEFILE_PATHS="<dir relative to the repo root>" make test` from the
  repo root, where `<dir>` is the nearest ancestor of the change that has a `Makefile`
  (some modules, such as `libs/clients/go/clients/*`, have none). With no Makefile, run
  `go test ./...` in the `go.mod` directory. Unscoped `make test` runs every building
  block, so always scope it, and treat "no building blocks matched" as a setup error,
  not a pass.
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
| local-stack | `make up` (compose + LocalStack) | `make local` (stops any running local environment first: check for one and ask before restarting) | not yet available |
| api | `scripts/api-tests/*.sh <local\|dev\|stage\|prod>` — `prod` only for `get-*` and `list-*` | `ijhttp -e local -v requests/http-client.env.json requests/<file>.http` — never `prod`. `local` only: `authToken` exists only for `local` and there is no private env file, so `dev`/`stage` calls cannot authenticate; mark those `unverified` | not yet available |
| component | Temporal `MemoraDomainTestSuite` via `services/common/test-worker` | `services/test-worker` | not yet available |
| dev-deploy | `dev-deploy` PR label → Buildkite → Harness; track with the repo's `dev-deploy` skill. **`manual`**: the label changes the shared dev environment, so the user applies it (the coordinator only after explicit confirmation); `make dev-deploy` is a break-glass path | none (CI-only): `make git-create-and-push-dev-branch` force-pushes the dev branch; never run it locally | none — no dev-only path; `main` deploys to every environment |
| deploy-status | Harness MCP, `beacon deploys <svc> --env <env> --since 1d` | Harness MCP | Harness MCP; ECS service status |
| observe | Grafana MCP (metrics), ClickHouse `otel_twlo.otel_logs` (logs) | Grafana MCP, ClickHouse | CloudWatch / ClickHouse logs for the service |

Prefer the Grafana MCP over WebFetch for dashboards and queries.

**Local stacks are machine-global, not per worktree.** memora's compose project is
named `memora` with fixed container names, so `make up` from a bucket worktree replaces
a stack started from another checkout, and `make down` removes it. maestro's `make local`
stops any running local environment first. Before either, look for a running stack
(`docker ps --filter label=com.docker.compose.project=memora`; for maestro, its running
services) and read its working directory (`docker inspect` label
`com.docker.compose.project.working_dir`). Reuse it only if that directory is inside the
bucket's worktree; otherwise ask the user before replacing it.

`get-*` and `list-*` against `prod` return real customer data. Prefer `dev` or `stage`;
if `prod` is needed, ask first, use `list-stores`/`get-store` or counts, and never paste
response bodies into `Evidence`.

**Never send a mutating request to `prod`.** In memora, only `get-*` and `list-*` scripts
may run against `prod`; `create-*`, `patch-*`, `delete-*`, `import-profiles.sh`,
`recall.sh` (a POST) and the k6 scripts in `scripts/api-tests/load/` write data. Every
maestro `requests/*.http` file contains POST (some also PUT or DELETE) and `ijhttp` runs
the whole file, so none of them runs against `prod`; do not write an ad-hoc GET-only file
for it either. Run mutating checks against `local`, `dev`, or `stage`, and make any prod
check a read-only query.

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

Tear down a local stack only if this session started it: memora `make down`, maestro
`make stop` (maestro has no `down` target). Deployed dev changes stay; record what was
deployed.
