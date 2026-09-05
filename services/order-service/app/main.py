from fastapi import FastAPI
from app.routers.orders import router as orders_router

app = FastAPI(
    title="E-Commerce Order Service",
    version="0.1.0",
)

app.include_router(orders_router)

@app.get("/health")
async def health():
    """Liveness/readiness probe used by Docker HEALTHCHECK and orchestrators."""

    return {"status": "ok"}