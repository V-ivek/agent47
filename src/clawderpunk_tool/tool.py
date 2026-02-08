from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from clawderpunk_tool.client import PunkRecordsClient
from clawderpunk_tool.config import ToolConfig


class ClawderpunkTool:
    def __init__(self, config: ToolConfig | None = None):
        self._config = config or ToolConfig()
        self._client: PunkRecordsClient | None = None

    async def __aenter__(self) -> ClawderpunkTool:
        self._client = PunkRecordsClient(self._config)
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.__aexit__(*args)
            self._client = None

    def _build_envelope(
        self,
        event_type: str,
        payload: dict,
        severity: str = "low",
        confidence: float = 0.0,
        trace_id: str | None = None,
    ) -> dict:
        return {
            "event_id": str(uuid4()),
            "schema_version": 1,
            "ts": datetime.now(timezone.utc).isoformat(),
            "workspace_id": self._config.workspace_id,
            "satellite_id": self._config.satellite_id,
            "trace_id": trace_id or str(uuid4()),
            "type": event_type,
            "severity": severity,
            "confidence": confidence,
            "payload": payload,
        }

    async def emit_event(
        self,
        event_type: str,
        payload: dict,
        severity: str = "low",
        confidence: float = 0.0,
        trace_id: str | None = None,
    ) -> dict:
        envelope = self._build_envelope(
            event_type, payload, severity, confidence, trace_id
        )
        return await self._client.post_event(envelope)

    async def get_context(self, limit: int = 10, since_days: int = 7) -> dict:
        since = None
        if since_days > 0:
            from datetime import timedelta

            since = (
                datetime.now(timezone.utc) - timedelta(days=since_days)
            ).isoformat()
        return await self._client.get_context(
            self._config.workspace_id, limit=limit, since=since
        )

    async def record_decision(
        self,
        decision: str,
        rationale: str,
        confidence: float = 0.8,
        trace_id: str | None = None,
    ) -> dict:
        payload = {"decision": decision, "rationale": rationale}
        return await self.emit_event(
            "decision.recorded",
            payload,
            severity="medium",
            confidence=confidence,
            trace_id=trace_id,
        )

    async def create_task(
        self,
        title: str,
        description: str,
        priority: str = "medium",
        trace_id: str | None = None,
    ) -> dict:
        payload = {
            "title": title,
            "description": description,
            "priority": priority,
        }
        return await self.emit_event(
            "task.created",
            payload,
            severity="low",
            confidence=0.0,
            trace_id=trace_id,
        )
