import hmac
import hashlib
import pytest
from relayops.security.crypto import signature, validate_destination
from relayops.services.policy import choose_policy, event_status, region_for, retry_delay, retryable


def test_hmac_canonical_bytes():
    body = b'{"a":1}'
    expected = "sha256=" + hmac.new(b"secret", b"123." + body, hashlib.sha256).hexdigest()
    assert signature("secret", "123", body) == expected
    assert signature("secret", "124", body) != expected


@pytest.mark.parametrize(
    "status,expected",
    [
        (None, True),
        (408, True),
        (429, True),
        (500, True),
        (503, True),
        (400, False),
        (404, False),
        (302, False),
    ],
)
def test_retry_classification(status, expected):
    assert retryable(status) is expected


def test_backoff_bounded_and_retry_after():
    for _ in range(50):
        assert 4 <= retry_delay(4, 1, 60) <= 8
        assert 30 <= retry_delay(30, 1, 60) <= 60
    assert retry_delay(1, 1, 60, "9000") == 3600
    assert retry_delay(1, 1, 60, "5") == 5
    assert retry_delay(1, 1, 60, "garbage") <= 1


def test_canary_deterministic():
    for i in range(100):
        assert choose_policy(str(i), "stable", "candidate", 20) == choose_policy(
            str(i), "stable", "candidate", 20
        )
        assert region_for(str(i)) == region_for(str(i))
    assert choose_policy("one", "stable", "candidate", 0) == "stable"
    assert choose_policy("one", "stable", "candidate", 100) == "candidate"


@pytest.mark.parametrize(
    "url",
    [
        "http://evil.com/webhook",
        "file:///etc/passwd",
        "http://127.0.0.1:1234/webhook",
        "http://127.0.0.1:8081/control",
        "http://user:pass@127.0.0.1:8081/webhook",
        "https://169.254.169.254/latest",
        "https://unapproved.example.com/webhook",
    ],
)
def test_ssrf_rejected(url):
    with pytest.raises(ValueError):
        validate_destination(url)


def test_demo_origin_exact():
    assert validate_destination("http://127.0.0.1:8081/webhook")


def test_event_status_mixed():
    assert event_status(["delivered", "dead_letter"]) == "partial_failure"
    assert event_status(["delivered", "retry_wait"]) == "processing"
    assert event_status([]) == "no_destinations"
