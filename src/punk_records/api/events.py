from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError

from punk_records.api.deps import parse_iso8601_utc, verify_token
from punk_records.models.events import EventEnvelope, EventType, Severity
from punk_records.store.event_store import EventStore

router = APIRouter()


class ConsoleEventEnvelope(BaseModel):
    """Looser event schema used by the Console UI.

    The UI OpenAPI only requires `type` + `payload`. We enrich server-side.
    """

    id: str | None = None
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    workspace_id: str | None = None
    trace_id: str | None = None
    severity: str | None = None  # info|warning|error|critical
    timestamp: str | None = None


def _severity_to_console(s: str | None) -> str | None:
    if s is None:
        return None
    s = s.lower()
    return {"low": "info", "medium": "warning", "high": "error"}.get(s, s)


def _severity_from_console(s: str | None) -> Severity:
    if not s:
        return Severity.LOW

    value = {
        "info": Severity.LOW,
        "warning": Severity.MEDIUM,
        "error": Severity.HIGH,
        "critical": Severity.HIGH,
        "low": Severity.LOW,
        "medium": Severity.MEDIUM,
        "high": Severity.HIGH,
    }.get(s.lower())

    if value is None:
        raise ValueError(f"Invalid severity: {s}")
    return value


def _to_console_event(row: dict[str, Any]) -> dict[str, Any]:
    # rows from asyncpg include `payload_json` as json string
    payload = row.get("payload_json")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {"raw": payload}

    ts = row.get("ts")
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts = ts.astimezone(timezone.utc).isoformat()

    event_id = str(row.get("event_id")) if row.get("event_id") else None

    return {
        # console fields:
        "id": event_id,
        "type": row.get("type"),
        "payload": payload or {},
        "metadata": {},
        "workspace_id": row.get("workspace_id"),
        "trace_id": str(row.get("trace_id")) if row.get("trace_id") else None,
        "satellite_id": row.get("satellite_id"),
        "severity": _severity_to_console(row.get("severity")),
        "confidence": row.get("confidence"),
        "timestamp": ts,
        # legacy-ish aliases (harmless for UI):
        "event_id": event_id,
        "ts": ts,
        "schema_version": 1,
    }


@router.post("/events", status_code=201, dependencies=[Depends(verify_token)])
async def post_event(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """Emit an event.

    Accepts either:
    - Internal EventEnvelope schema (OpenClaw/satellites)
    - Console schema (UI) that only requires: {type, payload, workspace_id}

    We detect internal events by presence of `event_id`.
    """

    if "event_id" in body:
        # Internal envelope
        try:
            internal = EventEnvelope.model_validate(body)
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=e.errors()) from e
    else:
        # Console envelope
        try:
            event = ConsoleEventEnvelope.model_validate(body)
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=e.errors()) from e

        if not event.workspace_id:
            raise HTTPException(status_code=400, detail="workspace_id is required")

        try:
            event_type = EventType(event.type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Unknown event type: {event.type}") from e

        event_id = UUID(event.id) if event.id else uuid4()
        trace_id = UUID(event.trace_id) if event.trace_id else uuid4()

        if event.timestamp:
            ts = parse_iso8601_utc(event.timestamp, field_name="timestamp")
        else:
            ts = datetime.now(timezone.utc)

        try:
            severity = _severity_from_console(event.severity)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        internal = EventEnvelope(
            event_id=event_id,
            schema_version=1,
            ts=ts,
            workspace_id=event.workspace_id,
            satellite_id=str(event.metadata.get("satellite_id") or "console"),
            trace_id=trace_id,
            type=event_type,
            severity=severity,
            confidence=float(event.metadata.get("confidence") or 0.0),
            payload=event.payload,
        )

    producer = request.app.state.producer
    await producer.send_event(internal)

    return {
        "status": "accepted",
        # console:
        "id": str(internal.event_id),
        "timestamp": internal.ts.astimezone(timezone.utc).isoformat(),
        # legacy:
        "event_id": str(internal.event_id),
    }


@router.get("/events", dependencies=[Depends(verify_token)])
async def get_events(
    request: Request,
    workspace_id: str = Query(..., min_length=1),
    type: str | None = Query(None),
    after: datetime | None = Query(None),
    before: datetime | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Console contract: returns a JSON array of events."""

    event_store = EventStore(request.app.state.database.pool)
    events = await event_store.query_events(
        workspace_id, type, after, before, limit, offset
    )
    return [_to_console_event(e) for e in events]
