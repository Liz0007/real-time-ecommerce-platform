# app/consumer.py

import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer

from app.config import settings

logger = logging.getLogger(__name__)


async def run_consumer(stop_event: asyncio.Event) -> None:
    """Consume payment-processed and inventory-reserved events and simulate
    sending a customer notification for each. No downstream publish — this
    service is a terminal consumer in the event flow.
    """
    consumer = AIOKafkaConsumer(
        *settings.consume_topics,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        security_protocol=settings.kafka_security_protocol,
        group_id=settings.consumer_group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )

    await consumer.start()
    logger.info("notification-service consumer started, topics=%s", settings.consume_topics)

    try:
        while not stop_event.is_set():
            batches = await consumer.getmany(timeout_ms=1000, max_records=50)
            for tp, messages in batches.items():
                for msg in messages:
                    _handle_message(tp.topic, msg)
            if batches:
                await consumer.commit()
    finally:
        await consumer.stop()
        logger.info("notification-service consumer stopped")


def _handle_message(topic: str, msg) -> None:
    try:
        event = json.loads(msg.value)
    except json.JSONDecodeError:
        logger.exception("skipping unparseable message at offset=%s", msg.offset)
        return

    order_id = event.get("order_id")
    status = event.get("status")

    # Simulated notification send — replace with a real email/SMS/push provider.
    logger.info(
        "NOTIFY customer: order_id=%s topic=%s status=%s",
        order_id, topic, status,
    )