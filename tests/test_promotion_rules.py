from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from punk_records.models.memory import MemoryEntry
from punk_records.projections.rules import (
    CONFIDENCE_THRESHOLD,
    MIN_REFERENCES,
    PromotionEvaluator,
)


def make_candidate(**overrides):
    defaults = {
        "entry_id": uuid4(),
        "workspace_id": "ws-test",
        "bucket": "workspace",
        "key": "test.key",
        "value": {"data": "test"},
        "status": "candidate",
        "confidence": 0.8,
        "source_event_id": uuid4(),
    }
    defaults.update(overrides)
    return MemoryEntry(**defaults)


@pytest.fixture()
def event_store():
    store = AsyncMock()
    store.count_references = AsyncMock(return_value=0)
    store.has_event_type_in_trace = AsyncMock(return_value=False)
    return store


@pytest.fixture()
def evaluator(event_store):
    return PromotionEvaluator(event_store)


async def test_eligible_high_confidence_enough_references(
    evaluator, event_store
):
    """Candidate with high confidence and enough references is eligible."""
    entry = make_candidate(confidence=0.8)
    trace_id = uuid4()
    event_store.count_references.return_value = 3

    result = await evaluator.is_eligible(entry, trace_id)

    assert result is True
    event_store.count_references.assert_awaited_once()
    # Should not need to check decision since references suffice
    event_store.has_event_type_in_trace.assert_not_awaited()


async def test_eligible_high_confidence_decision_recorded(
    evaluator, event_store
):
    """Candidate with high confidence derived from decision is eligible."""
    entry = make_candidate(confidence=0.8)
    trace_id = uuid4()
    event_store.count_references.return_value = 0
    event_store.has_event_type_in_trace.return_value = True

    result = await evaluator.is_eligible(entry, trace_id)

    assert result is True
    event_store.count_references.assert_awaited_once()
    event_store.has_event_type_in_trace.assert_awaited_once_with(
        entry.workspace_id, trace_id, "decision.recorded"
    )


async def test_not_eligible_low_confidence(evaluator, event_store):
    """Low confidence candidate is not eligible; no store calls made."""
    entry = make_candidate(confidence=0.5)
    trace_id = uuid4()

    result = await evaluator.is_eligible(entry, trace_id)

    assert result is False
    event_store.count_references.assert_not_awaited()
    event_store.has_event_type_in_trace.assert_not_awaited()


async def test_not_eligible_high_confidence_no_references_no_decision(
    evaluator, event_store
):
    """High confidence but no references and no decision -> not eligible."""
    entry = make_candidate(confidence=0.8)
    trace_id = uuid4()
    event_store.count_references.return_value = 0
    event_store.has_event_type_in_trace.return_value = False

    result = await evaluator.is_eligible(entry, trace_id)

    assert result is False


async def test_not_eligible_wrong_status(evaluator, event_store):
    """Non-candidate entries are not eligible."""
    entry = make_candidate(
        status="promoted",
        confidence=0.9,
        promoted_at=datetime.now(timezone.utc),
    )
    trace_id = uuid4()

    result = await evaluator.is_eligible(entry, trace_id)

    assert result is False
    event_store.count_references.assert_not_awaited()
    event_store.has_event_type_in_trace.assert_not_awaited()


async def test_boundary_confidence_exactly_threshold(
    evaluator, event_store
):
    """Confidence exactly at threshold proceeds to check references."""
    entry = make_candidate(confidence=CONFIDENCE_THRESHOLD)
    trace_id = uuid4()
    event_store.count_references.return_value = MIN_REFERENCES

    result = await evaluator.is_eligible(entry, trace_id)

    assert result is True
    event_store.count_references.assert_awaited_once()


async def test_boundary_confidence_just_below(evaluator, event_store):
    """Confidence just below threshold is not eligible."""
    entry = make_candidate(confidence=0.749)
    trace_id = uuid4()

    result = await evaluator.is_eligible(entry, trace_id)

    assert result is False
    event_store.count_references.assert_not_awaited()


async def test_boundary_references_exactly_two(evaluator, event_store):
    """Exactly MIN_REFERENCES references is eligible (>= check)."""
    entry = make_candidate(confidence=0.8)
    trace_id = uuid4()
    event_store.count_references.return_value = 2

    result = await evaluator.is_eligible(entry, trace_id)

    assert result is True
    event_store.has_event_type_in_trace.assert_not_awaited()


async def test_boundary_references_one(evaluator, event_store):
    """One reference and no decision -> not eligible."""
    entry = make_candidate(confidence=0.8)
    trace_id = uuid4()
    event_store.count_references.return_value = 1
    event_store.has_event_type_in_trace.return_value = False

    result = await evaluator.is_eligible(entry, trace_id)

    assert result is False
