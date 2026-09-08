# app/main.py

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.consumer import run_consumer

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()
    consumer_task = asyncio.create_task(run_consumer(stop_event))

    yield

    stop_event.set()
    await consumer_task


app = FastAPI(title="Notification Service", lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {"status": "ok"}