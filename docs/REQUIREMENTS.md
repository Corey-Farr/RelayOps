# Requirements audit

Audit date: 2026-10-24. This maps the supplied 22-section build specification to
the repository. It is a completion checklist, not a claim that every runtime gate
has passed. Source inspection proves implementation; it does not prove an
unexecuted deployment works. File paths below are repository-relative.

Final verification: 57 backend tests, 19 frontend tests, five launcher tests and
four receiver tests passed. Frontend lint/type/build and real Chromium checks
passed. See IMPLEMENTATION.md for measurements and deployment limitations.

## Completion gates

| Gate | Evidence |
| --- | --- |
| Monitoring | Four scrape targets up, Grafana healthy, all 14 expressions executed, API/worker/retry trace chains queried; MONITORING.md |
| Tracing | Jaeger 2.22.0 persistent Badger configuration validated and run natively |
| Browser | Real destination PATCH, event delivery,503 recovery, focus trap and mobile layout verified |
| Incidents | test_incident_api covers 205-record history pagination/filtering and action/timeline/audit persistence |
| Documentation | Ledger/SLO updated; real screenshots committed and embedded |
| Pool continuity | 30/30 delivered during us-east pause, 10 reassigned; pool restored healthy |
| Repository | Main incremental commits, no remote; final status/count in completion report |
| Limitations | Docker/Compose execution and hosted Actions unavailable; documented conditional checks |

## 1–3. Product, stack and organization

| Requirement | Implementation/evidence | Assessment |
| --- | --- | --- |
| Real asynchronous infrastructure product | API, PostgreSQL queue, separate workers, receiver, operational React console | Implemented; runtime gates below |
| No fake metrics/backend/placeholders | Overview SQL aggregates; workers measure actual attempts; UI reads API via TanStack Query | Inspected; real browser review passed |
| Neutral infrastructure product copy | README and inspected product/docs use infrastructure terminology | Product and documentation text inspected |
| Correctness/security/tests/local launch/incremental Git | Queue/security/test modules, launchers, meaningful Git history | Implemented; clean-tree check accompanies final commit |
| Python ≥3.12, FastAPI/Pydantic2/SQLAlchemy2/asyncpg/Alembic/httpx | `backend/pyproject.toml`, `requirements.lock`, migrations | Present; PostgreSQL native integration used |
| React/TS/Vite/Tailwind/Query/Recharts | `frontend/package.json`, lockfile, source | Present |
| Docker/Prometheus/Grafana/OTel/Jaeger/Actions | Compose, infrastructure and workflows | Present; native Jaeger2 verified |
| pytest/asyncio/PostgreSQL/Vitest/RTL/Playwright/k6/profiling | Backend/frontend tests, benchmark scripts | Present; executed results require final ledger |
| Reproducible dependency locks | Python requirements lock, npm package lock | Present |
| Small monorepo, no unnecessary broker/cloud | Backend/frontend/receiver/infra/scripts/benchmarks/docs | Present; main API and UI page modules are relatively large, not separate microservices |

## 4. Durable delivery engine

| Requirement | Authoritative source/evidence |
| --- | --- |
| Event ID/project/type/payload/UTC creation/idempotency/derived status | `models/__init__.py`, `services/serialization.py`, `schemas.py` |
| Scoped idempotency uniqueness and payload conflict | Event unique constraint, `services/ingestion.py`; `test_atomic_idempotency_conflict`, concurrent ingestion test |
| Atomic event/jobs, commit before response | Ingest adds both in one transaction; API commits before 201; rollback and backpressure atomicity tests |
| Payload bound/request validation | API body middleware, Pydantic schema, canonical byte check in ingestion; invalid schema test |
| Multiple enabled subscribed destinations | Ingestion selects project subscriptions; destination scope tests |
| pending/leased/retry_wait/delivered/dead_letter | Delivery model and queue transition logic; integration/recovery tests |
| Append-only dispatch/outcome history and unknown crash outcomes | `DispatchStart`, `Attempt`, migration 0002; pre-I/O journal/fencing tests |
| Attempt number/worker/region/times/duration/status/category/safe error/trace | Attempt fields, `workers/runner.py`, serialization; duration uses monotonic clock |
| Mixed event outcomes | `services/policy.py:event_status`; mixed-status test |
| PostgreSQL competing consumers | `queue.claim` uses `FOR UPDATE SKIP LOCKED`; concurrent claim test |
| No DB transaction during HTTP | Dispatch reads metadata then closes session before HTTP; completion opens separate transaction |
| Lease expiration/owner/version fence/reclaim | Claim/begin_dispatch/complete; lease fencing and crash journal tests |
| At-least-once/destination dedupe documented | README, ARCHITECTURE, SECURITY |
| Bounded exponential jitter, timeout, max attempts, Retry-After | Policy/runner/queue code; classification/backoff/dead-letter tests |
| Retry network/timeout/408/429/5xx, terminate ordinary4xx | `retryable`; parametrized tests; live fault script |
| Safe redrive preserves history and selected policy | Queue redrive and policy pin tests; real incident exercise script |
| Persisted retry schedule | `next_attempt_at`, retry transaction |
| Queue admission/backpressure guidance | Serialized advisory lock/capacity check; 429 Retry-After; concurrency test |
| Bounded worker tasks/HTTP pool | Worker semaphore/task set and httpx limits; no memory work queue |
| Bounded graceful stop and recoverable unfinished leases | `test_shutdown.py` covers drain/no additional claim and deadline cancellation/reclaim |
| UTC persisted times/monotonic local durations | Model `now()`, timezone-aware columns, runner monotonic timer |

