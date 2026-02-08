from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from punk_records.models.events import EventEnvelope
from punk_records.store.event_store import EventStore

router = APIRouter()


async def verify_token(request: Request, authorization: str = Header(...)):
    expected = f"Bearer {request.app.state.settings.punk_records_api_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing token")


@router.post("/events", status_code=202, dependencies=[Depends(verify_token)])
async def post_event(event: EventEnvelope, request: Request):
    producer = request.app.state.producer
    await producer.send_event(event)
    return {"status": "accepted", "event_id": str(event.event_id)}


@router.get("/events", dependencies=[Depends(verify_token)])
async def get_events(
    request: Request,
    workspace_id: str = Query(..., min_length=1),
    type: str | None = Query(None),
    after: datetime | None = Query(None),
    before: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    event_store = EventStore(request.app.state.database.pool)
    events = await event_store.query_events(
        workspace_id, type, after, before, limit, offset
    )
    total = await event_store.count_events(
        workspace_id, type, after, before
    )
    return {
        "events": events,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
