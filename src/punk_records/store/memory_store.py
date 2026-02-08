import json
import logging
from datetime import datetime
from uuid import UUID

import asyncpg

from punk_records.models.memory import MemoryBucket, MemoryEntry, MemoryStatus

logger = logging.getLogger(__name__)

INSERT_ENTRY_SQL = """
INSERT INTO memory_entries (
    entry_id, workspace_id, bucket, key, value, status, confidence,
    source_event_id, promoted_at, retracted_at, expires_at,
    created_at, updated_at
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
ON CONFLICT (source_event_id) DO NOTHING
"""

UPDATE_STATUS_PROMOTED_SQL = """
UPDATE memory_entries
SET status = $1, promoted_at = $2, updated_at = $2
WHERE entry_id = $3
"""

UPDATE_STATUS_RETRACTED_SQL = """
UPDATE memory_entries
SET status = $1, retracted_at = $2, updated_at = $2
WHERE entry_id = $3
"""

DELETE_WORKSPACE_SQL = """
DELETE FROM memory_entries WHERE workspace_id = $1
"""

GET_CURSOR_SQL = """
SELECT last_event_id, last_event_ts
FROM projection_cursor
WHERE cursor_id = 'global'
"""

UPSERT_CURSOR_SQL = """
INSERT INTO projection_cursor (cursor_id, last_event_id, last_event_ts, updated_at)
VALUES ('global', $1, $2, NOW())
ON CONFLICT (cursor_id)
DO UPDATE SET last_event_id = $1, last_event_ts = $2, updated_at = NOW()
"""


class MemoryStore:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def create_entry(self, entry: MemoryEntry) -> bool:
        """Insert a memory entry idempotently. Returns True if inserted."""
        async with self._pool.acquire() as conn:
            status = await conn.execute(
                INSERT_ENTRY_SQL,
                entry.entry_id,
                entry.workspace_id,
                entry.bucket.value,
                entry.key,
                json.dumps(entry.value),
                entry.status.value,
                entry.confidence,
                entry.source_event_id,
                entry.promoted_at,
                entry.retracted_at,
                entry.expires_at,
                entry.created_at,
                entry.updated_at,
            )
        inserted = status == "INSERT 0 1"
        if inserted:
            logger.debug("Created memory entry %s", entry.entry_id)
        else:
            logger.debug("Duplicate memory entry %s skipped", entry.entry_id)
        return inserted

    async def update_status(
        self, entry_id: UUID, status: MemoryStatus, timestamp: datetime
    ) -> bool:
        """Update status of a memory entry. Returns True if updated."""
        if status == MemoryStatus.PROMOTED:
            sql = UPDATE_STATUS_PROMOTED_SQL
        else:
            sql = UPDATE_STATUS_RETRACTED_SQL

        async with self._pool.acquire() as conn:
            result = await conn.execute(sql, status.value, timestamp, entry_id)

        # result is e.g. "UPDATE 1" or "UPDATE 0"
        count = int(result.split()[-1])
        if count > 0:
            logger.debug("Updated entry %s to %s", entry_id, status)
        else:
            logger.debug("Entry %s not found for status update", entry_id)
        return count > 0

    async def get_entries(
        self,
        workspace_id: str,
        bucket: MemoryBucket | None = None,
        status: MemoryStatus | None = None,
        include_expired: bool = False,
    ) -> list[dict]:
        """Query memory entries with optional filters."""
        effective_status = status if status is not None else MemoryStatus.PROMOTED
        conditions = ["workspace_id = $1", "status = $2"]
        params: list = [workspace_id, effective_status.value]
        idx = 3

        if bucket is not None:
            conditions.append(f"bucket = ${idx}")
            params.append(bucket.value)
            idx += 1

        if not include_expired:
            conditions.append("(expires_at IS NULL OR expires_at > NOW())")

        where = " AND ".join(conditions)
        sql = f"SELECT * FROM memory_entries WHERE {where}"  # noqa: S608

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        return [dict(r) for r in rows]

    async def delete_workspace_entries(self, workspace_id: str) -> int:
        """Delete all memory entries for a workspace. Returns count."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(DELETE_WORKSPACE_SQL, workspace_id)

        # result is e.g. "DELETE 5"
        count = int(result.split()[-1])
        logger.debug("Deleted %d entries for workspace %s", count, workspace_id)
        return count

    async def get_cursor(self) -> tuple[UUID, datetime] | None:
        """Get the global projection cursor. Returns None if unset."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(GET_CURSOR_SQL)

        if row is None:
            return None
        return (row["last_event_id"], row["last_event_ts"])

    async def update_cursor(
        self, event_id: UUID, event_ts: datetime
    ) -> None:
        """Upsert the global projection cursor."""
        async with self._pool.acquire() as conn:
            await conn.execute(UPSERT_CURSOR_SQL, event_id, event_ts)
        logger.debug("Updated cursor to event %s", event_id)
