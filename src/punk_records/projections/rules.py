import logging
from datetime import timedelta
from uuid import UUID

from punk_records.models.memory import MemoryEntry, MemoryStatus
from punk_records.store.event_store import EventStore

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.75
REFERENCE_WINDOW_DAYS = 7
MIN_REFERENCES = 2


class PromotionEvaluator:
    """Evaluates whether a candidate memory entry is eligible for promotion."""

    def __init__(self, event_store: EventStore):
        self._event_store = event_store

    async def is_eligible(
        self, entry: MemoryEntry, trace_id: UUID
    ) -> bool:
        """Check if a candidate memory entry is eligible for promotion.

        A candidate is eligible when:
        - Its status is CANDIDATE
        - Its confidence >= CONFIDENCE_THRESHOLD (0.75)
        - AND at least one of:
          - Referenced by >= MIN_REFERENCES events within REFERENCE_WINDOW_DAYS
          - Derived from a decision.recorded event in the same trace
        """
        if entry.status != MemoryStatus.CANDIDATE:
            return False

        if entry.confidence < CONFIDENCE_THRESHOLD:
            return False

        # Check: referenced by >= 2 events in 7 days
        since_ts = entry.created_at - timedelta(days=REFERENCE_WINDOW_DAYS)
        ref_count = await self._event_store.count_references(
            entry.workspace_id, trace_id, since_ts
        )
        if ref_count >= MIN_REFERENCES:
            return True

        # Check: derived from decision.recorded
        has_decision = await self._event_store.has_event_type_in_trace(
            entry.workspace_id, trace_id, "decision.recorded"
        )
        return has_decision
