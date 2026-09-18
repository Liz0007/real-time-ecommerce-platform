# app/workers/order_status_consumer.py

import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import text

from app.config import settings
from app.db import async_session_factory

logger = logging.getLogger(__name__)

# Maps each topic's raw event status onto the value stored in
# order_fulfillment_state's corresponding column.
STATUS_MAP = {
    "payment-processed": {
        "payment_succeeded": "succeeded",
        "payment_failed": "failed",
    },
    "inventory-reserved": {
        "inventory_reserved": "reserved",
        "inventory_unavailable": "unavailable",
    },
}

# Which order_fulfillment_state column each topic writes into.
COLUMN_FOR_TOPIC = {
    "payment-processed": "payment_status",
    "inventory-reserved": "inventory_status",
}

# Topic to publish to when the order reaches each terminal status.
OUTPUT_TOPIC_FOR_STATUS = {
    "confirmed": "order-confirmed",
    "cancelled": "order-cancelled",
}

# Recomputes orders.status from order_fulfillment_state's current values —
# run in the same transaction as the state upsert below, so orders.status
# is never out of sync with the state it was derived from.
SYNC_ORDER_STATUS_SQL = """
    UPDATE orders o
    SET status = CASE
        WHEN f.payment_status = 'failed' OR f.inventory_status = 'unavailable' THEN 'cancelled'
        WHEN f.payment_status = 'succeeded' AND f.inventory_status = 'reserved' THEN 'confirmed'
        ELSE o.status
    END
    FROM order_fulfillment_state f
    WHERE o.id = :order_id AND f.order_id = :order_id
    RETURNING o.status
"""

CONSUME_TOPICS = ["payment-processed", "inventory-reserved"]


async def run_order_status_consumer(stop_event: asyncio.Event, producer: AIOKafkaProducer) -> None:
    """Consumes payment/inventory results, updates order_fulfillment_state,
    syncs orders.status, and — only on an actual status transition, not on
    every redelivered event — publishes a single consolidated
    order-confirmed / order-cancelled event for notification-service.
    """
    
    consumer = AIOKafkaConsumer(
        *CONSUME_TOPICS,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        security_protocol=settings.kafka_security_protocol,
        group_id="order-service-status-updater",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    logger.info("order status consumer started, topics=%s", CONSUME_TOPICS)

    try:
        while not stop_event.is_set():
            batches = await consumer.getmany(timeout_ms=1000, max_records=50)
            for tp, messages in batches.items():
                for msg in messages:
                    await _handle_message(tp.topic, msg, producer)
            if batches:
                await consumer.commit()
    finally:
        await consumer.stop()
        logger.info("order status consumer stopped")


async def _handle_message(topic: str, msg, producer: AIOKafkaProducer) -> None:
    try:
        event = json.loads(msg.value)
    except json.JSONDecodeError:
        logger.exception("skipping unparseable message at offset=%s", msg.offset)
        return

    order_id = event.get("order_id")
    raw_status = event.get("status")
    new_status = STATUS_MAP.get(topic, {}).get(raw_status)
    column = COLUMN_FOR_TOPIC.get(topic)

    if new_status is None or column is None:
        logger.warning("unrecognized status=%s on topic=%s, skipping", raw_status, topic)
        return

    async with async_session_factory() as session:
        async with session.begin():
            # Lock the row and read its status BEFORE updating, so we can
            # tell whether this event actually causes a transition — at-
            # least-once redelivery means the same event can arrive again
            # after the order is already confirmed/cancelled, and we must
            # not re-publish in that case.
            prev_row = await session.execute(
                text("SELECT status FROM orders WHERE id = :order_id FOR UPDATE"),
                {"order_id": order_id},
            )
            prev = prev_row.fetchone()
            if prev is None:
                logger.warning("no order found for id=%s (topic=%s)", order_id, topic)
                return
            previous_status = prev.status
            
            await session.execute(
                text(f"""
                    INSERT INTO order_fulfillment_state (order_id, {column}, updated_at)
                    VALUES (:order_id, :new_status, now())
                    ON CONFLICT (order_id) DO UPDATE
                    SET {column} = EXCLUDED.{column}, updated_at = now()
                """),
                {"order_id": order_id, "new_status": new_status},
            )

            result = await session.execute(
                text(SYNC_ORDER_STATUS_SQL),
                {"order_id": order_id},
            )
            row = result.fetchone()
            current_status = row.status if row else previous_status

            fulfillment_row = await session.execute(
                text("SELECT payment_status, inventory_status FROM order_fulfillment_state WHERE order_id = :id"),
                {"id": order_id},
            )
            fulfillment = fulfillment_row.mappings().first()

    logger.info(
        "order_id=%s %s(%s) synced -> order.status=%s",
        order_id, column, new_status, current_status,
    )
    
    # Only publish on an actual transition into a terminal state.
    output_topic = OUTPUT_TOPIC_FOR_STATUS.get(current_status)
    if output_topic and current_status != previous_status:
        payload = {
            "order_id": order_id,
            "status": current_status,
            "payment_status": fulfillment["payment_status"] if fulfillment else None,
            "inventory_status": fulfillment["inventory_status"] if fulfillment else None,
        }
        await producer.send_and_wait(
            output_topic,
            key=str(order_id).encode(),
            value=json.dumps(payload).encode(),
        )
        logger.info("published order_id=%s -> %s", order_id, output_topic)