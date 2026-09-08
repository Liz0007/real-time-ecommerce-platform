# app/consumer.py

import asyncio
import json
import logging
import random
from datetime import datetime, timezone

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from app.config import settings

logger = logging.getLogger(__name__)


async def run_consumer(stop_event: asyncio.Event) -> None:
    """Consume order-created events, simulate payment processing, publish the result.

    NOTE: this is a simple at-least-once consumer with manual offset commit
    AFTER a successful publish — if the process crashes between publish and
    commit, an event may be reprocessed on restart. That's a deliberate
    trade-off (favoring "no lost events" over "no duplicate events") and
    downstream consumers should treat payment-processed handling as
    idempotent if that matters for their use case.
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

    # Simulated stock check — replace with a real inventory DB lookup/reservation.
    await asyncio.sleep(0.1)
    in_stock = random.random() >= settings.simulated_failure_rate

    result = {
        "order_id": order_id,
        "status": "payment_succeeded" if in_stock else "payment_failed",
        "amount": order.get("total_amount"),
        "reserved_at": datetime.now(timezone.utc).isoformat(),
    }

    await producer.send_and_wait(
        settings.publish_topic,
        key=str(order_id).encode() if order_id else None,
        value=json.dumps(result).encode(),
    )
    logger.info("published %s for order_id=%s", result["status"], order_id)