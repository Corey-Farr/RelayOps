# Design tradeoffs

## PostgreSQL as a durable queue

Events and their delivery jobs belong in the same transaction. A PostgreSQL
queue makes that boundary explicit without a second broker and an outbox relay.
Workers compete for due rows using row locks and skip work already locked by
another claimant. The claim transaction ends before network I/O begins.

This keeps local operation understandable, but does not remove database costs.
Every attempt writes durable state. Queue indexes, table vacuuming, retention,
connection limits and transaction contention become capacity constraints.
Measure these before increasing worker concurrency. More workers cannot fix a
saturated destination or database.

At larger scale, partition history tables, introduce an archival policy, and
separate analytical queries from queue transactions. A broker could carry
notifications while PostgreSQL remains the source of truth; a transactional
outbox would then be needed to avoid losing accepted work between systems.

## Delivery semantics

Delivery is **at least once**. If a destination accepts an HTTP request and the
worker crashes before committing its result, the lease expires and another
worker sends the request again. Fencing protects database state, not external
side effects. Receivers must deduplicate by event ID and commit that ID with
their business operation. An idempotent ingestion request prevents duplicate
event creation; it cannot guarantee exactly-once downstream execution.

Retries preserve the policy selected for the delivery. A later configuration
promotion changes future delivery selection, not the semantics of work already
accepted. Manual redrive can cause additional downstream attempts and must be
treated as an operational action.

## Logical regions

The three local worker pools share one PostgreSQL database, one host and one
network. They demonstrate assignment, heartbeat monitoring, pausing and failover
between processes. They do not provide geographic redundancy or protection
against loss of the host or database.

Real geographic operation would require a documented database replication and
failover strategy, regional networking, credentials and egress policies,
clock discipline, capacity reserves, and explicit RPO/RTO objectives. Cross-region
latency and split-brain behavior would need separate failure testing.

## Polling and operational history

Short periodic API polling keeps the console independent of a streaming broker.
It introduces bounded display delay and repeated read load. This is appropriate
for a small operations deployment; very large histories need retention and
aggregation rather than unrestricted interactive queries.

## Scope of reliability evidence

A local successful run establishes behavior under that workload and environment.
It does not establish production uptime, geographic resilience, Internet-scale
capacity, or a completed external security review. Benchmark results must state
their workload and measurement window; absent data is not a zero-latency or
100-percent-success result.
