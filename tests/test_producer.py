"""Unit tests for the Kafka producer wrapper using mocks."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from punk_records.models.events import EventEnvelope


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


class TestEventProducer:
    @pytest.fixture
    def producer(self):
        with patch("punk_records.kafka.producer.AIOKafkaProducer") as MockProducer:
            mock_instance = MagicMock()
            mock_instance.start = AsyncMock()
            mock_instance.stop = AsyncMock()
            mock_instance.send_and_wait = AsyncMock()
            mock_instance.partitions_for = MagicMock(return_value={0, 1})
            MockProducer.return_value = mock_instance

            from punk_records.kafka.producer import EventProducer

            p = EventProducer(brokers="localhost:9092", topic="test-topic")
            yield p

    async def test_send_event_uses_workspace_key(self, producer):
        event = _make_event(workspace_id="ws-42")
        await producer.send_event(event)
        producer._producer.send_and_wait.assert_called_once_with(
            "test-topic",
            key=b"ws-42",
            value=event.to_kafka_value(),
        )

    async def test_start_delegates_to_aiokafka(self, producer):
        await producer.start()
        producer._producer.start.assert_called_once()

    async def test_stop_delegates_to_aiokafka(self, producer):
        await producer.stop()
        producer._producer.stop.assert_called_once()

    async def test_check_health_returns_true_when_partitions_exist(self, producer):
        result = await producer.check_health()
        assert result is True

    async def test_check_health_returns_false_when_no_partitions(self, producer):
        producer._producer.partitions_for = MagicMock(return_value=set())
        result = await producer.check_health()
        assert result is False

    async def test_check_health_returns_false_on_exception(self, producer):
        producer._producer.partitions_for = MagicMock(side_effect=Exception("boom"))
        result = await producer.check_health()
        assert result is False
