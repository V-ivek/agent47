"""Unit tests for the store layer using mocks (no real Postgres needed)."""

import json
from datetime import datetime, timezone
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


class TestEventStoreQueries:
    @pytest.fixture
    def mock_pool(self):
        pool = MagicMock()
        conn = AsyncMock()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__ = AsyncMock(return_value=False)
        pool.acquire.return_value = ctx
        return pool, conn

    async def test_query_events_basic(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        store = EventStore(pool)

        result = await store.query_events("ws-1")

        assert result == []
        sql, *params = conn.fetch.call_args[0]
        assert "WHERE workspace_id = $1" in sql
        assert "ORDER BY ts ASC" in sql
        assert "LIMIT $2 OFFSET $3" in sql
        assert params == ["ws-1", 50, 0]

    async def test_query_events_with_filters(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        store = EventStore(pool)
        after = datetime(2026, 1, 1, tzinfo=timezone.utc)
        before = datetime(2026, 2, 1, tzinfo=timezone.utc)

        await store.query_events(
            "ws-1",
            type="task.created",
            after=after,
            before=before,
            limit=10,
            offset=5,
        )

        sql, *params = conn.fetch.call_args[0]
        assert "AND type = $2" in sql
        assert "AND ts > $3" in sql
        assert "AND ts < $4" in sql
        assert "LIMIT $5 OFFSET $6" in sql
        assert params == ["ws-1", "task.created", after, before, 10, 5]

    async def test_query_events_caps_limit(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        store = EventStore(pool)

        await store.query_events("ws-1", limit=500)

        sql, *params = conn.fetch.call_args[0]
        # limit should be capped at 200
        assert params == ["ws-1", 200, 0]

    async def test_count_events(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchval = AsyncMock(return_value=42)
        store = EventStore(pool)

        result = await store.count_events("ws-1", type="risk.detected")

        assert result == 42
        sql, *params = conn.fetchval.call_args[0]
        assert "SELECT COUNT(*)" in sql
        assert "WHERE workspace_id = $1" in sql
        assert "AND type = $2" in sql
        assert params == ["ws-1", "risk.detected"]

    async def test_get_workspace_events_basic(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        store = EventStore(pool)

        result = await store.get_workspace_events("ws-1")

        assert result == []
        sql, *params = conn.fetch.call_args[0]
        assert "WHERE workspace_id = $1" in sql
        assert "ORDER BY ts ASC" in sql
        assert params == ["ws-1"]

    async def test_get_workspace_events_with_types(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        store = EventStore(pool)
        types = ["task.created", "task.updated"]

        await store.get_workspace_events("ws-1", types=types)

        sql, *params = conn.fetch.call_args[0]
        assert "AND type = ANY($2)" in sql
        assert params == ["ws-1", types]

    async def test_count_references(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchval = AsyncMock(return_value=3)
        store = EventStore(pool)
        tid = uuid4()
        since = datetime(2026, 1, 15, tzinfo=timezone.utc)

        result = await store.count_references("ws-1", tid, since)

        assert result == 3
        sql, *params = conn.fetchval.call_args[0]
        assert "WHERE workspace_id = $1" in sql
        assert "AND trace_id = $2" in sql
        assert "AND ts >= $3" in sql
        assert params == ["ws-1", tid, since]

    async def test_has_event_type_in_trace(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchval = AsyncMock(return_value=True)
        store = EventStore(pool)
        tid = uuid4()

        result = await store.has_event_type_in_trace(
            "ws-1", tid, "risk.detected"
        )

        assert result is True
        sql, *params = conn.fetchval.call_args[0]
        assert "SELECT EXISTS(" in sql
        assert "WHERE workspace_id = $1" in sql
        assert "AND trace_id = $2" in sql
        assert "AND type = $3" in sql
        assert params == ["ws-1", tid, "risk.detected"]
