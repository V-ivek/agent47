from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request

from punk_records.api.deps import parse_iso8601_utc, verify_token
from punk_records.models.memory import MemoryStatus
from punk_records.store.event_store import EventStore


def _to_console_memory(entry: dict) -> dict:
    # Mirror the /memory endpoint contract for console use.

    def iso(v):
        if v is None:
            return None
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.astimezone(timezone.utc).isoformat()
        return str(v)

    content = entry.get("value")
    if isinstance(content, str):
        try:
            content_json = json.loads(content)
            content = json.dumps(content_json, sort_keys=True, separators=(",", ":"))
        except Exception:
            content = content

    status = (entry.get("status") or "").lower()
    expires_at = iso(entry.get("expires_at"))
    if expires_at is not None:
        status_mapped = "expired" if status == "promoted" else status
    else:
        status_mapped = "active" if status == "promoted" else status

    return {
        "id": str(entry.get("entry_id")),
        "workspace_id": entry.get("workspace_id"),
        "bucket": entry.get("bucket"),
        "content": content or "",
        "title": entry.get("key"),
        "summary": "",
        "confidence": entry.get("confidence"),
        "status": status_mapped,
        "created_at": iso(entry.get("created_at")),
        "updated_at": iso(entry.get("updated_at")),
        "source_event_id": (
            str(entry.get("source_event_id")) if entry.get("source_event_id") else None
        ),
    }


router = APIRouter()


@router.get("/context/{workspace_id}", dependencies=[Depends(verify_token)])
async def get_context(
    request: Request,
    workspace_id: str,
    limit: int = Query(10, ge=1, le=100),
    since: str | None = Query(None),
):
    """Console contract: ContextPack wrapper.

    Returns:
    {
      workspace_id, timestamp, sections:{memory,decisions,tasks,risks}
    }
    """

    if since is not None:
        since_dt = parse_iso8601_utc(since, field_name="since")
    else:
        since_dt = datetime.now(timezone.utc) - timedelta(days=7)

    memory_store = request.app.state.memory_store
    event_store = EventStore(request.app.state.database.pool)

    memory_raw = await memory_store.get_entries(workspace_id, status=MemoryStatus.PROMOTED)
    memory_console = [_to_console_memory(e) for e in memory_raw]

    decisions = await event_store.query_events(
        workspace_id, type="decision.recorded", after=since_dt, limit=limit
    )
    tasks = await event_store.query_events(
        workspace_id, type="task.created", after=since_dt, limit=limit
    )
    risks = await event_store.query_events(
        workspace_id, type="risk.detected", severity="high", after=since_dt, limit=limit
    )

    now = datetime.now(timezone.utc)
    return {
        # console:
        "workspace_id": workspace_id,
        "timestamp": now.isoformat(),
        "sections": {
            "memory": memory_console,
            "decisions": decisions,
            "tasks": tasks,
            "risks": risks,
        },
        # legacy (kept for compatibility):
        "generated_at": now.isoformat(),
        "memory": memory_raw,
        "decisions": decisions,
        "tasks": tasks,
        "risks": risks,
        "counts": {
            "memory": len(memory_raw),
            "decisions": len(decisions),
            "tasks": len(tasks),
            "risks": len(risks),
        },
    }
