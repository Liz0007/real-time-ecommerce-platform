# Order Service

Part of the [`real-time-ecommerce-platform`](../../README.md) project — see
the root README for the full system architecture and how this service fits
in. Handles order creation and publishes order lifecycle events to Kafka
using the **transactional outbox pattern**, so an order is never persisted
without its corresponding event eventually reaching Kafka (and vice versa).

## Architecture

```
Client → FastAPI (Order API) → PostgreSQL (orders + outbox, same transaction)
                                        │
                              outbox publisher (polling worker)
                                        │
                                        ▼
                                     Kafka
```

- **Write path**: `POST /orders` writes the `orders` row and an `outbox` row
  in a single DB transaction — this is what guarantees atomicity between
  "the order exists" and "an event describing it exists," without needing
  distributed transactions or two-phase commit.
- **Publish path**: a background worker (`app/workers/outbox_publisher.py`)
  polls the `outbox` table for unpublished rows, sends them to Kafka, and
  marks them published. It runs inside the FastAPI process via `lifespan`.
- Retries are tracked per-row (`attempts`, `last_error`); rows stop being
  retried after `OUTBOX_MAX_ATTEMPTS` so a malformed event can't loop forever.
- `FOR UPDATE SKIP LOCKED` on the polling query means this is safe to run as
  multiple worker instances later without double-publishing.

**Why polling instead of Debezium/CDC?** Debezium + Kafka Connect (reading
Postgres's WAL) is the more "production-grade" way to implement this pattern,
and would be a reasonable v2. Polling was chosen here to keep the moving
parts explainable end-to-end for a solo project — the atomicity guarantee
that matters is the same either way; only the publish mechanism differs.

## Local development

This service is run as part of the full stack via the **root-level**
`docker-compose.yml` and `Makefile` — see the [root README](../../README.md#running-locally)
for `make up` / `make logs` / `make down` instructions. There's no
service-level compose file; orchestration lives at the repo root so Kafka
and Postgres are shared across all services.

## Running tests

From the repo root:

```bash
make test SERVICE=order-service
```

## Kafka topics

| Topic              | Produced by    | Consumed by (planned)             |
|---------------------|----------------|------------------------------------|
| `order-created`      | order-service  | payment-service, inventory-service |
| `order-updated`      | order-service  | notification-service               |
| `order-cancelled`    | order-service  | payment-service, inventory-service |

## Environment variables

See `.env.example` for the full list. Notable ones:

- `KAFKA_SECURITY_PROTOCOL` — `PLAINTEXT` for local Kafka; will become
  `SASL_SSL` when pointed at AWS MSK (auth mode TBD).
- `DATABASE_URL` — SQLAlchemy async connection string (asyncpg driver).

## Project layout

```
app/
├── main.py                    # FastAPI app, lifespan (Kafka producer + worker)
├── config.py                  # pydantic-settings config
├── db.py                      # async SQLAlchemy engine/session
├── schemas.py                 # Pydantic request/response models
├── repositories/
│   └── order_repository.py    # order + outbox write (same transaction)
├── routers/
│   └── orders.py               # POST /orders, GET /orders/{id}
└── workers/
    └── outbox_publisher.py     # polling worker → Kafka
migrations/                     # plain SQL, run automatically by Postgres on first boot
tests/
```