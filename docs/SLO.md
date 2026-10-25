# Delivery reliability objective

The default objective is **99% of eligible deliveries acknowledged within 30
seconds**, measured over a rolling 24-hour cohort. Eligibility is per delivery,
so an event subscribed to two destinations contributes two observations. Events
without matching destinations do not create an artificial successful delivery.

## Observation windows

Only deliveries whose events were accepted at least `SLO_DEADLINE_SECONDS` ago enter the denominator.
A successful acknowledgement must have been persisted within that deadline to
enter the numerator. Pending, leased, retrying, dead-lettered and late-successful
deliveries count as bad once their window matures. In-flight work is never
counted as successful merely because it has not failed yet.

The implementation uses UTC `Event.created_at` timestamps, including for the
deadline and both observation windows. A redrive retains the original acceptance time and does not
erase a missed deadline.

## Calculations

For eligible count `N`, on-time count `G` and target `T`:

```text
compliance = G / N
bad fraction = 1 - compliance
burn rate = bad fraction / (1 - T)
remaining budget fraction = 1 - burn rate
```

A negative remaining budget means the cohort has consumed more than its budget;
it is not clamped into an apparently healthy range. Burn rate 2 means the bad
fraction is twice the allowed fraction for that observed cohort. These values
describe the observed rolling sample, not a forecast of future uptime.

With no eligible samples, compliance and budget values are absent. The console
must present missing data explicitly. `SLO_MIN_SAMPLES` defaults to 20; fewer
observations are marked insufficient for alerting, even if a descriptive sample
percentage exists.

## Alert conditions

The monitor compares a 24-hour window and a one-hour window. Both must have the
configured minimum sample count, and both must reach `INCIDENT_BURN_THRESHOLD` (default 2) before
the SLO condition opens an incident. This avoids alerting from one isolated
failure in an otherwise empty sample. These are overlapping local demonstration
windows, not a statistically calibrated paging policy for every workload.

Separate infrastructure conditions cover unavailable worker pools with affected
queued work, queue capacity pressure and dead-letter accumulation. Those are not
SLO compliance measurements. Queue pressure is a capacity threshold, not a claim
that sustained growth has been statistically established.

An active condition has a stable fingerprint. Acknowledgement records ownership
without changing the condition. A resolved incident can reopen if detection
still observes its condition. Manual resolution is not proof of recovery.

## Other metrics

Overall terminal delivery success rate is delivered / (delivered + dead letter).
It excludes unfinished work and is displayed separately from deadline compliance.
Throughput is based on observed delivery completions. Histograms support latency
percentiles; quantiles depend on buckets and sample size. Queue drain estimates
assume the recent completion rate continues and are absent when no rate exists.

## Limitations

The demo uses one database and local logical worker regions. Clock skew, database
availability and retained history affect measurements. History retention is not
automatically configured. External alert routing and on-call escalation require
deployment-specific integration. Small samples and short native validation runs
do not establish a production SLO track record.
