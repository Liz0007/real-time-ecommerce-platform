import asyncio, json, logging
from collections import defaultdict
from datetime import datetime, timezone

from aiokafka import AIOKafkaConsumer

from app.config import settings
from app.sink import get_sink

logger = logging.getLogger(__name__)

async def run_consumer(stop_event: asyncio.Event) -> None:
    """Consume every order-lifecycle topic and land events in the data lake,
    batched per topic for efficient writes (one file per batch rather than
    one file per event).
    """
    consumer = AIOKafkaConsumer(
        *settings.consume_topics,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        security_protocol=settings.kafka_security_protocol,
        group_id=settings.consumer_group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    sink = get_sink()
    
    await consumer.start()
    logger.info("data-pipeline consumer started, topics=%s", settings.consume_topics)
    
    buffers: dict[str, list[dict]] = defaultdict(list)
    last_flush = datetime.now(timezone.utc)
    
    try:
        while not stop_event.is_set():
            batches = await consumer.getmany(
                timeout_ms=1000,
                max_records=settings.flush_batch_size
            )
            for tp, messages in batches.items():
                for msg in messages:
                    record = _to_record(tp.topic, msg)
                    if record is not None:
                        buffers[tp.topic].append(record)
            
            now = datetime.now(timezone.utc)
            should_flush = (
                any(len(v) >= settings.flush_batch_size for v in buffers.values())
                or (now - last_flush).total_seconds() >=settings.flush_interval_seconds
            )
            
            if should_flush and any(buffers.values()):
                try:
                    for topic, records in buffers.items():
                        if records:
                            await sink.write_batch(topic, records)
                    await consumer.commit()        
                    buffers = defaultdict(list)
                    last_flush = now
                except Exception:
                    logger.exception("failed to flush batch to sink — will retry next poll")
    finally:    
        # Flush whatever's left on shutdown so a clean stop doesn't drop data.
        for topic, records in buffers.items():
            await sink.write_batch(topic, records)
        await consumer.stop()
        logger.info("data-pipeline consumer stopped")

def _to_record(topic: str, msg) -> dict | None:
    try:
        payload = json.loads(msg.value)
    except json.JSONDecodeError:
        logger.exception("skipping unparseable message at offset=%s", msg.offset)
        return None

    return {
        "topic": topic,
        "partition": msg.partition,
        "offset": msg.offset,
        "kafka_timestamp": msg.timestamp,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }        