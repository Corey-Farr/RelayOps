# Implementation and verification ledger

RelayOps is being built against the supplied master requirements. Completion claims
require executed checks; implementation alone is not validation.

## Work streams

- Backend: durable PostgreSQL queue, ingestion, authentication, control plane,
  workers, telemetry, incidents, policies, migrations and behavioral tests.
- Frontend: authenticated operational console, real API actions, unit and browser tests.
- Infrastructure: local Compose stack, signature-verifying fault sink, bootstrap,
  smoke tests, monitoring, CI and benchmarking.
- Integration: security review, real PostgreSQL validation where possible,
  documentation, repository hygiene and final measured evidence.

## Environment

Initial environment: Windows, Python 3.13.1, Node 22.13.1, npm 10.9.2.
Docker and PostgreSQL were not on PATH at task start. An isolated native PostgreSQL
17.11 instance was started on loopback port 56483. Docker-specific validation
remains unavailable and must be reported separately.

## Executed checks

- Native Alembic migration and administrator/demo bootstrap succeeded.
- Native smoke passed against API, signed receiver and three independent worker
  processes: readiness, actual successful delivery, persisted HTTP 503 attempt,
  retry recovery and metrics availability.
- Backend: 37 pytest tests passed against the dedicated PostgreSQL test database.
  Coverage includes concurrent idempotent ingestion, atomic rollback/capacity,
  competing claims, lease recovery/fencing, retries/redrive, pause/failover,
  incident deduplication, auth/CSRF/key revocation and policy promotion/rollback.
- Backend Ruff and mypy passed after worker nullability/resource fixes.
- Frontend: 13 Vitest tests passed; TypeScript checking and production build passed.
  Tests cover authentication, navigation, filtering, detail rendering, forms,
  errors/empty/loading states, incident acknowledgement and policy confirmation.
- npm install completed with zero reported audit vulnerabilities. `.npmrc` records
  the peer-resolution workaround needed for the installed npm dependency graph.

These checks do not establish Docker image execution, hosted CI, exported traces,
browser end-to-end success or benchmark capacity. Those remain separate gates.

## Verification pending

- Broader crash/shutdown, security, policy and incident behavioral coverage
- Requirement-by-requirement feature audit and remaining implementation
- Browser end-to-end operation and screenshots
- Monitoring/Compose configuration validation
- Measured benchmark and incident evidence
- Security and documentation reconciliation

## Subsequent hardening evidence

- Added a durable dispatch-intent journal and pre-I/O fencing; unknown outcomes
  remain visible after crashes. Repeated expired claims are bounded by policy,
  and redrive grants a fresh retry cycle without rewriting historical attempts.
- All 40 backend tests passed after this change; Ruff and mypy passed.
- Frozen migration DDL replaces the original migration's mutable model import.
  Fresh migration upgrade, full downgrade and re-upgrade passed on a separate
  native PostgreSQL database. The existing native demo also upgraded successfully.
- The restarted native stack passed signed-delivery / 503-retry-recovery smoke.
- Event filters now execute before database pagination. A further PostgreSQL
  test passed for status, offset, date, project, destination and sorting behavior.
- A real Playwright delivery/outage/recovery flow passed previously. It must be
  rerun after the latest API/UI changes before final screenshot publication.

## Remaining scope audit (not completion claims)

- Review every master requirement against implementation, particularly the full
  destination editor/health/test-event flow, role-aware UI, user administration,
  overview summaries, pool activity/failover evidence and policy comparisons.
- Exercise sustained threshold-crossing incidents and acknowledgement/resolution,
  timeout/rate-limit/latency scenarios and bounded graceful shutdown.
- Review login-rate-limit storage, production destination/DNS boundary, validation,
  tracing context propagation, telemetry freshness and secret handling.
- Validate all launch/CI/monitoring configurations possible without Docker; do not
  label container builds, Grafana queries or exported Jaeger traces as executed.
- Reconcile docs and API contract with final behavior, regenerate real screenshots,
  rerun appropriate checks, inspect repository hygiene and deliver final report.
