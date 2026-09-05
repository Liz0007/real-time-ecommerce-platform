# app/routers/orders.py

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.repositories.order_repository import create_order_with_event, get_order
from app.schemas import OrderCreate, OrderResponse

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_in: OrderCreate,
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    """Create an order. Writes the order row and an outbox event atomically;
    the outbox publisher worker picks up the event and sends it to Kafka."""
    return await create_order_with_event(session, order_in)


@router.get("/{order_id}", response_model=OrderResponse)
async def read_order(
    order_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    order = await get_order(session, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
