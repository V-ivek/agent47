from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from punk_records.models.memory import MemoryBucket, MemoryEntry, MemoryStatus


def _base_entry(**overrides):
    defaults = {
        "entry_id": uuid4(),
        "workspace_id": "ws-test",
        "bucket": "workspace",
        "key": "test.key",
        "value": {"data": "hello"},
        "status": "candidate",
        "confidence": 0.8,
        "source_event_id": uuid4(),
    }
    defaults.update(overrides)
    return defaults


class TestMemoryBucket:
    def test_valid_buckets(self):
        assert MemoryBucket("global") == MemoryBucket.GLOBAL
        assert MemoryBucket("workspace") == MemoryBucket.WORKSPACE
        assert MemoryBucket("ephemeral") == MemoryBucket.EPHEMERAL

    def test_invalid_bucket(self):
        with pytest.raises(ValueError):
            MemoryBucket("invalid")


class TestMemoryStatus:
    def test_valid_statuses(self):
        assert MemoryStatus("candidate") == MemoryStatus.CANDIDATE
        assert MemoryStatus("promoted") == MemoryStatus.PROMOTED
        assert MemoryStatus("retracted") == MemoryStatus.RETRACTED

    def test_invalid_status(self):
        with pytest.raises(ValueError):
            MemoryStatus("deleted")


class TestMemoryEntry:
    def test_valid_candidate(self):
        entry = MemoryEntry(**_base_entry())
        assert entry.status == MemoryStatus.CANDIDATE
        assert entry.bucket == MemoryBucket.WORKSPACE
        assert entry.confidence == 0.8
        assert entry.promoted_at is None
        assert entry.retracted_at is None
        assert entry.expires_at is None

    def test_valid_promoted(self):
        now = datetime.now(timezone.utc)
        entry = MemoryEntry(**_base_entry(
            status="promoted",
            promoted_at=now,
        ))
        assert entry.status == MemoryStatus.PROMOTED
        assert entry.promoted_at == now

    def test_valid_retracted(self):
        now = datetime.now(timezone.utc)
        entry = MemoryEntry(**_base_entry(
            status="retracted",
            retracted_at=now,
        ))
        assert entry.status == MemoryStatus.RETRACTED
        assert entry.retracted_at == now

    def test_valid_ephemeral(self):
        expires = datetime.now(timezone.utc) + timedelta(hours=24)
        entry = MemoryEntry(**_base_entry(
            bucket="ephemeral",
            expires_at=expires,
        ))
        assert entry.bucket == MemoryBucket.EPHEMERAL
        assert entry.expires_at == expires

    def test_ephemeral_requires_expires_at(self):
        with pytest.raises(ValueError, match="ephemeral entries must have expires_at"):
            MemoryEntry(**_base_entry(bucket="ephemeral"))

    def test_non_ephemeral_rejects_expires_at(self):
        expires = datetime.now(timezone.utc) + timedelta(hours=24)
        with pytest.raises(ValueError, match="only ephemeral entries may have expires_at"):
            MemoryEntry(**_base_entry(bucket="workspace", expires_at=expires))

    def test_global_bucket_rejects_expires_at(self):
        expires = datetime.now(timezone.utc) + timedelta(hours=24)
        with pytest.raises(ValueError, match="only ephemeral entries may have expires_at"):
            MemoryEntry(**_base_entry(bucket="global", expires_at=expires))

    def test_promoted_requires_promoted_at(self):
        with pytest.raises(ValueError, match="promoted entries must have promoted_at"):
            MemoryEntry(**_base_entry(status="promoted"))

    def test_retracted_requires_retracted_at(self):
        with pytest.raises(ValueError, match="retracted entries must have retracted_at"):
            MemoryEntry(**_base_entry(status="retracted"))

    def test_invalid_confidence_low(self):
        with pytest.raises(ValueError):
            MemoryEntry(**_base_entry(confidence=-0.1))

    def test_invalid_confidence_high(self):
        with pytest.raises(ValueError):
            MemoryEntry(**_base_entry(confidence=1.1))

    def test_empty_workspace_id(self):
        with pytest.raises(ValueError):
            MemoryEntry(**_base_entry(workspace_id=""))

    def test_empty_key(self):
        with pytest.raises(ValueError):
            MemoryEntry(**_base_entry(key=""))

    def test_invalid_bucket(self):
        with pytest.raises(ValueError):
            MemoryEntry(**_base_entry(bucket="invalid"))

    def test_invalid_status(self):
        with pytest.raises(ValueError):
            MemoryEntry(**_base_entry(status="deleted"))

    def test_timestamp_normalization_naive(self):
        naive_dt = datetime(2026, 1, 1, 12, 0, 0)
        entry = MemoryEntry(**_base_entry(
            status="promoted",
            promoted_at=naive_dt,
        ))
        assert entry.promoted_at.tzinfo is not None
        assert entry.promoted_at == naive_dt.replace(tzinfo=timezone.utc)

    def test_timestamp_normalization_string(self):
        entry = MemoryEntry(**_base_entry(
            status="promoted",
            promoted_at="2026-01-15T10:30:00Z",
        ))
        assert entry.promoted_at == datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)

    def test_default_value_empty_dict(self):
        data = _base_entry()
        del data["value"]
        entry = MemoryEntry(**data)
        assert entry.value == {}

    def test_created_at_updated_at_defaults(self):
        entry = MemoryEntry(**_base_entry())
        assert entry.created_at is not None
        assert entry.updated_at is not None
        assert entry.created_at.tzinfo is not None
