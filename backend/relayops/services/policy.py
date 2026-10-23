import hashlib
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

REGIONS = ("us-east", "eu-west", "ap-southeast")
ACTIVE = ("pending", "leased", "retry_wait")


def bucket(identifier: str) -> int:
    return int.from_bytes(hashlib.sha256(identifier.encode()).digest()[:8], "big") % 100


def region_for(identifier: str) -> str:
    return REGIONS[int(hashlib.sha256(identifier.encode()).hexdigest(), 16) % len(REGIONS)]


def choose_policy(identifier: str, stable: str, candidate: str | None, percent: int) -> str:
    return candidate if candidate and bucket(identifier) < percent else stable


def retryable(status: int | None) -> bool:
    return status is None or status in {408, 429} or status >= 500


def retry_delay(attempt: int, base: float, cap: float, retry_after: str | None = None) -> float:
    delay = random.uniform(0.5, 1.0) * min(cap, base * 2 ** min(attempt - 1, 20))
    if retry_after:
        try:
            value = float(retry_after)
        except ValueError:
            try:
                value = (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                value = 0
        delay = max(delay, min(3600, max(0, value)))
    return delay


def event_status(statuses: list[str]) -> str:
    if not statuses:
        return "no_destinations"
    if all(s == "delivered" for s in statuses):
        return "delivered"
    if any(s in ACTIVE for s in statuses):
        return "processing"
    if all(s == "dead_letter" for s in statuses):
        return "dead_letter"
    return "partial_failure"
