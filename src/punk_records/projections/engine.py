import json
import logging
from datetime import timedelta
from uuid import uuid4

from punk_records.kafka.producer import EventProducer
from punk_records.models.events import EventEnvelope, EventType
from punk_records.models.memory import (
    MemoryBucket,
    MemoryEntry,
    MemoryStatus,
)
from punk_records.projections.rules import PromotionEvaluator
from punk_records.store.event_store import EventStore
from punk_records.store.memory_store import MemoryStore

logger = logging.getLogger(__name__)

MEMORY_EVENT_TYPES = {
    EventType.MEMORY_CANDIDATE,
    EventType.MEMORY_PROMOTED,
    EventType.MEMORY_RETRACTED,
}

DEFAULT_EPHEMERAL_TTL_HOURS = 24


class ProjectionEngine:
    def __init__(
        self,
        event_store: EventStore,
        memory_store: MemoryStore,
        producer: EventProducer | None = None,
    ):
        self._event_store = event_store
        self._memory_store = memory_store
        self._producer = producer
        self._evaluator = PromotionEvaluator(event_store)

    async def process(self, event: EventEnvelope) -> None:
        """Process an event for memory projections."""
        if event.type == EventType.MEMORY_CANDIDATE:
            await self._handle_candidate(event)
        elif event.type == EventType.MEMORY_PROMOTED:
            await self._handle_promoted(event)
        elif event.type == EventType.MEMORY_RETRACTED:
            await self._handle_retracted(event)

        # Check auto-promotion for candidates in this workspace
        await self._check_auto_promotion(event)

        # Update cursor
        await self._memory_store.update_cursor(
            event.event_id, event.ts
        )

    async def _handle_candidate(self, event: EventEnvelope) -> None:
        """Create a memory entry from a memory.candidate event."""
        payload = event.payload
        bucket = MemoryBucket(payload.get("bucket", "workspace"))
        expires_at = None
        if bucket == MemoryBucket.EPHEMERAL:
            ttl_hours = payload.get(
                "ttl_hours", DEFAULT_EPHEMERAL_TTL_HOURS
            )
            expires_at = event.ts + timedelta(hours=ttl_hours)

        entry = MemoryEntry(
            entry_id=event.event_id,
            workspace_id=event.workspace_id,
            bucket=bucket,
            key=payload.get("key", ""),
            value=payload.get("value", {}),
            status=MemoryStatus.CANDIDATE,
            confidence=event.confidence,
            source_event_id=event.event_id,
            expires_at=expires_at,
            created_at=event.ts,
            updated_at=event.ts,
        )
        inserted = await self._memory_store.create_entry(entry)
        if inserted:
            logger.info(
                "Created memory candidate %s (key=%s)",
                entry.entry_id, entry.key,
            )

    async def _handle_promoted(self, event: EventEnvelope) -> None:
        """Update a memory entry to promoted status."""
        entry_id = event.payload.get("entry_id")
        if entry_id is None:
            logger.warning(
                "memory.promoted event %s missing entry_id in payload",
                event.event_id,
            )
            return
        from uuid import UUID as _UUID
        updated = await self._memory_store.update_status(
            _UUID(entry_id), MemoryStatus.PROMOTED, event.ts,
        )
        if updated:
            logger.info("Promoted memory entry %s", entry_id)
        else:
            logger.warning(
                "Failed to promote entry %s (not found)", entry_id
            )

    async def _handle_retracted(self, event: EventEnvelope) -> None:
        """Update a memory entry to retracted status."""
        entry_id = event.payload.get("entry_id")
        if entry_id is None:
            logger.warning(
                "memory.retracted event %s missing entry_id",
                event.event_id,
            )
            return
        from uuid import UUID as _UUID
        updated = await self._memory_store.update_status(
            _UUID(entry_id), MemoryStatus.RETRACTED, event.ts,
        )
        if updated:
            logger.info("Retracted memory entry %s", entry_id)
        else:
            logger.warning(
                "Failed to retract entry %s (not found)", entry_id
            )

    async def _check_auto_promotion(
        self, event: EventEnvelope
    ) -> None:
        """Check if any candidates are now eligible for promotion."""
        candidates = await self._memory_store.get_entries(
            event.workspace_id,
            status=MemoryStatus.CANDIDATE,
        )
        for row in candidates:
            raw_value = row.get("value", {})
            if isinstance(raw_value, str):
                raw_value = json.loads(raw_value)
            entry = MemoryEntry(
                entry_id=row["entry_id"],
                workspace_id=row["workspace_id"],
                bucket=row["bucket"],
                key=row["key"],
                value=raw_value,
                status=row["status"],
                confidence=row["confidence"],
                source_event_id=row["source_event_id"],
                expires_at=row.get("expires_at"),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            eligible = await self._evaluator.is_eligible(
                entry, event.trace_id
            )
            if eligible:
                await self._auto_promote(entry, event)

    async def _auto_promote(
        self, entry: MemoryEntry, trigger_event: EventEnvelope
    ) -> None:
        """Auto-promote an eligible candidate by emitting a synthetic event."""
        synthetic = EventEnvelope(
            event_id=uuid4(),
            schema_version=1,
            ts=trigger_event.ts,
            workspace_id=entry.workspace_id,
            satellite_id="punk-records.projection-engine",
            trace_id=trigger_event.trace_id,
            type=EventType.MEMORY_PROMOTED,
            severity=trigger_event.severity,
            confidence=entry.confidence,
            payload={"entry_id": str(entry.entry_id)},
        )
        if self._producer:
            await self._producer.send_event(synthetic)
            logger.info(
                "Auto-promoted candidate %s via synthetic event %s",
                entry.entry_id, synthetic.event_id,
            )
        else:
            # No producer — apply directly (for replay)
            await self._handle_promoted(synthetic)

    async def replay(self, workspace_id: str) -> dict:
        """Replay all events for a workspace to rebuild projections."""
        deleted = await self._memory_store.delete_workspace_entries(
            workspace_id
        )
        events = await self._event_store.get_workspace_events(
            workspace_id
        )
        entries_created = 0
        for row in events:
            raw_payload = row.get("payload_json", {})
            if isinstance(raw_payload, str):
                raw_payload = json.loads(raw_payload)
            event = EventEnvelope(
                event_id=row["event_id"],
                schema_version=1,
                ts=row["ts"],
                workspace_id=row["workspace_id"],
                satellite_id=row["satellite_id"],
                trace_id=row["trace_id"],
                type=row["type"],
                severity=row["severity"],
                confidence=row["confidence"],
                payload=raw_payload,
            )
            if event.type in MEMORY_EVENT_TYPES:
                if event.type == EventType.MEMORY_CANDIDATE:
                    await self._handle_candidate(event)
                    entries_created += 1
                elif event.type == EventType.MEMORY_PROMOTED:
                    await self._handle_promoted(event)
                elif event.type == EventType.MEMORY_RETRACTED:
                    await self._handle_retracted(event)

        logger.info(
            "Replay for %s: deleted=%d, events=%d, created=%d",
            workspace_id, deleted, len(events), entries_created,
        )
        return {
            "entries_deleted": deleted,
            "events_replayed": len(events),
            "entries_created": entries_created,
        }
