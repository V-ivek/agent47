from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _coerce_utc_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_utc(value: Any) -> str | None:
    dt = _coerce_utc_datetime(value)
    if dt is None:
        if value is None:
            return None
        return str(value)
    return dt.isoformat()


def map_console_memory_status(
    status: str | None,
    *,
    expires_at: Any,
    now: datetime | None = None,
) -> str:
    normalized = (status or "").lower()

    if normalized == "promoted":
        expires_at_dt = _coerce_utc_datetime(expires_at)
        if expires_at_dt is None:
            return "active"

        if now is None:
            now = datetime.now(timezone.utc)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)

        return "expired" if expires_at_dt <= now else "active"

    if normalized == "retracted":
        return "archived"

    return normalized
