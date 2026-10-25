# Requirements audit

Audit date: 2026-10-24. This maps the supplied 22-section build specification to
the repository. It is a completion checklist, not a claim that every runtime gate
has passed. Source inspection proves implementation; it does not prove an
unexecuted deployment works. File paths below are repository-relative.

The coordinator reported **55 backend tests passing against PostgreSQL** during
this audit. Other execution results must be reconciled with the final
implementation ledger. Frontend edits and native monitoring verification were in
progress when this snapshot was written.

## Priority completion gates

| Gate | Current evidence and remaining action |
| --- | --- |
| Monitoring runtime | Prometheus/Grafana provisioning and telemetry exist. Coordinator is verifying actual native scrapes, dashboard queries and exported linked traces. Do not infer success from configuration files. |
| Maintained tracing backend | `compose.yaml` currently pins Jaeger all-in-one 1.76.0. Coordinator observed its end-of-life warning. Replace with supported Jaeger 2 configuration and verify export/query behavior. |
| Final frontend validation | Existing browser flow uses the real API/receiver, but edits are in progress. Rerun lint, type checking, unit tests, production build and real browser flow on final source. |
| Browser destination configuration | `frontend/e2e/delivery.spec.ts` selects the demo project and checks its existing destination, but the inspected test does not configure a destination. Add an actual configuration operation to satisfy the explicit minimum browser flow. |
| Incident action tests | Live exercise invokes acknowledge/resolve, but inspected backend monitoring tests mutate incident status directly. Add API action/status/timeline/audit assertions for both operations. |
| Historical incident access | `/api/incidents` caps the newest 200 rows with no server offset/filter. Client filtering/pagination cannot reach older history. Implement server pagination/filtering or clearly document the restricted history view. |
| Documentation reconciliation | `docs/IMPLEMENTATION.md` retains superseded pending gates and historical counts. `docs/SLO.md` describes delivery creation rather than the now-implemented event acceptance timestamp and hardcodes burn threshold 2. Update final ledger and SLO text. |
| Screenshots | Actual screenshot files are present but untracked; README has no embeds. Review final screenshots for layout/secrets, commit and embed them. |
| Live pool continuity | PostgreSQL tests prove pause/claim failover. Add or locate real native pool pause plus HTTP delivery evidence before claiming the complete live demonstration. |
| Final repository hygiene | Concurrent work is uncommitted. Recheck tests after integration, tracked secrets/build files, documentation consistency, Git status/count/hash and absence of remotes. |
| Environment-limited checks | Docker is unavailable. Container build/Compose runtime and hosted GitHub Actions must remain explicitly unverified; the specification permits this limitation. |

## 1–3. Product, stack and organization

| Requirement | Implementation/evidence | Assessment |
| --- | --- | --- |
| Real asynchronous infrastructure product | API, PostgreSQL queue, separate workers, receiver, operational React console | Implemented; runtime gates below |
| No fake metrics/backend/placeholders | Overview SQL aggregates; workers measure actual attempts; UI reads API via TanStack Query | Inspected; final browser review remains |
| No employer/recruiting copy | README and inspected product/docs use infrastructure terminology | Final whole-repository text scan still appropriate |
| Correctness/security/tests/local launch/incremental Git | Queue/security/test modules, launchers, meaningful Git history | Implemented; final clean-tree gate remains |
| Python ≥3.12, FastAPI/Pydantic2/SQLAlchemy2/asyncpg/Alembic/httpx | `backend/pyproject.toml`, `requirements.lock`, migrations | Present; PostgreSQL native integration used |
| React/TS/Vite/Tailwind/Query/Recharts | `frontend/package.json`, lockfile, source | Present |
| Docker/Prometheus/Grafana/OTel/Jaeger/Actions | Compose, infrastructure and workflows | Present; Jaeger maintenance gap above |
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
| Admin/operator/viewer authorization | Security dependencies plus role tests; frontend controls under final review |
| Authentication throttling | Bounded expiring per-process IP buckets; throttle/capacity tests; shared edge limiter required for replicas |
| Scoped hashed API keys, revoke/rotate | API key digest/scope checks; rotation is create replacement then revoke old; revocation test |
| Audit of administrative changes | `Audit` records in routes/users CLI; settings audit view |
| No plaintext DB passwords/API keys | Password hash/API digest; signing secret encrypted with Fernet |
| No routine secret leakage | Serialization excludes ciphertext/digests; key/signing secret reveal only on creation; final logs/screenshots scan needed |
| HMAC headers/canonical format/verifier | Runner signature(timestamp + dot + raw bytes); SECURITY example and demo sink verification tests |
| Production HTTPS/approved hosts/unsafe literals/no redirects | `security/crypto.py`, httpx client; SSRF parametrized tests |
| DNS rebinding boundary | Explicit approved-host fallback, documented trusted DNS/egress obligation; no claim that pre-resolution alone is safe |
| Demo-only named HTTP target; no arbitrary load/fault endpoints | Exact configured receiver origin/path; lab validates all enabled destinations; benchmark localhost restriction |
| SECURITY document | Present with operational deployment obligations and limitations |
| Three independent logical pools | Compose worker-us-east/eu-west/ap-southeast, same runner with region env |
| Heartbeat ID/region/time/version/capacity/state | Worker model, heartbeat routine and API |
| Pause/resume/deterministic selection/failover | Pool routes, stable identifier hashing, healthy-owner claim predicate; PostgreSQL test |
| No physical-region claim; documented guarantees/timing | README/ARCHITECTURE/TRADEOFFS/RUNBOOK; live failover demonstration gate above |

## 7–10. Observability, incidents, lab and policies

