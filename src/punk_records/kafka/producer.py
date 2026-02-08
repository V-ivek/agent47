import logging

from aiokafka import AIOKafkaProducer

from punk_records.models.events import EventEnvelope

logger = logging.getLogger(__name__)


class EventProducer:
    def __init__(self, brokers: str, topic: str):
        self._topic = topic
        self._producer = AIOKafkaProducer(
            bootstrap_servers=brokers,
            acks="all",
        )

    async def start(self) -> None:
        await self._producer.start()
        logger.info("Kafka producer started")

    async def stop(self) -> None:
        await self._producer.stop()
        logger.info("Kafka producer stopped")

    async def send_event(self, event: EventEnvelope) -> None:
        await self._producer.send_and_wait(
            self._topic,
            key=event.kafka_key(),
            value=event.to_kafka_value(),
        )
        logger.debug("Produced event %s to %s", event.event_id, self._topic)

    async def check_health(self) -> bool:
        try:
            partitions = await self._producer.partitions_for(self._topic)
            return partitions is not None and len(partitions) > 0
        except Exception:
            logger.exception("Kafka producer health check failed")
            return False
