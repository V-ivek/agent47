from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from punk_records.api.console import iso_utc, map_console_memory_status
from punk_records.api.deps import verify_token
from punk_records.models.memory import MemoryBucket, MemoryStatus

router = APIRouter()


def _to_console_memory(row: dict[str, Any]) -> dict[str, Any]:
    content = row.get("value")
    # DB stores value as json string
    if isinstance(content, str):
        try:
            import json

            content_json = json.loads(content)
            content = json.dumps(content_json, sort_keys=True, separators=(",", ":"))
        except Exception:
            content = content

    entry_id = str(row.get("entry_id")) if row.get("entry_id") else None

    return {
        # console:
        "id": entry_id,
        "workspace_id": row.get("workspace_id"),
        "bucket": row.get("bucket"),
        "content": content or "",
        "title": row.get("key"),
        "summary": "",
        "confidence": row.get("confidence"),
        "status": map_console_memory_status(
            row.get("status"),
            expires_at=row.get("expires_at"),
        ),
        "created_at": iso_utc(row.get("created_at")),
        "updated_at": iso_utc(row.get("updated_at")),
        "source_event_id": str(row.get("source_event_id")) if row.get("source_event_id") else None,
        # legacy-ish:
        "entry_id": entry_id,
        "key": row.get("key"),
        "value": row.get("value"),
        "expires_at": iso_utc(row.get("expires_at")),
        "promoted_at": iso_utc(row.get("promoted_at")),
        "retracted_at": iso_utc(row.get("retracted_at")),
    }


@router.get("/memory/{workspace_id}", dependencies=[Depends(verify_token)])
async def get_memory(
    request: Request,
    workspace_id: str,
    bucket: str | None = Query(None),
    status: str | None = Query(None),
    include_expired: bool = Query(False),
):
    memory_store = request.app.state.memory_store

    bucket_enum = None
    if bucket is not None:
        try:
            bucket_enum = MemoryBucket(bucket)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid bucket: {bucket}") from e

    status_enum = None
    if status is not None:
        try:
            status_enum = MemoryStatus(status)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}") from e

    entries = await memory_store.get_entries(
        workspace_id,
        bucket=bucket_enum,
        status=status_enum,
        include_expired=include_expired,
    )

    return [_to_console_memory(e) for e in entries]


@router.post("/replay/{workspace_id}", dependencies=[Depends(verify_token)])
async def replay_workspace(request: Request, workspace_id: str):
    projection_engine = request.app.state.projection_engine
    result = await projection_engine.replay(workspace_id)
    return result
