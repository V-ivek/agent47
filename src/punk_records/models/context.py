from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ContextPack(BaseModel):
    workspace_id: str
    generated_at: datetime
    memory: list[dict] = Field(default_factory=list)
    decisions: list[dict] = Field(default_factory=list)
    tasks: list[dict] = Field(default_factory=list)
    risks: list[dict] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