| Requirement | Implementation/evidence and remaining verification |
| --- | --- |
| Accepted/attempt/success/failure/retry/dead/backpressure counters | `observability/telemetry.py`, ingestion/worker/queue updates |
| Depth/in-flight/heartbeat gauges; activity/throughput | Heartbeat gauges; rates of actual attempt/success counters; worker API activity |
| HTTP and E2E histograms/p50/p95/p99 capability | Histograms with bounded buckets, dashboard quantile expressions |
| Low-cardinality labels; separate worker scraping | Region labels; Prometheus explicit targets for each worker; runtime scrape proof pending |
| FastAPI + worker OTel with persisted parent context | FastAPI instrumentation, Event.trace_context inject/extract, dispatch header injection |
| Ingest/persist/claim/dispatch/retry/complete spans | Named spans in API/ingestion/queue/runner; safe identifiers, not payload |
| Export to included backend + trace investigation docs | OTLP exporter/config and tracing README/RUNBOOK; actual trace gate pending |
| Automatically provisioned real Grafana queries | Datasource/dashboard provisioning; throughput/outcomes/p95/p99/queue/retry/dead/regional panels; runtime query gate pending |
| Configurable99%/30s matured24h SLO | Config + SQL aggregation against Event.created_at; tests for maturity/deadline/current state/no data |
| Separate terminal success/latency/error budget/burn | Overview aggregates; frontend displays separate measures |
| Dual-window/sample-minimum alerts | Shared observation timestamp, 24h/1h windows, configurable burn threshold/minimum; dedicated tests |
| Incident source/severity/component/times/evidence/timeline/status | Incident model and API/detail view; acknowledgement/resolution actor and time live in timeline |
| Deduplication/acknowledgement/reopen | Fingerprint unique constraint/advisory monitor lock; tests preserve acknowledgement/current evidence and reopen resolved condition |
| Configurable detection | Burn, dead-letter and queue fraction thresholds; unavailable affected pool detection; queue condition is capacity pressure, not a sustained-growth claim |
| Authorized acknowledge/resolve/audit | Routes implemented; live script uses them; missing focused API assertions noted above |
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
| Incidents | Status/severity filters, evidence/timeline/actions; newest200 historical cap noted above |
| Reliability Lab | Real safe scenario/generation/reset/pool controls/history/live metrics |
| Release Policies | Versions/differences/percentage/outcomes/promotion/rollback/history |
| Settings | Projects/API keys/audit/authentication explanation; account creation is offline CLI, not web account/password administration |
| Responsive design/accessibility | CSS breakpoints/focus states, mobile nav, labels, dialog handling; final browser/keyboard review pending |
| Loading/empty/error/validation/toasts/confirmation | Shared UI components and behavioral unit tests |
| Query caching/invalidation/real API polling | `services/api.ts` hooks and mutation invalidation |
| Consistent pagination | Events server pagination and shared client pagination; caps on other history feeds must be explicit |

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
| 20 | Incident acknowledge/resolve | Live exercise exists; focused backend API action/audit test gap above |
| 21–22 | Deterministic assignment/rollback | policy_security canary_deterministic; integration API promotion/rollback; policy_rollout pin test |
| 23–25 | Auth/authorization/revocation/SSRF | integration API test; access_controls role/throttle tests; policy_security SSRF |
| 26 | Graceful shutdown | shutdown drain/no-claim and deadline/reclaim tests |

Frontend test source covers navigation, auth states, filters, detail, incident
action, form validation, API errors, loading/empty states, release confirmation,
sample sufficiency, role restrictions, shrinking pagination and duplicate submit.
Execution must be recorded after current edits. Real Playwright covers login,
project selection, submission, persisted200, detail, actual503 and recovery;
destination configuration gap remains above. Smoke checks readiness, ingestion,
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
| README all required sections | Present; actual screenshot embeds and final evidence reconciliation remain |
| Architecture | Components/data/entities/lifecycles/transactions/locking/retries/idempotency/regions/security/telemetry documented |
| Runbook | DB outage/backlog/worker/retry/p99/deadletter/incidents/redrive/rollback/recovery with commands/SQL |
| SLO/PERFORMANCE/SECURITY/RELEASE | Present; SLO timestamp/threshold wording needs refresh |
| Genuine incident report | INCIDENT_REPORT records actual outage/20 dead letters/incident/ack/restore/redrive/resolve; references local exercise |
| PostgreSQL broker tradeoff/logical region limits | TRADEOFFS and ARCHITECTURE |
| Demonstration sequence1–16 | App/lab/event/incident/policy/benchmark supported; runtime monitoring/trace and pool continuity evidence gates remain |
| Git main/incremental commits/no remote/no secrets | Inspected main history contains19 commits at audit start, no remote output; final count/hash/status must be refreshed |
| Phased delivery/checklist/autonomous fixes/honest reporting | Implementation ledger and this audit; no completion inferred from scaffold or startup alone |

## 21–22. Completion and final report

Before completion, preserve direct evidence for launch/frontend/login/destination
creation/ingestion/HTTP delivery/persisted attempts/retry/redrive/concurrency/
reclaim/metrics/monitoring/event history/faults/incidents/auth/security/test/build.
Link each to a test, live run or inspected artifact above. Container execution is
an explicit environment limitation, not a pass. CI definitions are present,
benchmark commands and documents exist, and multiple Git milestones exist; final
publication hygiene is still a gate.

The final report must include implemented scope, architecture choices, exact
startup command, localhost URLs, executed suites/results, measured benchmark,
actually exercised faults, security controls, limitations, fresh commit count
and hash, and genuinely required deployment actions. Three technically accurate
resume suggestions belong only in the user-facing final report, not product copy.
Do not claim throughput improvements, production scale, uptime, hosted CI, Docker
builds or successful monitoring export without corresponding evidence.
