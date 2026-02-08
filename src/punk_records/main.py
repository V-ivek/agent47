import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from punk_records.api.events import router as events_router
from punk_records.api.health import router as health_router
from punk_records.config import Settings
from punk_records.kafka.consumer import EventConsumer
from punk_records.kafka.producer import EventProducer
from punk_records.store.database import Database
from punk_records.store.event_store import EventStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Database
    db = Database(settings.database_url)
    await db.connect()
    await db.run_migrations()
    app.state.database = db

    # Kafka producer
    producer = EventProducer(settings.kafka_brokers, settings.kafka_topic)
    await producer.start()
    app.state.producer = producer

    # Event store + Kafka consumer
    event_store = EventStore(db.pool)
    consumer = EventConsumer(
        brokers=settings.kafka_brokers,
        topic=settings.kafka_topic,
        group_id=settings.kafka_consumer_group,
        event_store=event_store,
    )
    await consumer.start()
    app.state.consumer = consumer

    logger.info("Punk Records started")
    yield

    # Shutdown in reverse order
    await consumer.stop()
    await producer.stop()
    await db.disconnect()
    logger.info("Punk Records stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()

    app = FastAPI(title="Punk Records", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    app.include_router(events_router)
    app.include_router(health_router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.errors()},
        )

    return app


app = create_app()
