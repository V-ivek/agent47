from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class MemoryBucket(StrEnum):
    GLOBAL = "global"
    WORKSPACE = "workspace"
    EPHEMERAL = "ephemeral"


class MemoryStatus(StrEnum):
    CANDIDATE = "candidate"
    PROMOTED = "promoted"
    RETRACTED = "retracted"


class MemoryEntry(BaseModel):
    entry_id: UUID
    workspace_id: str = Field(min_length=1)
    bucket: MemoryBucket
    key: str = Field(min_length=1)
    value: dict[str, Any] = Field(default_factory=dict)
    status: MemoryStatus
    confidence: float = Field(ge=0.0, le=1.0)
    source_event_id: UUID
    promoted_at: datetime | None = None
    retracted_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator(
        "promoted_at", "retracted_at", "expires_at", "created_at", "updated_at",
        mode="before",
    )
    @classmethod
    def normalize_timestamps(cls, v: Any) -> datetime | None:
        if v is None:
            return None
        if isinstance(v, str):
            dt = datetime.fromisoformat(v)
        elif isinstance(v, datetime):
            dt = v
        else:
            raise ValueError("timestamp must be a datetime or ISO-8601 string")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt

    @model_validator(mode="after")
    def validate_ephemeral_expires(self) -> "MemoryEntry":
        if self.bucket == MemoryBucket.EPHEMERAL and self.expires_at is None:
            raise ValueError("ephemeral entries must have expires_at set")
        if self.bucket != MemoryBucket.EPHEMERAL and self.expires_at is not None:
            raise ValueError("only ephemeral entries may have expires_at")
        return self

    @model_validator(mode="after")
    def validate_status_timestamps(self) -> "MemoryEntry":
        if self.status == MemoryStatus.PROMOTED and self.promoted_at is None:
            raise ValueError("promoted entries must have promoted_at set")
        if self.status == MemoryStatus.RETRACTED and self.retracted_at is None:
            raise ValueError("retracted entries must have retracted_at set")
        return self

    model_config = {"str_strip_whitespace": True}
