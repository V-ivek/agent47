from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Header, HTTPException, Request


def parse_iso8601_utc(value: str, *, field_name: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: must be an ISO-8601 datetime",
        ) from exc

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def verify_token(request: Request, authorization: str | None = Header(default=None)):
    expected = f"Bearer {request.app.state.settings.punk_records_api_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
