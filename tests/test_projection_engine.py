"""Unit tests for the projection engine."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from punk_records.models.events import EventEnvelope, EventType
from punk_records.projections.engine import ProjectionEngine


def _make_event(**overrides) -> EventEnvelope:
    base = {
        "event_id": str(uuid4()),
        "schema_version": 1,
        "ts": "2026-02-07T22:00:00Z",
        "workspace_id": "ws-test",
        "satellite_id": "sat-test",
        "trace_id": str(uuid4()),
        "type": "task.created",
        "severity": "low",
        "confidence": 0.9,
        "payload": {},
    }
    base.update(overrides)
    return EventEnvelope(**base)


@pytest.fixture
def mock_event_store():
    store = MagicMock()
    store.count_references = AsyncMock(return_value=0)
    store.has_event_type_in_trace = AsyncMock(return_value=False)
    store.get_workspace_events = AsyncMock(return_value=[])
    return store


@pytest.fixture
def mock_memory_store():
    store = MagicMock()
    store.create_entry = AsyncMock(return_value=True)
    store.update_status = AsyncMock(return_value=True)
    store.get_entries = AsyncMock(return_value=[])
    store.delete_workspace_entries = AsyncMock(return_value=0)
    store.update_cursor = AsyncMock()
    store.get_cursor = AsyncMock(return_value=None)
    return store


@pytest.fixture
def mock_producer():
    producer = MagicMock()
    producer.send_event = AsyncMock()
    return producer


@pytest.fixture
def engine(mock_event_store, mock_memory_store, mock_producer):
    return ProjectionEngine(
        event_store=mock_event_store,
        memory_store=mock_memory_store,
        producer=mock_producer,
    )


class TestHandleCandidate:
    async def test_creates_memory_entry(
        self, engine, mock_memory_store
    ):
        event = _make_event(
            type="memory.candidate",
            confidence=0.8,
            payload={
                "bucket": "workspace",
                "key": "test.fact",
                "value": {"data": "hello"},
            },
        )
        await engine.process(event)

        mock_memory_store.create_entry.assert_called_once()
        entry = mock_memory_store.create_entry.call_args[0][0]
        assert entry.entry_id == event.event_id
        assert entry.workspace_id == "ws-test"
        assert entry.bucket.value == "workspace"
        assert entry.key == "test.fact"
        assert entry.status.value == "candidate"
        assert entry.confidence == 0.8
        assert entry.source_event_id == event.event_id

    async def test_ephemeral_sets_expires_at(
        self, engine, mock_memory_store
    ):
        event = _make_event(
            type="memory.candidate",
            payload={
                "bucket": "ephemeral",
                "key": "temp.data",
                "ttl_hours": 12,
            },
        )
        await engine.process(event)

        entry = mock_memory_store.create_entry.call_args[0][0]
        assert entry.bucket.value == "ephemeral"
        assert entry.expires_at is not None
        expected = event.ts + timedelta(hours=12)
        assert entry.expires_at == expected

    async def test_ephemeral_default_ttl(
        self, engine, mock_memory_store
    ):
        event = _make_event(
            type="memory.candidate",
            payload={
                "bucket": "ephemeral",
                "key": "temp.data",
            },
        )
        await engine.process(event)

        entry = mock_memory_store.create_entry.call_args[0][0]
        expected = event.ts + timedelta(hours=24)
        assert entry.expires_at == expected


class TestHandlePromoted:
    async def test_updates_entry_status(
        self, engine, mock_memory_store
    ):
        entry_id = uuid4()
        event = _make_event(
            type="memory.promoted",
            payload={"entry_id": str(entry_id)},
        )
        await engine.process(event)

        mock_memory_store.update_status.assert_called_once()
        args = mock_memory_store.update_status.call_args
        assert args[0][0] == entry_id
        assert args[0][1].value == "promoted"

    async def test_missing_entry_id_logs_warning(
        self, engine, mock_memory_store
    ):
        event = _make_event(
            type="memory.promoted",
            payload={},
        )
        await engine.process(event)

        mock_memory_store.update_status.assert_not_called()


class TestHandleRetracted:
    async def test_updates_entry_status(
        self, engine, mock_memory_store
    ):
        entry_id = uuid4()
        event = _make_event(
            type="memory.retracted",
            payload={"entry_id": str(entry_id)},
        )
        await engine.process(event)

        mock_memory_store.update_status.assert_called_once()
        args = mock_memory_store.update_status.call_args
        assert args[0][0] == entry_id
        assert args[0][1].value == "retracted"

    async def test_missing_entry_id_logs_warning(
        self, engine, mock_memory_store
    ):
        event = _make_event(
            type="memory.retracted",
            payload={},
        )
        await engine.process(event)

        mock_memory_store.update_status.assert_not_called()


class TestAutoPromotion:
    async def test_triggers_when_eligible(
        self, engine, mock_memory_store, mock_event_store,
        mock_producer,
    ):
        """An eligible candidate triggers a synthetic promotion event."""
        candidate_id = uuid4()
        now = datetime.now(timezone.utc)
        mock_memory_store.get_entries.return_value = [
            {
                "entry_id": candidate_id,
                "workspace_id": "ws-test",
                "bucket": "workspace",
                "key": "test.fact",
                "value": {},
                "status": "candidate",
                "confidence": 0.9,
                "source_event_id": uuid4(),
                "expires_at": None,
                "created_at": now,
                "updated_at": now,
            }
        ]
        # Make promotion evaluator say eligible
        mock_event_store.count_references.return_value = 3

        event = _make_event(type="task.created")
        await engine.process(event)

        mock_producer.send_event.assert_called_once()
        synthetic = mock_producer.send_event.call_args[0][0]
        assert synthetic.type == EventType.MEMORY_PROMOTED
        assert synthetic.payload["entry_id"] == str(candidate_id)
        assert synthetic.satellite_id == (
            "punk-records.projection-engine"
        )

    async def test_no_promotion_when_ineligible(
        self, engine, mock_memory_store, mock_event_store,
        mock_producer,
    ):
        """Low-confidence candidates are not auto-promoted."""
        now = datetime.now(timezone.utc)
        mock_memory_store.get_entries.return_value = [
            {
                "entry_id": uuid4(),
                "workspace_id": "ws-test",
                "bucket": "workspace",
                "key": "test.fact",
                "value": {},
                "status": "candidate",
                "confidence": 0.5,
                "source_event_id": uuid4(),
                "expires_at": None,
                "created_at": now,
                "updated_at": now,
            }
        ]
        event = _make_event(type="task.created")
        await engine.process(event)

        mock_producer.send_event.assert_not_called()


class TestCursorTracking:
    async def test_cursor_updated_after_process(
        self, engine, mock_memory_store
    ):
        event = _make_event(type="task.created")
        await engine.process(event)

        mock_memory_store.update_cursor.assert_called_once_with(
            event.event_id, event.ts
        )


class TestReplay:
    async def test_replay_deletes_and_rebuilds(
        self, engine, mock_memory_store, mock_event_store
    ):
        candidate_id = uuid4()
        promoted_id = uuid4()
        ts = datetime(2026, 2, 7, 22, 0, tzinfo=timezone.utc)
        mock_event_store.get_workspace_events.return_value = [
            {
                "event_id": candidate_id,
                "ts": ts,
                "workspace_id": "ws-test",
                "satellite_id": "sat-test",
                "trace_id": uuid4(),
                "type": "memory.candidate",
                "severity": "low",
                "confidence": 0.8,
                "payload_json": {
                    "bucket": "workspace",
                    "key": "test.fact",
                    "value": {"data": "replayed"},
                },
            },
            {
                "event_id": promoted_id,
                "ts": ts + timedelta(seconds=10),
                "workspace_id": "ws-test",
                "satellite_id": "sat-test",
                "trace_id": uuid4(),
                "type": "memory.promoted",
                "severity": "low",
                "confidence": 0.8,
                "payload_json": {
                    "entry_id": str(candidate_id),
                },
            },
        ]
        mock_memory_store.delete_workspace_entries.return_value = 5

        result = await engine.replay("ws-test")

        assert result["entries_deleted"] == 5
        assert result["events_replayed"] == 2
        assert result["entries_created"] == 1
        mock_memory_store.delete_workspace_entries.assert_called_once_with(
            "ws-test"
        )
        mock_memory_store.create_entry.assert_called_once()
        mock_memory_store.update_status.assert_called_once()

    async def test_replay_empty_workspace(
        self, engine, mock_memory_store, mock_event_store
    ):
        mock_event_store.get_workspace_events.return_value = []
        mock_memory_store.delete_workspace_entries.return_value = 0

        result = await engine.replay("ws-empty")

        assert result["entries_deleted"] == 0
        assert result["events_replayed"] == 0
        assert result["entries_created"] == 0


class TestNonMemoryEvents:
    async def test_non_memory_event_only_checks_promotion(
        self, engine, mock_memory_store
    ):
        """Non-memory events should still check auto-promotion."""
        event = _make_event(type="task.created")
        await engine.process(event)

        # Should not create/update entries directly
        mock_memory_store.create_entry.assert_not_called()
        mock_memory_store.update_status.assert_not_called()
        # But should check for promotion candidates
        mock_memory_store.get_entries.assert_called_once()
        # And update cursor
        mock_memory_store.update_cursor.assert_called_once()
