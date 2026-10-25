# Monitoring validation

Native validation on 2026-10-24 used Prometheus 3.13.3, Grafana 12.3.2 and
Jaeger 2.22.0. Docker was unavailable. Native copies of the committed configuration
changed only service DNS names to loopback addresses, worker ports to 9001–9003,
and persistence/provisioning paths to ignored local directories.

## Results

- Prometheus `/api/v1/targets`: API and all three worker targets reported `up`.
- Grafana `/api/health`: database `ok`; provisioned dashboard
  `relayops-operations` loaded successfully.
- Grafana Prometheus datasource health: successfully queried the Prometheus API.
- All fourteen expressions in the twelve-panel dashboard executed successfully.
  No-sample series remain empty; they are not substituted with fabricated zeros.
- Live validation exposed a PromQL duplicate-labelset error when a single `rate`
  selector included both outcome counters. Separate success/failure expressions
  corrected it and were rerun successfully.
- Jaeger v3 queries returned `relayops-api` and `relayops-worker` services and
  connected ingestion/persistence/dispatch/completion/retry spans. One observed
  trace was `1d32238a8cf6f0c31255badcb722f7f6`, including a failed attempt,
  retry scheduling and another dispatch under the same ingestion parent.

## Traces

Open Jaeger directly at `http://localhost:16686`; select `relayops-worker` and
operation `delivery.dispatch`, then inspect the trace ID shown by event details.
Idle claim spans can dominate an unfiltered search. Trace retention is 48 hours
in the local Badger volume; the recorded validation ID may expire.

The Compose configuration uses Jaeger 2.22.0 and a persistent Badger backend.
The named volume mounts the image's writable `/tmp` directory; data lives under
`/tmp/relayops` and survives container replacement without running Jaeger as root.
It replaces the obsolete v1 image. Grafana 12's legacy Jaeger datasource API
is incompatible with this Jaeger release, so it is deliberately not provisioned;
Grafana provides metrics and Jaeger provides the trace viewer separately.
Native `jaeger validate --config=...` and collection/query were executed.
Container execution remains unverified.

API ingestion persists W3C trace context; workers extract it and inject context
into outbound webhook headers. Heartbeat gauges update after database commit.
JSON worker logs include UTC timestamps and exception type/code locations without
serializing exception values or locals that could contain payloads or credentials.

## Deployment boundary

The demo publishes monitoring UIs only on loopback. Production needs private
access, authentication/TLS at the deployment boundary, storage sizing and retention
appropriate to workload. Badger is single-node storage, not a highly available
distributed trace store. See the upstream [Jaeger storage documentation](https://www.jaegertracing.io/docs/2.dev/storage/badger/)
and [release configuration](https://github.com/jaegertracing/jaeger/blob/v2.22.0/cmd/jaeger/config-badger.yaml).
