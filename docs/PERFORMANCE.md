# Performance methodology and measured baseline

Use `make benchmark`, or invoke `python benchmarks/run.py` with a bounded local
workload. The runner creates a temporary project API key, invokes k6, samples
actual queue state, waits for sampled deliveries, writes a JSON report and revokes
the key. It accepts only localhost API targets and requires demo mode.

```sh
python benchmarks/run.py --scenario sustained --rate 5 --seconds 20 --vus 5
python benchmarks/run.py --scenario concurrent --vus 10 --seconds 30
python benchmarks/run.py --scenario burst --rate 20
python benchmarks/run.py --scenario backpressure --rate 100 --seconds 30
```

The backpressure workload generates pressure; whether admission rejection occurs
depends on configured queue capacity and measured drain rate. It does not inject
fake 429 responses. Use a dedicated demo database when changing capacity limits.
Do not run against external destinations.

## Native baseline measured 2026-10-23

Environment: Windows 10 build 19045, Python 3.13.1, PostgreSQL 17.11, six reported
logical CPUs, three native worker processes with eight slots each, local HTTP
receiver in normal mode, k6 2.3.0. API and workers were the initial native runtime
started before subsequent hardening edits; this is a baseline, not validation of
every later source change. No Docker, Grafana or Jaeger ran during this workload.

Run ID: `6596ff6d628c417b8481c9a69ee235ef`. Constant arrival workload: five requests
per second for 20 seconds. The scenario allocated 10 initial VUs and up to 100;
`--vus` controls the separate concurrent scenario, not constant arrival allocation.

| Measurement | Observed value |
| --- | ---: |
| Requests / accepted / rejected | 100 / 100 / 0 |
| Request rate | 5.00/s |
| Ingestion p50 / p95 / p99 | 12.49 / 24.60 / 30.03 ms |
| Delivered end-to-end samples | 100 |
| End-to-end p50 / p95 / p99 | 168.64 / 278.21 / 304.07 ms |
| Queue depth in two-second samples | 0–1 |
| Queue sample errors | 0 |
| k6 exit status | 0 |

This deliberately small workload verifies measurement and delivery. It is not a
saturation test, maximum throughput claim, improvement comparison or production
capacity estimate. Queue sampling can miss peaks between samples. End-to-end
reporting inspects at most the 100 newest matching events and reports that sample
size; it must not be extrapolated to all events in larger runs.

Raw results are generated under ignored `benchmarks/results/`. Portable results
can be selectively published after reviewing for private data and machine paths.

## Profiling and bottleneck investigation

With backend dependencies installed and normal database environment configured:

```sh
python benchmarks/profile.py api
python benchmarks/profile.py worker
python -m pstats benchmarks/results/COMPONENT-TIMESTAMP.pstats
```

Stop the ordinary instance using the same port before starting a profiler. Ctrl+C
flushes the cProfile output. Load the service while profiling; an idle profile
does not characterize a busy system. Profiles are ignored generated artifacts.
No profile-driven optimization result is claimed yet.

For queue growth, correlate completion rate with PostgreSQL `pg_stat_activity`
wait events, table/index statistics and receiver latency. Inspect short claim
transactions separately from HTTP waits. The ingestion advisory lock serializes
capacity checks and can limit admission throughput; measure contention before
changing its correctness boundary. The claim index follows status/due-time
queries; event and attempt foreign keys support operational inspection.

The console's drain estimate divides backlog by recent observed completions.
It is absent without observations and assumes no new arrivals or rate changes.
A short warm-up can make the rolling estimate conservative. More worker slots
do not guarantee higher throughput when the database or destination is saturated.

## Not yet measured

Saturation, long-duration load, host failure, production network latency, database
disk exhaustion and container-specific overhead are outside the recorded
baseline. Run them separately and preserve configuration and machine details.
