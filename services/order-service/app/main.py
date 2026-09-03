from fastapi import FastAPI

app = FastAPI(
    title="E-Commerce Order Service",
    version="0.1.0",
)


@app.get("/health")
async def health():
    """Liveness/readiness probe used by Docker HEALTHCHECK and orchestrators."""

    return {"status": "ok"}