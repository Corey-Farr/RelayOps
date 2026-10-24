from functools import lru_cache
from pydantic import Field, model_validator
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
    lease_seconds: int = Field(default=60, ge=35, le=3600)
    shutdown_grace_seconds: float = Field(default=35, gt=0, le=120)
    heartbeat_seconds: int = Field(default=5, ge=1, le=60)
    failover_seconds: int = Field(default=20, ge=2, le=3600)
    max_queue_depth: int = Field(default=10000, ge=1)
    max_payload_bytes: int = Field(default=262144, ge=1024, le=10485760)
    session_hours: int = Field(default=12, ge=1, le=168)
    slo_target: float = Field(default=0.99, gt=0, lt=1)
    slo_deadline_seconds: int = Field(default=30, ge=1, le=3600)
    slo_min_samples: int = Field(default=20, ge=1)
    incident_dead_letter_threshold: int = Field(default=10, ge=1)
    otel_exporter_otlp_endpoint: str = ""

    @model_validator(mode="after")
    def validate_settings(self):
        if self.app_env not in {"demo", "production", "test"}:
            raise ValueError("APP_ENV must be demo, production, or test")
        if not 1 <= self.worker_concurrency <= 128:
            raise ValueError("WORKER_CONCURRENCY must be 1..128")
        if self.worker_region not in {"us-east", "eu-west", "ap-southeast"}:
            raise ValueError("Unknown worker region")
        if self.failover_seconds <= self.heartbeat_seconds:
            raise ValueError("FAILOVER_SECONDS must exceed HEARTBEAT_SECONDS")
        if self.app_env == "production" and (len(self.session_secret) < 32 or not self.approved_hosts):
            raise ValueError("Production requires SESSION_SECRET and APPROVED_HOSTS")
        return self


@lru_cache
def settings():
    return Settings()
