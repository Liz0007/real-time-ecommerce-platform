# app/repositories/order_repository.py

import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import OrderCreate, OrderResponse


async def create_order_with_event(session: AsyncSession, order_in: OrderCreate) -> OrderResponse:
    """Insert the order and its outbox event in a single DB transaction.

    Atomicity here is the whole point of the outbox pattern: either both
    rows commit, or neither does. The event is published to Kafka later,
    asynchronously, by the outbox publisher worker.
    """
    order_id = uuid4()
    status = "pending"

    async with session.begin():
        await session.execute(
            text("""
                INSERT INTO orders (id, customer_id, status, total_amount)
                VALUES (:id, :customer_id, :status, :total_amount)
            """),
            {
                "id": order_id,
                "customer_id": order_in.customer_id,
                "status": status,
                "total_amount": order_in.total_amount,
            },
        )

        payload = {
            "id": str(order_id),
            "customer_id": str(order_in.customer_id),
            "status": status,
            "total_amount": str(order_in.total_amount),
        }

        await session.execute(
            text("""
                INSERT INTO outbox (aggregate_type, aggregate_id, event_type, payload)
                VALUES (:aggregate_type, :aggregate_id, :event_type, :payload)
            """),
            {
                "aggregate_type": "order",
                "aggregate_id": order_id,
                "event_type": "order.created",
                "payload": json.dumps(payload),
            },
        )

    return OrderResponse(
        id=order_id,
        customer_id=order_in.customer_id,
        status=status,
        total_amount=order_in.total_amount,
    )


async def get_order(session: AsyncSession, order_id: UUID) -> OrderResponse | None:
    result = await session.execute(
        text("""
            SELECT id, customer_id, status, total_amount
            FROM orders
            WHERE id = :id
        """),
        {"id": order_id},
    )
    row = result.mappings().first()
    if row is None:
        return None
    return OrderResponse(**row)