## 5–6. Security and logical regions

| Requirement | Implementation/evidence and boundary |
| --- | --- |
| Admin bootstrap, Argon2 login/logout | Bootstrap, users CLI, auth routes, login tests |
| Sessions, HttpOnly/SameSite/Secure, CSRF | Hashed session cookies, expiry and CSRF dependency; Secure in production; auth tests |
| Admin/operator/viewer authorization | Security dependencies plus role tests; frontend role controls verified by unit tests |
| Authentication throttling | Bounded expiring per-process IP buckets; throttle/capacity tests; shared edge limiter required for replicas |
| Scoped hashed API keys, revoke/rotate | API key digest/scope checks; rotation is create replacement then revoke old; revocation test |
| Audit of administrative changes | `Audit` records in routes/users CLI; settings audit view |
| No plaintext DB passwords/API keys | Password hash/API digest; signing secret encrypted with Fernet |
| No routine secret leakage | Serialization excludes ciphertext/digests; key/signing secret reveal only on creation; generated-secret scan and real screenshot review completed |
| HMAC headers/canonical format/verifier | Runner signature(timestamp + dot + raw bytes); SECURITY example and demo sink verification tests |
| Production HTTPS/approved hosts/unsafe literals/no redirects | `security/crypto.py`, httpx client; SSRF parametrized tests |
| DNS rebinding boundary | Explicit approved-host fallback, documented trusted DNS/egress obligation; no claim that pre-resolution alone is safe |
| Demo-only named HTTP target; no arbitrary load/fault endpoints | Exact configured receiver origin/path; lab validates all enabled destinations; benchmark localhost restriction |
| SECURITY document | Present with operational deployment obligations and limitations |
| Three independent logical pools | Compose worker-us-east/eu-west/ap-southeast, same runner with region env |
| Heartbeat ID/region/time/version/capacity/state | Worker model, heartbeat routine and API |
| Pause/resume/deterministic selection/failover | Pool routes, stable identifier hashing, healthy-owner claim predicate; PostgreSQL test |
| No physical-region claim; documented guarantees/timing | README/ARCHITECTURE/TRADEOFFS/RUNBOOK; live failover evidence in IMPLEMENTATION.md |

## 7–10. Observability, incidents, lab and policies

