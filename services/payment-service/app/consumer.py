# app/consumer.py

import asyncio
import json
import logging
import random
from datetime import datetime, timezone

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import text

from app.config import settings
from app.db import async_session_factory

logger = logging.getLogger(__name__)


async def run_consumer(stop_event: asyncio.Event) -> None:
    """Consume order-created events, simulate payment processing, persist the
    result to Postgres and publish the result.

    Persisting before/alongside publishing is what makes GET /payments/{id}
    possible — previously this service was purely reactive with no memory
    of what it had done. ON CONFLICT in the insert makes this safe against
    at-least-once redelivery (a message reprocessed after a restart just
    overwrites the same row instead of erroring or duplicating).
    """
    consumer = AIOKafkaConsumer(
        settings.consume_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        security_protocol=settings.kafka_security_protocol,
        group_id=settings.consumer_group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        security_protocol=settings.kafka_security_protocol,
    )

    await consumer.start()
    await producer.start()
    logger.info("payment-service consumer started, topic=%s", settings.consume_topic)

    try:
        while not stop_event.is_set():
            batches = await consumer.getmany(timeout_ms=1000, max_records=50)
            for _tp, messages in batches.items():
                for msg in messages:
                    await _handle_message(msg, producer)
            if batches:
                await consumer.commit()
    finally:
        await consumer.stop()
        await producer.stop()
        logger.info("payment-service consumer stopped")


async def _handle_message(msg, producer: AIOKafkaProducer) -> None:
    try:
        order = json.loads(msg.value)
    except json.JSONDecodeError:
        logger.exception("skipping unparseable message at offset=%s", msg.offset)
        return

    order_id = order.get("id")
    logger.info("processing payment for order_id=%s", order_id)

    # Simulated payment processing — replace with a real provider call.
    await asyncio.sleep(0.1)
    success = random.random() >= settings.simulated_failure_rate

    processed_at = datetime.now(timezone.utc)
    result = {
        "order_id": order_id,
        "status": "payment_succeeded" if success else "payment_failed",
        "amount": order.get("total_amount"),
        "processed_at": processed_at.isoformat(),
    }

    # Persist first — if this fails, we haven't told the rest of the system
    # about a payment result we can't ourselves recall.
    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(
                text("""
                    INSERT INTO payments (order_id, status, amount, processed_at)
                    VALUES (:order_id, :status, :amount, :processed_at)
                    ON CONFLICT (order_id) DO UPDATE
                    SET status = EXCLUDED.status,
                        amount = EXCLUDED.amount,
                        processed_at = EXCLUDED.processed_at
                """),
                {
                    "order_id": order_id,
                    "status": result["status"],
                    "amount": result["amount"],
                    "processed_at": processed_at,
                },
            )

    await producer.send_and_wait(
        settings.publish_topic,
        key=str(order_id).encode() if order_id else None,
        value=json.dumps(result).encode(),
    )
    logger.info("published %s for order_id=%s", result["status"], order_id)