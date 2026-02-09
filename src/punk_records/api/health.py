from datetime import datetime, timezone

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    """Console-friendly health endpoint.

    Contract (dashboard):
    {
      status: ok|degraded|down,
      details: { postgres: bool, kafka: bool },
      timestamp: ISO-8601
    }
    """

    db = request.app.state.database
    producer = request.app.state.producer

    pg_ok = await db.check_health()
    kafka_ok = await producer.check_health()

    if pg_ok and kafka_ok:
        status = "ok"
    elif pg_ok or kafka_ok:
        status = "degraded"
    else:
        status = "down"

    # Return a superset: console fields + legacy fields (harmless for UI).
    return {
        "status": status,
        "details": {"postgres": bool(pg_ok), "kafka": bool(kafka_ok)},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # legacy:
        "postgres": "ok" if pg_ok else "error",
        "kafka": "ok" if kafka_ok else "error",
    }
