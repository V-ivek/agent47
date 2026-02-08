"""Unit tests for the store layer using mocks (no real Postgres needed)."""

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from punk_records.models.events import EventEnvelope
from punk_records.store.event_store import EventStore


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
        "payload": {"title": "test"},
    }
    base.update(overrides)
    return EventEnvelope(**base)


class TestEventStore:
    @pytest.fixture
    def mock_pool(self):
        pool = MagicMock()
        conn = AsyncMock()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__ = AsyncMock(return_value=False)
        pool.acquire.return_value = ctx
        return pool, conn

    async def test_persist_returns_true_on_insert(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="INSERT 0 1")
        store = EventStore(pool)
        event = _make_event()
        result = await store.persist(event)
        assert result is True
        conn.execute.assert_called_once()

    async def test_persist_returns_false_on_duplicate(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="INSERT 0 0")
        store = EventStore(pool)
        event = _make_event()
        result = await store.persist(event)
        assert result is False

    async def test_persist_passes_correct_args(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="INSERT 0 1")
        store = EventStore(pool)
        event = _make_event(workspace_id="ws-42")
        await store.persist(event)
        args = conn.execute.call_args[0]
        # args[0] is SQL, args[1] is event_id, args[3] is workspace_id
        assert args[3] == "ws-42"
        # payload is JSON string at args[9]
        assert json.loads(args[9]) == event.payload
