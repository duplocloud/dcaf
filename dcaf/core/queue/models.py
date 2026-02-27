"""Pydantic models for the DCAF async job queue."""

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JobRequest(BaseModel):
    """Payload published to the jobs-in NATS stream when queue=true."""

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str
    messages: list[dict[str, Any]]
    request_fields: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


class JobStatus(BaseModel):
    """Current state of a queued job."""

    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    agent_name: str
    created_at: datetime
    updated_at: datetime | None = None
    error: str | None = None


class JobEvent(BaseModel):
    """A single event emitted by an agent worker for a job."""

    job_id: str
    seq: int = 0
    event_type: str  # "log" | "status" | "done" | "error"
    message: str | None = None
    data: dict[str, Any] | None = None
    timestamp: datetime = Field(default_factory=_now)
