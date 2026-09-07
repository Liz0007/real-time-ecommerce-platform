import asyncio, logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
from aiokafka import AIOKafkaProducer

from app.config import settings
from app.db import async_session_factory
from app.routers.orders import router as orders_router
from app.workers.outbox_publisher import run_outbox_publisher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        security_protocol=settings.kafka_security_protocol,
    )
    await producer.start()

    stop_event = asyncio.Event()
    worker_task = asyncio.create_task(run_outbox_publisher(async_session_factory, producer, stop_event))

    yield

    stop_event.set()
    await worker_task
    await producer.stop()


app = FastAPI(
    title="E-Commerce Order Service",
    version="0.1.0",
    lifespan=lifespan
)

app.include_router(orders_router)

@app.get("/health")
async def health():
    """Liveness/readiness probe used by Docker HEALTHCHECK and orchestrators."""

    return {"status": "ok"}