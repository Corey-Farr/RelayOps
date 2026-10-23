# Security model and deployment

RelayOps's local demo is an isolated development configuration. Production
operation requires an independently reviewed deployment, private metrics and
tracing networks, TLS termination, managed secrets, backups and an egress policy.
The supplied Compose stack binds published administrative ports to localhost.
Do not expose it directly to the Internet.

## Authentication and authorization

Passwords use Argon2. Browser sessions use HttpOnly cookies, a bounded lifetime
and SameSite protection; authenticated mutations also require a CSRF header.
Production cookies require HTTPS. Admin, operator and viewer roles gate actions.
An ingestion API key authorizes only its project. Keys are shown when created,
stored as hashes, and may be revoked. Rotation means creating a replacement,
updating clients, then revoking the old key.

First-run credentials are generated into an ignored local `.env`, rather than
committed defaults. Restrict access to that file, especially on shared machines.
Windows file mode flags do not replace NTFS access controls. Change credentials
before sharing a running environment. Keep application logs and screenshots free
of keys, session cookies and passwords.

## Account administration

Additional accounts can be created by an administrator with deployment database
access using `docker compose exec api python -m relayops.users person@example.com
--role operator` (one command). The password is entered through a hidden prompt,
hashed before storage, and never passed as a command-line argument. Account
creation is audited. Use `viewer` for read-only access. Login limiting is local
to each API process (10 attempts per client address per minute); deploy a shared
edge limiter before introducing multiple API replicas. Expired rate-limit entries
are pruned and the number of active address buckets is capped.

## Webhook signing

Destinations receive these headers:

- `X-RelayOps-Event-ID`
- `X-RelayOps-Delivery-ID`
- `X-RelayOps-Timestamp`
- `X-RelayOps-Signature`

The signature is `sha256=` followed by the hexadecimal HMAC-SHA256 of ASCII
timestamp, a literal period, then the exact raw HTTP body. Use the destination
secret as the HMAC key. Do not parse and reserialize JSON before verification.
The demo receiver enforces a five-minute timestamp tolerance and uses constant
time comparison. See [its working implementation](demo-sink/server.py).

```python
import hashlib
import hmac
import time

def verify(secret: str, timestamp: str, body: bytes, received: str) -> bool:
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
    except ValueError:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received)
```

Timestamp validation limits replay age but does not deduplicate events. A real
receiver must atomically deduplicate the event ID with its business operation.
The demo sink demonstrates acknowledgement and fault behavior, not a business
transaction ledger. The signature authenticates the raw body and timestamp;
consumers should take authoritative event identity from the signed body rather
than trusting an independently supplied unsigned header.

Signing secrets are encrypted at rest because workers need to recover them for
HMAC use. Protect and back up `ENCRYPTION_KEY` separately from the database.
Losing it prevents delivery to existing encrypted destinations. Rotating the
encryption key requires a controlled re-encryption procedure; simply replacing
the environment value is not a migration.

## Outbound request / SSRF boundary

Production requires HTTPS and explicitly approved destination hosts. Arbitrary
schemes, embedded credentials, unsafe literal addresses and redirects are not
accepted. Host approval must be limited to domains controlled by trusted parties.
An allowlist is a security boundary only when its DNS ownership and routing are
also trusted. Enforce network egress restrictions that block private, loopback,
link-local and metadata address ranges at connection time. Do not approve
attacker-controlled wildcard domains or treat a one-time DNS lookup as rebinding
protection. This application is not a general unrestricted webhook proxy.

Demo mode allows the exact configured local receiver origin and `/webhook` path.
For Compose this is the named `demo-sink` service. Native validation may configure
the loopback receiver explicitly. Other local ports and arbitrary targets remain
rejected. Lab controls act only on the configured receiver and require authorized
sessions; the receiver's control endpoint has a separate secret token.

## Operational protections and remaining responsibilities

Payload and queue limits bound admission. Worker concurrency, timeouts and retry
limits bound processing. Audit records retain administrative changes without
credentials. Access to metrics, tracing and the database must remain restricted:
operational identifiers and system behavior can still be sensitive even when
payloads are omitted.

Before production, establish retention and deletion requirements, tested backups,
TLS and proxy configuration, rate limiting at the edge, dependency update policy,
secret rotation, alert routing and incident ownership. Do not rely on local
logical regions for geographic redundancy. This project has not undergone an
independent penetration test.

## Reporting

Do not open a public issue containing a working exploit, credentials or private
payloads. Contact the repository maintainer privately through the hosting
platform's security advisory mechanism when a public repository is established.
No security contact address or response SLA is claimed before publication.
