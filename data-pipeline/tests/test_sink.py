"""The S3 sink path, which local runs never exercise (they use the file sink)."""

import asyncio
import json

from app import sink as sink_mod
from app.config import settings


class FakeS3:
    def __init__(self):
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)


def test_get_sink_returns_an_s3_sink_object_in_s3_mode(monkeypatch):
    monkeypatch.setattr(settings, "sink_mode", "s3")
    monkeypatch.setattr(sink_mod.S3Sink, "__init__", lambda self: setattr(self, "_client", FakeS3()))
    assert isinstance(sink_mod.get_sink(), sink_mod.S3Sink)


def test_s3_sink_writes_ndjson_partitioned_by_topic_and_date(monkeypatch):
    monkeypatch.setattr(settings, "s3_bucket", "lake")
    s = sink_mod.S3Sink.__new__(sink_mod.S3Sink)
    s._client = FakeS3()
    asyncio.run(s.write_batch("order-created", [{"a": 1}, {"b": 2}]))
    call = s._client.calls[0]
    assert call["Bucket"] == "lake"
    assert call["Key"].startswith("topic=order-created/date=") and call["Key"].endswith(".jsonl")
    assert [json.loads(line) for line in call["Body"].decode().splitlines()] == [{"a": 1}, {"b": 2}]