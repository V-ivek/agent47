"""Unit tests for the memory store layer using mocks (no real Postgres needed)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from punk_records.models.memory import MemoryBucket, MemoryStatus
from punk_records.store.memory_store import MemoryStore


def _make_entry_kwargs(**overrides):
    """Build kwargs for a MemoryEntry with sensible defaults."""
    now = datetime.now(timezone.utc)
    base = {
        "entry_id": uuid4(),
        "workspace_id": "ws-test",
        "bucket": "workspace",
        "key": "test-key",
        "value": {"fact": "unit test"},
        "status": "promoted",
        "confidence": 0.85,
        "source_event_id": uuid4(),
        "promoted_at": now,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return base


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = ctx
    return pool, conn


class TestCreateEntry:
    async def test_returns_true_on_insert(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="INSERT 0 1")
        store = MemoryStore(pool)

        from punk_records.models.memory import MemoryEntry
        entry = MemoryEntry(**_make_entry_kwargs())
        result = await store.create_entry(entry)

        assert result is True
        conn.execute.assert_called_once()

    async def test_returns_false_on_duplicate(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="INSERT 0 0")
        store = MemoryStore(pool)

        from punk_records.models.memory import MemoryEntry
        entry = MemoryEntry(**_make_entry_kwargs())
        result = await store.create_entry(entry)

        assert result is False

    async def test_passes_correct_source_event_id(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="INSERT 0 1")
        store = MemoryStore(pool)

        source_id = uuid4()
        from punk_records.models.memory import MemoryEntry
        entry = MemoryEntry(**_make_entry_kwargs(source_event_id=source_id))
        await store.create_entry(entry)

        args = conn.execute.call_args[0]
        # args[8] is source_event_id (0=SQL, 1=entry_id, ..., 8=source_event_id)
        assert args[8] == source_id


class TestUpdateStatus:
    async def test_promoted_returns_true(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="UPDATE 1")
        store = MemoryStore(pool)

        entry_id = uuid4()
        ts = datetime.now(timezone.utc)
        result = await store.update_status(
            entry_id, MemoryStatus.PROMOTED, ts
        )

        assert result is True
        args = conn.execute.call_args[0]
        assert "promoted_at" in args[0]
        assert args[1] == "promoted"
        assert args[2] == ts
        assert args[3] == entry_id

    async def test_retracted_returns_true(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="UPDATE 1")
        store = MemoryStore(pool)

        entry_id = uuid4()
        ts = datetime.now(timezone.utc)
        result = await store.update_status(
            entry_id, MemoryStatus.RETRACTED, ts
        )

        assert result is True
        args = conn.execute.call_args[0]
        assert "retracted_at" in args[0]

    async def test_returns_false_when_not_found(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="UPDATE 0")
        store = MemoryStore(pool)

        result = await store.update_status(
            uuid4(), MemoryStatus.PROMOTED, datetime.now(timezone.utc)
        )

        assert result is False


class TestGetEntries:
    async def test_basic_query_with_defaults(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        store = MemoryStore(pool)

        result = await store.get_entries("ws-test")

        assert result == []
        args = conn.fetch.call_args[0]
        sql = args[0]
        assert "workspace_id = $1" in sql
        assert "status = $2" in sql
        # Default status is promoted
        assert args[1] == "ws-test"
        assert args[2] == "promoted"
        # Expired entries excluded by default
        assert "expires_at" in sql

    async def test_with_bucket_filter(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        store = MemoryStore(pool)

        await store.get_entries("ws-test", bucket=MemoryBucket.EPHEMERAL)

        args = conn.fetch.call_args[0]
        sql = args[0]
        assert "bucket = $3" in sql
        assert args[3] == "ephemeral"

    async def test_with_explicit_status(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        store = MemoryStore(pool)

        await store.get_entries("ws-test", status=MemoryStatus.CANDIDATE)

        args = conn.fetch.call_args[0]
        assert args[2] == "candidate"

    async def test_include_expired(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        store = MemoryStore(pool)

        await store.get_entries("ws-test", include_expired=True)

        args = conn.fetch.call_args[0]
        sql = args[0]
        assert "expires_at" not in sql

    async def test_returns_list_of_dicts(self, mock_pool):
        pool, conn = mock_pool
        # asyncpg Records act like dicts — use MagicMock with dict()
        row = MagicMock()
        row.__iter__ = MagicMock(
            return_value=iter([("entry_id", uuid4()), ("key", "test")])
        )
        row.keys = MagicMock(return_value=["entry_id", "key"])
        row.__getitem__ = MagicMock(side_effect=lambda k: {
            "entry_id": uuid4(), "key": "test"
        }[k])
        # Make dict(row) work by making row iterable as key-value pairs
        mock_dict = {"entry_id": uuid4(), "key": "test"}

        class FakeRecord:
            def keys(self):
                return mock_dict.keys()

            def __getitem__(self, key):
                return mock_dict[key]

            def __iter__(self):
                return iter(mock_dict)

            def __len__(self):
                return len(mock_dict)

        conn.fetch = AsyncMock(return_value=[FakeRecord()])
        store = MemoryStore(pool)

        result = await store.get_entries("ws-test")

        assert len(result) == 1
        assert isinstance(result[0], dict)


class TestDeleteWorkspaceEntries:
    async def test_returns_count(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="DELETE 5")
        store = MemoryStore(pool)

        count = await store.delete_workspace_entries("ws-test")

        assert count == 5
        args = conn.execute.call_args[0]
        assert args[1] == "ws-test"

    async def test_returns_zero_when_none(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="DELETE 0")
        store = MemoryStore(pool)

        count = await store.delete_workspace_entries("ws-empty")

        assert count == 0


class TestGetCursor:
    async def test_returns_tuple_when_exists(self, mock_pool):
        pool, conn = mock_pool
        eid = uuid4()
        ts = datetime.now(timezone.utc)
        row = {"last_event_id": eid, "last_event_ts": ts}
        conn.fetchrow = AsyncMock(return_value=row)
        store = MemoryStore(pool)

        result = await store.get_cursor()

        assert result == (eid, ts)

    async def test_returns_none_when_empty(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value=None)
        store = MemoryStore(pool)

        result = await store.get_cursor()

        assert result is None


class TestUpdateCursor:
    async def test_calls_upsert(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="INSERT 0 1")
        store = MemoryStore(pool)

        eid = uuid4()
        ts = datetime.now(timezone.utc)
        await store.update_cursor(eid, ts)

        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        sql = args[0]
        assert "projection_cursor" in sql
        assert "ON CONFLICT" in sql
        assert args[1] == eid
        assert args[2] == ts
