from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EventType(StrEnum):
    PROPOSAL_CREATED = "proposal.created"
    DECISION_RECORDED = "decision.recorded"
    RISK_DETECTED = "risk.detected"
    FINDING_LOGGED = "finding.logged"
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    MEMORY_CANDIDATE = "memory.candidate"
    MEMORY_PROMOTED = "memory.promoted"
    MEMORY_RETRACTED = "memory.retracted"


class EventEnvelope(BaseModel):
    event_id: UUID
    schema_version: int = Field(ge=1, le=1)
    ts: datetime
    workspace_id: str = Field(min_length=1)
    satellite_id: str = Field(min_length=1)
    trace_id: UUID
    type: EventType
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ts", mode="before")
    @classmethod
    def normalize_ts_to_utc(cls, v: Any) -> datetime:
        if isinstance(v, str):
            dt = datetime.fromisoformat(v)
        elif isinstance(v, datetime):
            dt = v
        else:
            raise ValueError("ts must be a datetime or ISO-8601 string")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt

    def to_kafka_value(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def from_kafka_value(cls, data: bytes) -> "EventEnvelope":
        return cls.model_validate_json(data)

    def kafka_key(self) -> bytes:
        return self.workspace_id.encode("utf-8")

    model_config = {"str_strip_whitespace": True}
