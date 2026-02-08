import json
import logging

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
