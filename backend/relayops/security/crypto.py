import hashlib
import hmac
import ipaddress
import secrets
from urllib.parse import urlsplit
from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from relayops.core.config import settings

passwords = PasswordHasher()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def token() -> str:
    return secrets.token_urlsafe(32)


def encrypt(value: str) -> str:
    return Fernet(settings().encryption_key.encode()).encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return Fernet(settings().encryption_key.encode()).decrypt(value.encode()).decode()


def signature(secret: str, timestamp: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def validate_destination(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.fragment or not parsed.hostname:
        raise ValueError("Destination must have a host and no credentials or fragment")
    config = settings()
    if config.app_env in {"demo", "test"} and parsed.hostname in {"demo-sink", "localhost", "127.0.0.1"}:
        # Only exact configured sink origin is allowed; arbitrary local ports are rejected.
        allowed = urlsplit(config.demo_sink_url)
        if (parsed.scheme, parsed.hostname, parsed.port) == (allowed.scheme, allowed.hostname, allowed.port):
            if parsed.path == "/webhook" and not parsed.query:
                return url
        raise ValueError("Local demo destinations must use the configured sink /webhook")
    if parsed.scheme != "https" or parsed.port not in {None, 443}:
        raise ValueError("Production destinations require HTTPS on port 443")
    approved = {h.strip().lower() for h in config.approved_hosts.split(",") if h.strip()}
    if parsed.hostname.lower() not in approved:
        raise ValueError("Destination host is not on APPROVED_HOSTS")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        if parsed.hostname.lower() in {"localhost", "metadata.google.internal"} or "." not in parsed.hostname:
            raise ValueError("Unsafe destination host")
    else:
        if not address.is_global:
            raise ValueError("Unsafe destination address")
    return url
