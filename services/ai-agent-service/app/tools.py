import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field, ValidationError

ORDER_SERVICE_URL = "http://order-service:8000"
PAYMENT_SERVICE_URL = "http://payment-service:8000"
INVENTORY_SERVICE_URL = "http://inventory-service:8000"


class OrderStatus(BaseModel):
    """Structured, validated shape for an order lookup result.
 
    Raw JSON from order-service is parsed into this model before being
    returned to the agent, so the LLM (and anything downstream) always
    sees a guaranteed, typed shape instead of an arbitrary dict — and
    a malformed/unexpected response from order-service fails loudly
    here instead of silently confusing the LLM.
 
    Matches the actual order-service response shape:
    {"id": ..., "customer_id": ..., "status": ..., "total_amount": ...}
    """
 
    id: str
    customer_id: str
    status: str = Field(description="e.g. pending, paid, shipped, cancelled")
    total_amount: float
    currency: str = "EUR"

def _safe_get(url: str, not_found_msg: str) -> dict:
    """Shared error handling for all tool HTTP calls. Never raises —
    always returns either the parsed JSON or a structured error dict,
    so a downstream service being unreachable or returning 404 becomes
    something the agent can read and respond to sensibly, instead of
    an unhandled exception that crashes the whole request."""
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": not_found_msg}
        if e.response.status_code == 422:
            return {"error": "The ID provided isn't in a valid format for this lookup."}
        return {"error": f"Upstream service returned {e.response.status_code}."}
    except httpx.RequestError as e:
        return {"error": f"Could not reach upstream service: {e}"}

    
@tool
def get_order_status(order_id: str) -> OrderStatus:
    """Look up the status of an order by its ID. Return a structured OrderStatus."""
    data = _safe_get(f"{ORDER_SERVICE_URL}/orders/{order_id}", f"No order found with ID {order_id}.")
    if "error" in data:
        return data
    try:
        return OrderStatus.model_validate(data).model_dump()
    except ValidationError as e:
        return {"error": f"Could not reach upstream service: {e}"}

@tool
def get_payment_status(order_id: str) -> dict:
    """Look up the payment status for a given order ID."""
    return _safe_get(
        f"{PAYMENT_SERVICE_URL}/payments/{order_id}",
        f"No payment record found for order {order_id}.",
    )
 
 
@tool
def check_inventory(order_id: str) -> dict:
    """Check whether inventory was reserved for a given order."""
    return _safe_get(
        f"{INVENTORY_SERVICE_URL}/inventory/{order_id}",
        f"No inventory reservation found for order {order_id}.",
    )


# search_knowledge_base gets added here once rag.py exists, e.g.:
# from app.rag import search_knowledge_base

# Registry: display name -> tool. This is what the UI's multi-select
# dropdown populates itself from, and what the agent filters against.
TOOL_REGISTRY = {
    "order": get_order_status,
    "payment": get_payment_status,
    "inventory": check_inventory,
    # "rag": search_knowledge_base,
}
