from fastapi import APIRouter, Depends, Header, HTTPException, Request

from punk_records.models.events import EventEnvelope

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
