from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+asyncpg://relayops:relayops@localhost:5432/relayops"
    app_env: str = "demo"
    session_secret: str = ""
    encryption_key: str = ""
    admin_email: str = "admin@relayops.local"
    admin_password: str = ""
    demo_signing_secret: str = ""
    demo_control_token: str = ""
    demo_sink_url: str = "http://demo-sink:8081"
    approved_hosts: str = ""
    worker_region: str = "us-east"
    worker_id: str = ""
    worker_concurrency: int = 8
    worker_metrics_port: int = 9000
    lease_seconds: int = 60
    heartbeat_seconds: int = 5
    failover_seconds: int = 20
    max_queue_depth: int = 10000
    max_payload_bytes: int = 262144
    session_hours: int = 12
    slo_target: float = 0.99
    slo_deadline_seconds: int = 30
    slo_min_samples: int = 20
    incident_dead_letter_threshold: int = 10
    otel_exporter_otlp_endpoint: str = ""

    @model_validator(mode="after")
    def validate_settings(self):
        if self.app_env not in {"demo", "production", "test"}:
            raise ValueError("APP_ENV must be demo, production, or test")
        if not 1 <= self.worker_concurrency <= 128:
            raise ValueError("WORKER_CONCURRENCY must be 1..128")
        if self.app_env == "production" and (len(self.session_secret) < 32 or not self.approved_hosts):
            raise ValueError("Production requires SESSION_SECRET and APPROVED_HOSTS")
        return self


@lru_cache
def settings():
    return Settings()
