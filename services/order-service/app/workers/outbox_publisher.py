import asyncio, json, logging
from datetime import datetime, timezone

from aiokafka import AIOKafkaProducer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

TOPIC_MAP = {
    "order.created": "order-created",
}

async def run_outbox_publisher(
    session_factory: async_sessionmaker[AsyncSession],
    producer: AIOKafkaProducer,
    stop_event: asyncio.Event
) -> None:
    """Background loop: poll unpublished outbox rows, publish to Kafka, mark sent."""
    
    logger.info("outbox publisher started")
    
    while not stop_event.is_set():
        try:
            await _publish_batch(session_factory, producer)
        except Exception:
            logger.exception("outbox publisher batch failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.outbox_poll_interval_seconds)
        except asyncio.TimeoutError:
            pass # normal — just means it's time to poll again
    
    logger.info("outbox publisher stopped")   

async def _publish_batch(
    session_factory: async_sessionmaker[AsyncSession],
    producer: AIOKafkaProducer
) -> None:
    async with session_factory() as session:
        async with session.begin():
            # FOR UPDATE SKIP LOCKED: safe for multiple worker instances later —
            # each instance skips rows another one already has locked.
            rows = (
                await session.execute(
                    text("""
                        SELECT id, event_type, payload, attempts
                        FROM outbox
                        WHERE published_at IS NULL AND attempts < :max_attempts
                        ORDER BY created_at
                        LIMIT :batch_size
                        FOR UPDATE SKIP LOCKED 
                        """),
                    {
                        "max_attempts": settings.outbox_max_attempts,
                        "batch_size": settings.outbox_batch_size,
                    },
                )
            ).mappings().all()
            
            for row in rows:
                topic = TOPIC_MAP.get(row["event_type"])
                if topic is None:
                    logger.warning("no topic mapped for event_type=%s", row["event_type"])
                    continue
                    
                try:
                    await producer.send_and_wait(
                        topic,
                        key=str(row["id"]).encode(),
                        value=json.dumps(row["payload"]).encode()
                    )
                    await session.execute(
                        text("UPDATE outbox SET published_at = :now WHERE id = :id"),
                        {"now": datetime.now(timezone.utc),
                         "id": row["id"]
                         }
                    )
                    logger.info("published outbox row id=%s topic=%s", row["id"], topic)
                except Exception as exc:
                    new_attemps = row["attempts"] + 1
                    await session.execute(
                        text("""
                            UPDATE outbox
                            SET attempts = attempts + 1, last_error = :error
                            WHERE id = :id
                        """),
                        {"error": str(exc), "id": row["id"]},
                    )
                    if new_attemps >= settings.outbox_max_attempts:
                        logger.error(
                            "outbox row id=%s exceeded max_attempts=%s, giving up. last_error=%s",
                            row["id"], settings.outbox_max_attempts, exc,
                        )
                    logger.exception("failed to publish outbox row id=%s", row["id"])
