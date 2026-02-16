import asyncio
import logging

from aiokafka import AIOKafkaConsumer

from punk_records.models.events import EventEnvelope
from punk_records.observability.metrics import observe_consumed_event
from punk_records.store.event_store import EventStore

logger = logging.getLogger(__name__)


class EventConsumer:
    def __init__(
        self,
        brokers: str,
        topic: str,
        group_id: str,
        event_store: EventStore,
        projection_engine=None,
    ):
        self._topic = topic
        self._event_store = event_store
        self._projection_engine = projection_engine
        self._consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=brokers,
            group_id=group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        await self._consumer.start()
        self._task = asyncio.create_task(self._consume_loop())
        logger.info("Kafka consumer started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._consumer.stop()
        logger.info("Kafka consumer stopped")

    async def _consume_loop(self) -> None:
        try:
            async for msg in self._consumer:
                try:
                    event = EventEnvelope.from_kafka_value(msg.value)
                except Exception:
                    logger.exception(
                        "Malformed message at %s-%d offset %d, skipping",
                        msg.topic,
                        msg.partition,
                        msg.offset,
                    )
                    observe_consumed_event(topic=msg.topic, result="malformed")
                    await self._consumer.commit()
                    continue

                try:
                    inserted = await self._event_store.persist(event)
                except Exception:
                    logger.exception("Failed to persist event %s", event.event_id)
                    observe_consumed_event(topic=msg.topic, result="persist_error")
                    continue

                if inserted:
                    logger.info("Persisted event %s (type=%s)", event.event_id, event.type)
                    observe_consumed_event(topic=msg.topic, result="persisted")
                else:
                    logger.debug("Duplicate event %s observed", event.event_id)
                    observe_consumed_event(topic=msg.topic, result="duplicate")

                if self._projection_engine:
                    try:
                        await self._projection_engine.process(event)
                        observe_consumed_event(topic=msg.topic, result="projected")
                    except Exception:
                        logger.exception("Failed to project event %s", event.event_id)
                        observe_consumed_event(topic=msg.topic, result="projection_error")
                        continue

                await self._consumer.commit()
        except asyncio.CancelledError:
            logger.info("Consumer loop cancelled, shutting down")
            raise