| Requirement | Implementation and evidence |
| --- | --- |
| Accepted/attempt/success/failure/retry/dead/backpressure counters | `observability/telemetry.py`, ingestion/worker/queue updates |
| Depth/in-flight/heartbeat gauges; activity/throughput | Heartbeat gauges; rates of actual attempt/success counters; worker API activity |
| HTTP and E2E histograms/p50/p95/p99 capability | Histograms with bounded buckets, dashboard quantile expressions |
| Low-cardinality labels; separate worker scraping | Region labels; Prometheus explicit targets for each worker; all four native targets up |
| FastAPI + worker OTel with persisted parent context | FastAPI instrumentation, Event.trace_context inject/extract, dispatch header injection |
| Ingest/persist/claim/dispatch/retry/complete spans | Named spans in API/ingestion/queue/runner; safe identifiers, not payload |
| Export to included backend + trace investigation docs | OTLP exporter/config and tracing README/RUNBOOK; connected traces queried in native Jaeger2 |
| Automatically provisioned real Grafana queries | Datasource/dashboard provisioning; throughput/outcomes/p95/p99/queue/retry/dead/regional panels; all fourteen native expressions executed successfully |
| Configurable99%/30s matured24h SLO | Config + SQL aggregation against Event.created_at; tests for maturity/deadline/current state/no data |
| Separate terminal success/latency/error budget/burn | Overview aggregates; frontend displays separate measures |
| Dual-window/sample-minimum alerts | Shared observation timestamp, 24h/1h windows, configurable burn threshold/minimum; dedicated tests |
| Incident source/severity/component/times/evidence/timeline/status | Incident model and API/detail view; acknowledgement/resolution actor and time live in timeline |
| Deduplication/acknowledgement/reopen | Fingerprint unique constraint/advisory monitor lock; tests preserve acknowledgement/current evidence and reopen resolved condition |
| Configurable detection | Burn, dead-letter and queue fraction thresholds; unavailable affected pool detection; queue condition is capacity pressure, not a sustained-growth claim |
| Authorized acknowledge/resolve/audit | Routes implemented; live script uses them; test_incident_api verifies action/timeline/audit persistence |
| Six real receiver fault modes | `demo-sink/server.py`, `scripts/fault_modes.py`, `scripts/exercise.py`; observed report in INCIDENT_REPORT |
| UI fault controls/generation/intensity/pause/normal/reset/recovery | Controls page uses real API; reset restores normal behavior and preserves events/history |
| Seeded/persisted safe exercise | Seeded payload generation, fault mode control, audit records; local-only checks |
| Versioned timeout/maxattempt/backoff/canary policy | Policy/control models and policy API; worker concurrency remains environment-driven |
| Stable/candidate/percentage/history/promote/rollback | Policy routes and UI; audit records actor/change/time |
| Stable deterministic assignment/pinned retry version | Hash selection and persisted policy_id; rollout/pin/retry tests |
| Measured comparison/sample sufficiency | SQL terminal counts/E2E latency/sample flags; dedicated policy comparison test; frontend test added |
| No binary deployment claim | UI/docs clearly describe delivery policy changes |

## 11. Frontend

| Page/standard | Source inspection |
| --- | --- |
| Overview all requested measures | Operations page: success/events/backlog/p95/p99/incidents/workers/chart/regions/recent events from API |
| Event Explorer filters/sort/pagination | Server filters type/date/status/project/destination/ID before offset/limit; UI controls and tests |
| Event detail | Metadata, safe React JSON text, deliveries, attempts/unknown dispatches, errors/traces/redrive |
| Destinations | Create/edit/subscriptions/health/recent failures/test/disable; one-time signing secret; backend scope tests |
| Worker pools | Freshness/count/state/activity/assigned depth/health/failovers and pause/resume |
| Incidents | Status/severity filters, evidence/timeline/actions; server filtering and offset/limit pagination tested past200 rows |
| Reliability Lab | Real safe scenario/generation/reset/pool controls/history/live metrics |
| Release Policies | Versions/differences/percentage/outcomes/promotion/rollback/history |
| Settings | Projects/API keys/audit/authentication explanation; account creation is offline CLI, not web account/password administration |
| Responsive design/accessibility | CSS breakpoints/focus states, mobile nav, labels, dialog handling; real browser keyboard/mobile review passed |
| Loading/empty/error/validation/toasts/confirmation | Shared UI components and behavioral unit tests |
| Query caching/invalidation/real API polling | `services/api.ts` hooks and mutation invalidation |
| Consistent pagination | Events server pagination and shared client pagination; audit/lab feeds are bounded recent-history views, documented in IMPLEMENTATION |

## 12–13. Performance and behavioral tests

`benchmarks/ingestion.js` supplies ingestion, concurrent, burst, sustained and
backpressure scenarios. `run.py` records requests/acceptance/rejections/rate,
p50/p95/p99, sampled E2E delivery latency, queue observations, environment and
parameters. `profile.py` runs cProfile on API/worker; PERFORMANCE describes
PostgreSQL contention/wait inspection and limitations. Indexes follow claims,
foreign keys and operational queries. Overview drain time uses observed
completions and is null without a rate. The recorded 100-request native baseline
is a low-rate measurement, not a capacity result or final-code speed claim.

Required backend tests map as follows (names abbreviated):

