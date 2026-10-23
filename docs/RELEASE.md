# Release engineering

RelayOps uses semantic version tags (`vMAJOR.MINOR.PATCH`) for application
releases. Configuration policy versions are separate database records and do not
represent deployed application versions.

## Validation before tagging

Run the backend lint, formatting, type and PostgreSQL tests; frontend lint, type,
unit and build checks; and real-stack smoke/browser tests. Inspect dependency
changes and migration behavior. Preserve a tested database backup before a
deployment that changes schema. Do not publish generated `.env` files, database
volumes, request payloads, private benchmark logs or credentials.

The CI workflow performs these checks on pushes and pull requests. The stack job
builds the Compose application, runs smoke tests and invokes Playwright against
the actual services. A workflow file is not evidence of a successful hosted run:
no hosted execution or publication is claimed until the repository is connected
and those runs have completed.

## Container publication

The tagged-release workflow validates code and builds images with version and
commit-SHA tags, using GitHub Container Registry permissions when available.
Review the workflow and repository package permissions before pushing a tag.
The build assignment does not create a remote, push tags or publish images.

For an actual release, record the source commit, immutable image digests,
dependency locks, migration revision and executed verification results. Promote
the same tested digests between environments. Configure deployment-specific TLS,
private observability access, approved destination hosts and managed secrets.

## Verification and rollback

After migration and deployment, verify readiness, heartbeats, one signed delivery,
attempt persistence, queue progression and metrics. A live HTTP process alone is
insufficient. Monitor new error categories and SLO windows during rollout.

Retain the previous application images and deployment configuration. Application
rollback is safe only if the previous version understands the current schema.
Prefer compatible additive migrations; destructive schema changes require a
separate recovery plan and tested backup restoration. Do not blindly downgrade
the database while workers are running.

## Delivery-policy releases

Release Policies offers a stable version, optional candidate, canary percentage,
promotion and rollback. Assignment is deterministic from delivery identifiers;
the selected policy ID is persisted with each job. Compare actual outcomes with
adequate sample sizes. Existing jobs and retries keep their original policy even
after promotion or rollback. The audit trail records actor and action.

Promoting a candidate affects newly assigned deliveries. Rolling back an active
candidate removes it from future assignment; rollback after promotion can restore
the prior stable policy. Neither action changes application binaries or erases
historical attempts.
