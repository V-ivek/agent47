from fastapi import APIRouter
from fastapi.responses import Response

from punk_records.observability.metrics import metrics_payload

router = APIRouter()


@router.get("/metrics")
async def metrics() -> Response:
    payload, content_type = metrics_payload()
    return Response(content=payload, media_type=content_type)
