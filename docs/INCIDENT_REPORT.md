# Observed local destination-outage exercises

The first exercise describes a real browser-driven fault exercise, not a production
incident. The small, quickly recovered sample did not establish sustained SLO
degradation or require an automatically opened incident.

## Scenario and evidence

Playwright signed in to the running console, selected the demo project, verified
a normal delivery, then activated **Destination outage** in Reliability Lab.
The real HTTP receiver returned 503. After observing the persisted failure, the
test restored **Normal operation** through the console and waited for delivery.

Event: `5d12d2b0-369b-457f-bd17-870015d1d3bd` (`e2e.recovery`).
Delivery: `609ad86e-0216-4aaa-b729-5d74f88ea654`.
Worker: `native-ap-southeast`.

| UTC, 2026-10-23 | Observed event |
| --- | --- |
| 12:15:25.100832 | Event accepted and persisted |
| 12:15:25.298884 | First dispatch began |
| 12:15:25.324637 | HTTP 503 recorded; measured request duration 25.56 ms |
| 12:15:26.317903 | Persisted retry became due |
| 12:15:26.344352 | Second dispatch began |
| 12:15:26.354668 | HTTP 200 recorded; measured request duration 10.23 ms |

Both attempts remain in the database. Acceptance-to-success elapsed time was
approximately 1.254 seconds. The browser test verified the failure and success
in Event Explorer and passed in 16.2 seconds for its complete workflow.

## Cause, recovery and lessons

The root cause was the deliberately enabled receiver outage mode. The delivery
engine classified 503 as retryable and persisted the next attempt time. Restoring
the receiver allowed the next attempt to succeed without manual redrive.

Detection in this exercise was explicit test polling of persisted attempts.
It does not prove automatic sustained-degradation detection. Separate PostgreSQL
tests verify incident deduplication. The later threshold-crossing exercise below
also verifies automatic detection in the running local system.

The exercise confirms that a displayed fault changes real receiver behavior,
failed attempts remain inspectable, and restoring the dependency permits normal
retry recovery. It does not prove geographic redundancy, exactly-once delivery,
or resilience to database loss.

## Threshold-crossing incident and redrive exercise

Executed October 23, 2026 at approximately 20:39 America/Phoenix (October 24,
03:39 UTC). Reproduce with `python scripts/exercise.py` against the demo stack.
The script restores Normal mode and removes its candidate policy in `finally`.

A temporary 100% candidate with one maximum attempt made the outage produce
dead letters deterministically. Twenty events were accepted through the real
lab endpoint; each produced a persisted HTTP 503. The monitor detected the
configured accumulation threshold of ten and opened incident
`cafe7219-f02b-45d4-a9e8-6a57f2d16b7e` with evidence `{count: 20, threshold: 10}`.

| UTC on 2026-10-24 | Observed action |
| --- | --- |
| 03:39:32.208 | Receiver outage enabled |
| 03:39:32.310 | Twenty events accepted |
| 03:39:33.919 | Twenty dead-letter events observed |
| 03:39:37.596 | Automatic incident observed |
| 03:39:37.604 | Incident acknowledged |
| 03:39:37.872 | Receiver restored |
| 03:39:39.244 | All twenty redriven events delivered |
| 03:39:39.274 | Incident resolved |

Acknowledgement recorded ownership while the failures remained present. After
restoration, authorized redrive granted each delivery a fresh bounded retry
cycle, preserving its original failed attempt. Every event finished delivered
with at least two recorded attempts. The incident timeline retained detection,
acknowledgement and resolution. Raw local evidence is in
`.local/incident-exercise.json`; it is intentionally excluded from Git.

This demonstrates automatic dead-letter incident detection, not an SLO-burn
incident. The exercise remained local and did not contact external destinations.

## Receiver mode validation

`python scripts/fault_modes.py` separately exercised normal acknowledgements,
deterministic intermittent HTTP 500, HTTP 429 with two-second retry guidance,
actual two-second response latency and a real HTTP timeout using a 0.5-second
delivery policy. Each event subsequently reached delivered state. The rate-limit
check compared persisted attempt timestamps and required the retry to wait at
least 1.9 seconds after the failed attempt ended. Measured latency was 2010.35 ms;
the timeout occurred after 505.68 ms. These checks used actual HTTP requests,
not patched clocks. Evidence is saved locally in `.local/fault-modes.json`.
