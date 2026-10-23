# Operations runbook

Use the console's Event Explorer to correlate an event, delivery, attempt and
trace. Treat payloads and credentials as sensitive. Preserve evidence before
redrive or configuration changes. Commands below assume the root Compose stack.

## Initial diagnosis

```sh
docker compose ps
docker compose logs --tail=100 api worker-us-east worker-eu-west worker-ap-southeast
curl --fail http://localhost:8000/ready
docker compose exec postgres pg_isready -U relayops -d relayops
```

Readiness checks database access. Process liveness alone does not establish that
the queue is progressing. Compare queue depth, attempted throughput, heartbeat
freshness and destination errors. Inspect Grafana and Jaeger alongside the
persisted attempt timeline.

## Database unavailable

1. Check PostgreSQL health, disk capacity, logs and connection count.
2. Restore database connectivity before restarting application processes.
3. Verify readiness, new event acceptance and actual successful delivery.
4. Look for expired leases being recovered. Do not manually delete leased rows.

Never bypass failed persistence with an in-memory acceptance path. A rejected
client request may be retried using the same project and idempotency key.

## Growing backlog

Inspect queue states and the age of due work:

```sh
docker compose exec postgres psql -U relayops -d relayops
```

```sql
SELECT status, count(*) FROM deliveries GROUP BY status;
SELECT pid, state, wait_event_type, wait_event
FROM pg_stat_activity WHERE datname = current_database();
SELECT relname, n_live_tup, n_dead_tup, last_autovacuum
FROM pg_stat_user_tables ORDER BY n_dead_tup DESC;
```

Check paused pools, destination rate limits, timeout policy and available worker
capacity before increasing concurrency. A downstream outage requires restoring
the dependency, not multiplying requests against it. Capacity estimates are
based on observed completion rates and can become invalid as load changes.

## Worker failure

Check the Worker Pools screen and the specific service log. A missing heartbeat
with assigned queued work is actionable; an idle healthy worker is not a fault.
Resume a deliberately paused pool through the authenticated console. Restart a
failed service after determining its cause:

```sh
docker compose restart worker-us-east
```

Recovery is bounded by lease expiration, heartbeat/failover thresholds and
polling. A request sent before a crash can be sent again. Destination-side
idempotency must handle this ambiguity.

## High retries or elevated p99 latency

Group attempts by HTTP status and failure category. HTTP 429 often indicates a
destination capacity limit; timeouts can indicate slow service or networking.
Check latency distributions and traces, then compare stable/candidate policy
outcomes. Avoid increasing timeouts without considering occupied worker slots
and lease duration. A single slow request is not evidence of sustained SLO burn.

## Dead letters and safe redrive

1. Inspect the original payload, destination and complete attempt history.
2. Fix authentication, destination availability or configuration first.
3. Confirm that the receiver deduplicates event IDs.
4. Redrive selected deliveries through the console with an operator/admin role.
5. Verify new attempts and final state; keep the original history for diagnosis.

Do not delete or rewrite attempts to make a dashboard appear healthy. Redrive
does not retroactively make a missed SLO deadline successful.

## Incident investigation

Read the incident evidence and timeline. Acknowledge ownership, then investigate
the affected component. Acknowledgement does not restore health. Resolve only
after inspecting delivery progress and the triggering condition. If a condition
persists, subsequent detection can produce a new incident after resolution.

For the reliability lab, restore the destination mode to **Normal**, resume
paused pools, and watch pending and retry queues drain. Retain lab history and
attempt evidence for the post-incident report.

## Configuration rollback

Use Release Policies to inspect the stable and candidate settings, traffic
percentage and measured outcomes. Rollback removes the candidate from future
assignment. Existing deliveries retain their selected policy, including retries.
This is a delivery-configuration operation, not a software binary deployment.

## Graceful recovery and shutdown

```sh
make down
make up
```

Ordinary shutdown preserves database volumes. Do not use volume deletion as a
recovery procedure. Allow workers their shutdown grace period; interrupted work
remains recoverable through leases. After restart, check readiness, heartbeats,
backlog progression and one end-to-end delivery before declaring recovery.

## Escalation evidence

Collect sanitized timestamps, affected component, event/delivery identifiers,
attempt categories, policy versions, trace references, queue depth and relevant
service versions. Never include session cookies, API keys, signing secrets,
database passwords or unreviewed payloads in public reports.
