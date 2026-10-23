# Observed local destination-outage exercise

This report describes a real browser-driven fault exercise, not a production
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
tests verify incident deduplication; a larger threshold-crossing operational
exercise remains a distinct validation gate.

The exercise confirms that a displayed fault changes real receiver behavior,
failed attempts remain inspectable, and restoring the dependency permits normal
retry recovery. It does not prove geographic redundancy, exactly-once delivery,
or resilience to database loss.