| # | Required behavior | Test source |
| --- | --- | --- |
| 1–5 | Valid/invalid ingestion, duplicates/conflicts, atomic jobs | integration: atomic_idempotency_conflict, api_auth_csrf_keys_and_policies, concurrent_ingest_and_claim, rollback_atomicity |
| 6–9 | Competing claims, transitions, delivery, HMAC | integration: concurrent_ingest_and_claim, retry_dead_letter_redrive, real_dispatch_signature; policy_security HMAC; receiver verification |
| 10–14 | Transient/permanent retry, backoff, dead letter/redrive | integration retry_dead_letter_redrive; policy_security classification/backoff; policy_rollout redrive cycle |
| 15–18 | Lease recovery, stale fencing, backpressure, pause/failover | integration lease_recovery_fencing/backpressure_atomic/pause_failover; dispatch_recovery |
| 19 | Incident detection/deduplication | integration incident_deduplication; monitoring dual-window/evidence tests |
| 20 | Incident acknowledge/resolve | Live exercise plus test_incident_api assertions |
| 21–22 | Deterministic assignment/rollback | policy_security canary_deterministic; integration API promotion/rollback; policy_rollout pin test |
| 23–25 | Auth/authorization/revocation/SSRF | integration API test; access_controls role/throttle tests; policy_security SSRF |
| 26 | Graceful shutdown | shutdown drain/no-claim and deadline/reclaim tests |

Frontend test source covers navigation, auth states, filters, detail, incident
action, form validation, API errors, loading/empty states, release confirmation,
sample sufficiency, role restrictions, shrinking pagination and duplicate submit.
19 tests passed. Real Playwright covers login,
project selection, submission, persisted200, detail, actual503 and recovery;
destination configuration PATCH is included. Smoke checks readiness, ingestion,
worker delivery, retry and monitoring endpoints with bounded polling. CI invokes
the real stack and smoke/browser checks, but has not run on GitHub.

## 14–20. Delivery, documentation and workflow

| Requirement | Source/evidence |
| --- | --- |
| All eight Make targets | Makefile: demo/up/down/test/lint/smoke/benchmark/clean |
| Single-command secrets/build/readiness/migration/bootstrap/URLs | `scripts/demo.py`; Compose isolated initialize service; launch unit tests |
| No external accounts/paid service requirement | Local receiver and generated secrets; no cloud resources |
| Persistent volumes/loopback/admin readiness/restarts/log bounds/grace | Compose and Dockerfiles; Docker runtime not available |
| Environment validation, health/ready, worker health | Config validators, API endpoints, heartbeat healthcheck |
| Production/demo boundary | SECURITY/.env.example/config/SSRF/lab guards; Compose intentionally demo-only |
| CI push/PR format/lint/types/tests/frontend/container/smoke/E2E | `.github/workflows/ci.yml`; explicit PostgreSQL service and real stack job |
| Tagged validated version/SHA GHCR release | release.yml verifies versions, requires reusable CI, publishes only in future authorized GitHub execution |
| README all required sections | Present; real screenshots and final evidence ledger included |
| Architecture | Components/data/entities/lifecycles/transactions/locking/retries/idempotency/regions/security/telemetry documented |
| Runbook | DB outage/backlog/worker/retry/p99/deadletter/incidents/redrive/rollback/recovery with commands/SQL |
| SLO/PERFORMANCE/SECURITY/RELEASE | Present; timestamp and threshold wording refreshed |
| Genuine incident report | INCIDENT_REPORT records actual outage/20 dead letters/incident/ack/restore/redrive/resolve; references local exercise |
| PostgreSQL broker tradeoff/logical region limits | TRADEOFFS and ARCHITECTURE |
| Demonstration sequence1–16 | App/lab/event/incident/policy/benchmark implemented; native monitoring/traces and live pool continuity verified |
| Git main/incremental commits/no remote/no secrets | Main incremental history and no remote inspected; final count/hash in completion report |
| Phased delivery/checklist/autonomous fixes/honest reporting | Implementation ledger and this audit; no completion inferred from scaffold or startup alone |

## 21–22. Completion and final report

Before completion, preserve direct evidence for launch/frontend/login/destination
creation/ingestion/HTTP delivery/persisted attempts/retry/redrive/concurrency/
reclaim/metrics/monitoring/event history/faults/incidents/auth/security/test/build.
Link each to a test, live run or inspected artifact above. Container execution is
an explicit environment limitation, not a pass. CI definitions are present,
benchmark commands and documents exist, and multiple Git milestones exist; final
publication hygiene is checked separately from runtime validation.

The final report must include implemented scope, architecture choices, exact
startup command, localhost URLs, executed suites/results, measured benchmark,
actually exercised faults, security controls, limitations, fresh commit count
and hash, and genuinely required deployment actions. Three technically accurate
resume suggestions belong only in the user-facing final report, not product copy.
Do not claim throughput improvements, production scale, uptime, hosted CI, Docker
builds or successful monitoring export without corresponding evidence.
