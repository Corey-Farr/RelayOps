# Implementation and verification ledger

Verified on 2026-10-24 (America/Phoenix). This ledger supersedes earlier milestone
counts. The full requirement mapping is in [REQUIREMENTS](REQUIREMENTS.md).

## Implemented

- FastAPI/PostgreSQL durable event and delivery storage, transactional admission,
  scoped idempotency, bounded backpressure, SKIP LOCKED claims, expiring fenced
  leases, pre-dispatch intent journal and immutable attempt history.
- Asynchronous HTTP workers, HMAC signatures, bounded jittered retries,
  Retry-After, dead letters, history-preserving redrive and graceful draining.
- Three logical regional pools, heartbeat/health controls, pause/resume and
  failover. Stable/candidate delivery policies use deterministic assignment and
  preserve the selected version through retries and rollback.
- React operations console: overview, searchable events and detailed timelines,
  destinations with editing/test/health, dead letters, workers, incidents, demo
  fault lab, policy release controls, projects/API keys and access information.
- Hashed passwords and API keys, encrypted signing secrets, session/CSRF protection,
  role enforcement, input bounds, URL allowlisting, login throttling and audit logs.
- Matured SQL SLO windows, minimum sample gates, configurable incident thresholds,
  incident deduplication/acknowledgement/resolution and paginated history.
- Prometheus metrics, provisioned Grafana dashboard, connected OpenTelemetry traces,
  JSON diagnostics, Docker/CI/release definitions, reproducible locks and runbooks.

## Executed verification

| Check | Result |
| --- | --- |
| Backend pytest against isolated PostgreSQL | 57 passed in 12.43s |
| Backend Ruff lint/format and mypy | Passed; mypy checked 22 source files |
| Frontend Vitest | 19 passed |
| Frontend lint, TypeScript, production build | Passed; bundle warning remains below |
| Real Chromium Playwright | Passed in 9.4s: login, project/destination configuration, actual delivery 200, actual 503, recovery 200, dialog keyboard/focus, mobile navigation/layout |
| Native launcher regression tests | 5 passed |
| Demo receiver signature/fault tests | 4 passed |
| Infrastructure Python lint/format | Passed after final formatting |
| Workflow actionlint | Both workflows passed |
| Migration round trip | Fresh upgrade, downgrade to base and re-upgrade passed; existing native demo upgraded |
| Real smoke | Signed delivery, persisted failed attempt, retry/recovery, three pools and metrics passed |
| Monitoring | Four scrape targets up; Grafana health/provisioning/datasource verified; all 14 dashboard queries executed; linked API/worker traces queried from Jaeger2 |

The integration suite includes concurrent ingestion/claims, atomic rollback,
lease reclaim/fencing, crash ambiguity, bounded repeated crash recovery,
backpressure, SSRF/HMAC/auth/CSRF/roles/key revocation, policy pinning/rollback,
SLO maturity and dual-window gates, incident API/audit/history pagination,
redrive backoff reset, and shutdown drain/cancellation. Destructive fixtures reject
non-test database names and verify the actual engine database before dropping tables.

## Measured and live exercises

The recorded k6 baseline sent 100 requests at 5/s for 20s: 100 accepted and delivered.
Ingestion p50/p95/p99:12.49/24.60/30.03ms; delivery end-to-end p50/p95/p99:
168.64/278.21/304.07ms. This earlier native revision is a reproducibility baseline,
not a final-code capacity or improvement claim. See [PERFORMANCE](PERFORMANCE.md).

`scripts/exercise.py` produced 20 actual 503 failures/dead letters, an automatic
threshold incident, acknowledgement, receiver restoration, 20 successful redrives
and resolution. `scripts/fault_modes.py` verified normal 200, intermittent 500→200,
429 with persisted Retry-After wait, real 2s latency and timeout→recovery.
See [INCIDENT_REPORT](INCIDENT_REPORT.md).

`scripts/failover.py` ran 2026-10-25T05:33:22–05:34:28 UTC: 30/30 events delivered while
us-east was paused; 10 deliveries assigned there completed in the other pools.
The finally block restored the pool and verified all pools healthy. These are
logical processes on one host, not geographic redundancy.

[MONITORING](MONITORING.md) records native Prometheus/Grafana/Jaeger verification.
Committed screenshots were captured from the actual app and visually inspected.

## Environmental and product limits

- Docker is absent: image builds and Compose execution were not run. Native
  PostgreSQL 17.11 exercised the application; Compose pins PostgreSQL 16.11.
- GitHub Actions and release publishing were not executed; no remote/push/public
  deployment occurred. Workflow validation is not a hosted CI success claim.
- Production JS bundle is approximately 709 KB before compression. Build succeeds;
  route splitting is a future optimization, not a claimed implemented feature.
- Accounts are created with the offline CLI; this is not an identity-provider or
  full account-lifecycle administration console. Role enforcement is global to this
  local operator console; API keys are project-scoped.
- Audit/lab overview feeds are bounded recent-history views; incident and event
  history support server pagination. Database history retention needs operational
  policy. Metrics reset when a process restarts; database history remains durable.
- Single PostgreSQL host, local logical regions and single-node trace storage do
  not provide geographic or database high availability. Delivery is at-least-once.
- TLS/egress controls, managed secrets, private observability, backups/restore
  drills and deployment-specific retention/rate-limit controls are prerequisites
  for public deployment. See SECURITY.md and RUNBOOK.md.
