# Data Pipeline

Part of [`real-time-ecommerce-platform`](../README.md). Consumes every
order-lifecycle Kafka topic and lands raw events in a data lake, then a
separate batch script loads them into an analytics database for BI queries.

## Two stages, deliberately separate

1. **Ingestion (long-running consumer, `app/`)** — subscribes to
   `order-created`, `order-cancelled`, `payment-processed`, and
   `inventory-reserved`, batches records per topic, and writes them as
   newline-delimited JSON to a sink (local disk or S3), partitioned as
   `topic=<topic>/date=<YYYY-MM-DD>/<file>.jsonl` — a layout tools like
   Athena/Glue can partition on directly.
2. **Load into analytics DB (batch script, `scripts/load_analytics_db.py`)**
   — reads a given date's JSONL files and upserts them into a Postgres table
   for BI/reporting. Run on a schedule (cron, Airflow, EventBridge+Lambda) —
   it's intentionally not a long-running container.

Keeping these separate mirrors how a real lake/warehouse split works: the
lake is the durable, replayable raw event store; the warehouse is a derived,
queryable projection you can rebuild from the lake at any time.

## Running without an AWS account

Set `SINK_MODE=local` (the default) and events are written under
`LOCAL_DATA_DIR` instead of S3 — the whole platform runs locally with zero
AWS dependency. Flip to `SINK_MODE=s3` (optionally with `S3_ENDPOINT_URL`
pointed at a LocalStack container) when you want to exercise the real path.

## Running the analytics loader

```bash
pip install -e ".[analytics]"
python scripts/load_analytics_db.py --date 2026-09-03
python scripts/load_analytics_db.py --date 2026-09-03 --topic order-created
```

Requires a Postgres instance reachable at `ANALYTICS_DATABASE_URL` — separate
from the `order-service` operational database, matching a real OLTP/OLAP split.
