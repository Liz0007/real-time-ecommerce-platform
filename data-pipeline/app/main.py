# app/main.py

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.consumer import run_consumer
from app.supervision import watch
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()
    consumer_task = asyncio.create_task(run_consumer(stop_event))
    watch(consumer_task, stop_event, "data-pipeline consumer")
    yield

    stop_event.set()
    await consumer_task


app = FastAPI(title="Data Pipeline", lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {"status": "ok"}