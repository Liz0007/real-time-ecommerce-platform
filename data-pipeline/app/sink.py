# app/sink.py

import json, logging, os
from datetime import datetime, timezone
from typing import Protocol

from app.config import settings

logger = logging.getLogger(__name__)

class Sink(Protocol):
    async def write_batch(sefl, topic: str, records: list[dict]) -> None: ...
    

class LocalFileSink:
    """Writes newline-delimited JSON to local disk, partitioned by topic/date —
    mirrors the S3 key layout so switching sinks later doesn't change the
    downstream analytics loader's assumptions. Meant for local dev / running
    the whole stack without an AWS account."""
    
    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir
    
    async def write_batch(self, topic: str, records: list[dict]) -> None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dir_path = os.path.join(self.base_dir, topic, date_str)
        os.makedirs(dir_path, exist_ok=True)
        
        filename = f"{datetime.now(timezone.utc).strftime('%H%M%S_%f')}.jsonl"
        file_path = os.path.join(dir_path, filename)
        
        with open(file_path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        
        logger.info("wrote %d records to %s", len(records), file_path)
        
class S3Sink:
    """Writes newline-delimited JSON to S3 (or LocalStack, via s3_endpoint_url),
    partitioned as topic=<topic>/date=<YYYY-MM-DD>/<timestamp>.jsonl — a layout
    Athena/Glue can partition on directly."""
    
    def __init__(self) -> None:
        import boto3 # imported lazily so local-mode doesn't require boto3 configured
        
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.aws_region,
        )
                        
    async def write_batch(self, topic: str, records: list[dict]) -> None:
        import asyncio
        
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        timestamp = datetime.now(timezone.utc).strftime("%H%M%S_%f")
        key = f"topic={topic}/date={date_str}/{timestamp}.jsonl"
        body = "\n".join(json.dumps(r) for r in records).encode()
        
        # boto3 is sync — run in a thread so we don't block the event loop.
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=settings.s3_bucket,
            Key=key,
            Body=body,
        )
        logger.info("wrote %d records to s3://%s/%s", len(records), settings.s3_bucket, key)

def get_sink() -> Sink:
    if settings.sink_mode == "s3":
        return S3Sink
    return LocalFileSink(settings.local_data_dir)