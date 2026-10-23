# Measured load and profiling

Start the demo, then run `python benchmarks/run.py`. Python reads credentials from
the ignored `.env`, creates an ephemeral project API key, and revokes it afterward.
Only a localhost API in demo mode is accepted. Install k6 locally or use the runner's
Docker fallback on the Compose network. The workload always targets the configured
local demo project, never an arbitrary webhook URL.

`--scenario` selects `ingestion` (one VU), `concurrent`, `burst`, `sustained` or
`backpressure`. Control `--rate`, `--vus`, `--seconds`, and `--drain-seconds`.
For backpressure, lower the configured queue limit and pause logical pools through
the console before running; restore pools afterward. A run with zero observed 429/503
responses did **not** demonstrate backpressure.

Each ignored `results/<run-id>/` contains raw k6 summary and `report.json`, including
real request counts, rejection counts, RPS and p50/p95/p99 request durations; observed
queue samples and drain estimates; and delivery latencies from at most 100 newest
matching events. Results identify sampling and shared-workload limitations. Run on
an otherwise idle demo for meaningful comparison. No precomputed results are supplied.
Record CPU/memory limits, host specifications and the git revision when publishing a report.

Profile from the backend virtual environment, with its package installed and configuration
exported: `python benchmarks/profile.py api` or `python benchmarks/profile.py worker`.
Drive real traffic while profiling, then Ctrl+C and inspect the `.pstats` file using
`python -m pstats <file>` (`sort cumulative`, `stats 30`). For wall-time and I/O investigations,
optionally install py-spy and use `py-spy record --pid <pid> --output profile.svg`.
Correlate profiler output with Jaeger database/dispatch spans, PostgreSQL
`pg_stat_activity` waits and Prometheus queue/dispatch histograms; cProfile alone
does not attribute asynchronous network waits precisely.
