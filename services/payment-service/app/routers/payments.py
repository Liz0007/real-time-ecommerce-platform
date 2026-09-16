from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session

router = APIRouter(prefix="/payments", tags=["payments"])

@router.get("/{order_id}")
async def get_payment(order_id: UUID, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        text("SELECT order_id, status, amount, processed_at FROM payments WHERE order_id = :id"),
        {"id": order_id},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="No payment record for this order")
    return dict(row)