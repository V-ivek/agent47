from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response

from punk_records.models.events import EventEnvelope
from punk_records.store.event_store import EventStore

router = APIRouter()


async def verify_token(request: Request, authorization: str = Header(...)):
    expected = f"Bearer {request.app.state.settings.punk_records_api_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing token")


def _to_console_event(row: dict[str, Any]) -> dict[str, Any]:
    # rows from asyncpg include `payload_json` as json string
    payload = row.get("payload_json")
    try:
        if isinstance(payload, str):
            import json

            payload = json.loads(payload)
    except Exception:
        payload = payload

    ts = row.get("ts")
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts = ts.astimezone(timezone.utc).isoformat()

    return {
        "id": str(row.get("event_id")),
        "type": row.get("type"),
        "payload": payload or {},
        "metadata": {},
        "workspace_id": row.get("workspace_id"),
        "trace_id": str(row.get("trace_id")) if row.get("trace_id") else None,
        "satellite_id": row.get("satellite_id"),
        "severity": row.get("severity"),
        "confidence": row.get("confidence"),
        "timestamp": ts,
    }


@router.post("/events", status_code=204, dependencies=[Depends(verify_token)])
async def post_event(event: EventEnvelope, request: Request) -> Response:
    # Asynchronous ingest: accept and publish to backbone.
    producer = request.app.state.producer
    await producer.send_event(event)
    return Response(status_code=204)


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
