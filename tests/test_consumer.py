"""Unit tests for the Kafka consumer using mocks."""

import asyncio
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


def _make_kafka_msg(value: bytes, topic: str = "test", partition: int = 0, offset: int = 0):
    msg = MagicMock()
    msg.value = value
    msg.topic = topic
    msg.partition = partition
    msg.offset = offset
    return msg


def _mock_kafka_consumer(messages):
    """Create a mock AIOKafkaConsumer that yields the given messages."""
    mock_kafka = AsyncMock()
    mock_kafka.commit = AsyncMock()
    mock_kafka.stop = AsyncMock()
    mock_kafka.start = AsyncMock()

    async def _aiter(self):
        for m in messages:
            yield m

    mock_kafka.__aiter__ = _aiter
    return mock_kafka


class TestEventConsumer:
    @pytest.fixture
    def mock_store(self):
        store = MagicMock()
        store.persist = AsyncMock(return_value=True)
        return store

    def _make_consumer(self, mock_store, messages):
        mock_kafka = _mock_kafka_consumer(messages)
        with patch("punk_records.kafka.consumer.AIOKafkaConsumer", return_value=mock_kafka):
            from punk_records.kafka.consumer import EventConsumer

            consumer = EventConsumer(
                brokers="localhost:9092",
                topic="test",
                group_id="test-group",
                event_store=mock_store,
            )
        return consumer, mock_kafka

    async def test_valid_message_persisted_and_committed(self, mock_store):
        event = _make_event()
        msg = _make_kafka_msg(event.to_kafka_value())
        consumer, mock_kafka = self._make_consumer(mock_store, [msg])

        await consumer.start()
        await asyncio.sleep(0.1)
        await consumer.stop()

        mock_store.persist.assert_called_once()
        persisted_event = mock_store.persist.call_args[0][0]
        assert persisted_event.event_id == event.event_id
        mock_kafka.commit.assert_called()

    async def test_malformed_message_skipped_and_committed(self, mock_store):
        msg = _make_kafka_msg(b"not valid json")
        consumer, mock_kafka = self._make_consumer(mock_store, [msg])

        await consumer.start()
        await asyncio.sleep(0.1)
        await consumer.stop()

        mock_store.persist.assert_not_called()
        mock_kafka.commit.assert_called()

    async def test_persist_failure_does_not_commit(self, mock_store):
        event = _make_event()
        msg = _make_kafka_msg(event.to_kafka_value())
        mock_store.persist = AsyncMock(side_effect=Exception("db down"))
        consumer, mock_kafka = self._make_consumer(mock_store, [msg])

        await consumer.start()
        await asyncio.sleep(0.1)
        await consumer.stop()

        mock_store.persist.assert_called_once()
        mock_kafka.commit.assert_not_called()
