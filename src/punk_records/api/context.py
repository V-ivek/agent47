from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from punk_records.models.context import ContextPack
from punk_records.models.memory import MemoryStatus
from punk_records.store.event_store import EventStore

router = APIRouter()


async def verify_token(request: Request, authorization: str = Header(...)):
    expected = f"Bearer {request.app.state.settings.punk_records_api_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing token")


@router.get(
    "/context/{workspace_id}",
    dependencies=[Depends(verify_token)],
)
async def get_context(
    request: Request,
    workspace_id: str,
    limit: int = Query(10, ge=1, le=100),
    since: str | None = Query(None),
):
    if since is not None:
        since_dt = datetime.fromisoformat(since)
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=timezone.utc)
    else:
        since_dt = datetime.now(timezone.utc) - timedelta(days=7)

    memory_store = request.app.state.memory_store
    event_store = EventStore(request.app.state.database.pool)

    memory = await memory_store.get_entries(
        workspace_id, status=MemoryStatus.PROMOTED
    )
    decisions = await event_store.query_events(
        workspace_id,
        type="decision.recorded",
        after=since_dt,
        limit=limit,
    )
    tasks = await event_store.query_events(
        workspace_id,
        type="task.created",
        after=since_dt,
        limit=limit,
    )
    risks = await event_store.query_events(
        workspace_id,
        type="risk.detected",
        severity="high",
        after=since_dt,
        limit=limit,
    )

    pack = ContextPack(
        workspace_id=workspace_id,
        generated_at=datetime.now(timezone.utc),
        memory=memory,
        decisions=decisions,
        tasks=tasks,
        risks=risks,
        counts={
            "memory": len(memory),
            "decisions": len(decisions),
            "tasks": len(tasks),
            "risks": len(risks),
        },
    )
    return pack
