from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/{order_id}")
async def get_reservation(order_id: UUID, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        text("SELECT order_id, status, reserved_at, expires_at, released_at FROM inventory_reservations WHERE order_id = :id"),
        {"id": order_id},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="No inventory reservation for this order")
    return dict(row)