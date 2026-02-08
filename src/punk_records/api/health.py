from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    db = request.app.state.database
    producer = request.app.state.producer

    pg_ok = await db.check_health()
    kafka_ok = await producer.check_health()

    status = "healthy" if (pg_ok and kafka_ok) else "unhealthy"
    return {
        "status": status,
        "postgres": "ok" if pg_ok else "error",
        "kafka": "ok" if kafka_ok else "error",
    }
