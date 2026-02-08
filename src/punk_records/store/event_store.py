import json
import logging
from datetime import datetime
from uuid import UUID

import asyncpg

from punk_records.models.events import EventEnvelope

logger = logging.getLogger(__name__)

INSERT_SQL = """
INSERT INTO events (
    event_id, ts, workspace_id, satellite_id, trace_id,
    type, severity, confidence, payload_json
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
ON CONFLICT (event_id) DO NOTHING
"""


class EventStore:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def persist(self, event: EventEnvelope) -> bool:
        """Persist an event idempotently. Returns True if inserted, False if duplicate."""
        async with self._pool.acquire() as conn:
            status = await conn.execute(
                INSERT_SQL,
                event.event_id,
                event.ts,
                event.workspace_id,
                event.satellite_id,
                event.trace_id,
                event.type.value,
                event.severity.value,
                event.confidence,
                json.dumps(event.payload),
            )
        inserted = status == "INSERT 0 1"
        if inserted:
            logger.debug("Persisted event %s", event.event_id)
        else:
            logger.debug("Duplicate event %s skipped", event.event_id)
        return inserted

    async def query_events(
        self,
        workspace_id: str,
        type: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Query events with optional filters, ordered by ts ASC."""
        limit = min(limit, 200)
        sql = "SELECT * FROM events WHERE workspace_id = $1"
        params: list = [workspace_id]
        idx = 2

        if type is not None:
            sql += f" AND type = ${idx}"
            params.append(type)
            idx += 1
        if after is not None:
            sql += f" AND ts > ${idx}"
            params.append(after)
            idx += 1
        if before is not None:
            sql += f" AND ts < ${idx}"
            params.append(before)
            idx += 1

        sql += f" ORDER BY ts ASC LIMIT ${idx} OFFSET ${idx + 1}"
        params.extend([limit, offset])

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    async def count_events(
        self,
        workspace_id: str,
        type: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
    ) -> int:
        """Count events matching optional filters."""
        sql = (
            "SELECT COUNT(*) FROM events WHERE workspace_id = $1"
        )
        params: list = [workspace_id]
        idx = 2

        if type is not None:
            sql += f" AND type = ${idx}"
            params.append(type)
            idx += 1
        if after is not None:
            sql += f" AND ts > ${idx}"
            params.append(after)
            idx += 1
        if before is not None:
            sql += f" AND ts < ${idx}"
            params.append(before)
            idx += 1

        async with self._pool.acquire() as conn:
            return await conn.fetchval(sql, *params)

    async def get_workspace_events(
        self,
        workspace_id: str,
        types: list[str] | None = None,
        after_ts: datetime | None = None,
    ) -> list[dict]:
        """Get all events for a workspace in ts order (for replay)."""
        sql = "SELECT * FROM events WHERE workspace_id = $1"
        params: list = [workspace_id]
        idx = 2

        if types is not None:
            sql += f" AND type = ANY(${idx})"
            params.append(types)
            idx += 1
        if after_ts is not None:
            sql += f" AND ts > ${idx}"
            params.append(after_ts)
            idx += 1

        sql += " ORDER BY ts ASC"

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    async def count_references(
        self,
        workspace_id: str,
        trace_id: UUID,
        since_ts: datetime,
    ) -> int:
        """Count events with same trace_id since a timestamp."""
        sql = (
            "SELECT COUNT(*) FROM events"
            " WHERE workspace_id = $1"
            " AND trace_id = $2"
            " AND ts >= $3"
        )
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                sql, workspace_id, trace_id, since_ts
            )

    async def has_event_type_in_trace(
        self,
        workspace_id: str,
        trace_id: UUID,
        event_type: str,
    ) -> bool:
        """Check if a specific event type exists in a trace."""
        sql = (
            "SELECT EXISTS("
            "SELECT 1 FROM events"
            " WHERE workspace_id = $1"
            " AND trace_id = $2"
            " AND type = $3"
            ")"
        )
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                sql, workspace_id, trace_id, event_type
            )
