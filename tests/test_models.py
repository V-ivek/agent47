from datetime import datetime, timezone
from uuid import uuid4

import pytest

from punk_records.models.events import EventEnvelope, EventType, Severity


def _valid_event(**overrides) -> dict:
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
        "payload": {"title": "Hello"},
    }
    base.update(overrides)
    return base


class TestEventEnvelopeParsing:
    def test_valid_event_parses(self):
        evt = EventEnvelope(**_valid_event())
        assert evt.type == EventType.TASK_CREATED
        assert evt.severity == Severity.LOW
        assert evt.confidence == 0.9

    def test_naive_datetime_normalized_to_utc(self):
        evt = EventEnvelope(**_valid_event(ts="2026-02-07T22:00:00"))
        assert evt.ts.tzinfo == timezone.utc

    def test_aware_datetime_converted_to_utc(self):
        evt = EventEnvelope(**_valid_event(ts="2026-02-07T22:00:00+05:00"))
        assert evt.ts.tzinfo == timezone.utc
        assert evt.ts.hour == 17

    def test_datetime_object_accepted(self):
        dt = datetime(2026, 2, 7, 22, 0, 0)
        evt = EventEnvelope(**_valid_event(ts=dt))
        assert evt.ts.tzinfo == timezone.utc

    def test_empty_payload_default(self):
        data = _valid_event()
        del data["payload"]
        evt = EventEnvelope(**data)
        assert evt.payload == {}


class TestEventEnvelopeValidation:
    def test_invalid_severity_rejected(self):
        with pytest.raises(ValueError):
            EventEnvelope(**_valid_event(severity="critical"))

    def test_invalid_type_rejected(self):
        with pytest.raises(ValueError):
            EventEnvelope(**_valid_event(type="invalid.type"))

    def test_confidence_too_high_rejected(self):
        with pytest.raises(ValueError):
            EventEnvelope(**_valid_event(confidence=1.5))

    def test_confidence_too_low_rejected(self):
        with pytest.raises(ValueError):
            EventEnvelope(**_valid_event(confidence=-0.1))

    def test_schema_version_must_be_1(self):
        with pytest.raises(ValueError):
            EventEnvelope(**_valid_event(schema_version=2))

    def test_schema_version_zero_rejected(self):
        with pytest.raises(ValueError):
            EventEnvelope(**_valid_event(schema_version=0))

    def test_empty_workspace_id_rejected(self):
        with pytest.raises(ValueError):
            EventEnvelope(**_valid_event(workspace_id=""))

    def test_empty_satellite_id_rejected(self):
        with pytest.raises(ValueError):
            EventEnvelope(**_valid_event(satellite_id=""))


class TestKafkaSerialization:
    def test_round_trip(self):
        original = EventEnvelope(**_valid_event())
        data = original.to_kafka_value()
        restored = EventEnvelope.from_kafka_value(data)
        assert restored.event_id == original.event_id
        assert restored.type == original.type
        assert restored.payload == original.payload

    def test_kafka_key_is_workspace_id(self):
        evt = EventEnvelope(**_valid_event(workspace_id="ws-42"))
        assert evt.kafka_key() == b"ws-42"

    def test_to_kafka_value_returns_bytes(self):
        evt = EventEnvelope(**_valid_event())
        assert isinstance(evt.to_kafka_value(), bytes)

    def test_from_kafka_value_invalid_json_raises(self):
        with pytest.raises(Exception):
            EventEnvelope.from_kafka_value(b"not json")
