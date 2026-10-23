from typing import Any, Literal
from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class DestinationIn(NameIn):
    project_id: str
    url: str = Field(max_length=2048)
    event_types: list[str] = Field(default=["*"], min_length=1, max_length=100)
    signing_secret: str | None = Field(default=None, min_length=16, max_length=256)


class DestinationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    event_types: list[str] | None = Field(default=None, min_length=1, max_length=100)


class EventIn(BaseModel):
    project_id: str
    type: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")
    payload: dict[str, Any]


class ScenarioIn(BaseModel):
    mode: Literal["normal", "intermittent", "rate_limit", "latency", "timeout", "unavailable"]


class GenerateIn(BaseModel):
    project_id: str
    count: int = Field(default=20, ge=1, le=100)
    seed: int = 42


class PolicyIn(BaseModel):
    timeout_seconds: float = Field(gt=0, le=30)
    max_attempts: int = Field(ge=1, le=20)
    backoff_base: float = Field(ge=0.1, le=60)
    backoff_cap: float = Field(ge=1, le=3600)
    canary_percent: int = Field(ge=0, le=100)
