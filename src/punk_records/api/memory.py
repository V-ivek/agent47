from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from punk_records.models.memory import MemoryBucket, MemoryStatus

router = APIRouter()


async def verify_token(
    request: Request, authorization: str = Header(...)
):
    expected = (
        f"Bearer {request.app.state.settings.punk_records_api_token}"
    )
    if authorization != expected:
        raise HTTPException(
            status_code=401, detail="Invalid or missing token"
        )


@router.get(
    "/memory/{workspace_id}",
    dependencies=[Depends(verify_token)],
)
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
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid bucket: {bucket}",
            )
    status_enum = None
    if status is not None:
        try:
            status_enum = MemoryStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}",
            )
    entries = await memory_store.get_entries(
        workspace_id,
        bucket=bucket_enum,
        status=status_enum,
        include_expired=include_expired,
    )
    return {"entries": entries, "count": len(entries)}


@router.post(
    "/replay/{workspace_id}",
    dependencies=[Depends(verify_token)],
)
async def replay_workspace(
    request: Request,
    workspace_id: str,
):
    projection_engine = request.app.state.projection_engine
    result = await projection_engine.replay(workspace_id)
    return {
        "status": "completed",
        **result,
    }
