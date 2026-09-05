from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

class OrderCreate(BaseModel):
    customer_id: UUID
    total_amount: Decimal = Field(gt=0)
    
class OrderResponse(BaseModel):
    id: UUID
    customer_id: UUID
    status: str
    total_amount: Decimal