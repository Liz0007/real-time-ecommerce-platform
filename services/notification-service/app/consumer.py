# app/consumer.py

import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer

from app.config import settings
from app.kafka_auth import kafka_client_kwargs 

logger = logging.getLogger(__name__)

async def run_consumer(stop_event: asyncio.Event) -> None:
    """Consume payment-processed and inventory-reserved events and simulate
    sending a customer notification for each. No downstream publish — this
    service is a terminal consumer in the event flow.
    """
    consumer = AIOKafkaConsumer(
        *settings.consume_topics,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        # security_protocol=settings.kafka_security_protocol,
        group_id=settings.consumer_group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        **kafka_client_kwargs(),
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
    payment_status = event.get("payment_status")
    inventory_status = event.get("inventory_status")
    
    if status == "cancelled":
        reasons = []
        if payment_status == "failed":
            reasons.append("payment failed")
        if inventory_status == "unavailable":
            reasons.append("inventory unavailable")
        reason = " and ".join(reasons) if reasons else "unknown"
        logger.info("NOTIFY customer: order_id=%s CANCELLED (%s)", order_id, reason)
    else:
        logger.info("NOTIFY customer: order_id=%s CONFIRMED", order_id)