# Real-Time E-Commerce Data Platform

A production-oriented event-driven e-commerce platform built with Python,
FastAPI, PostgreSQL, Apache Kafka, and AWS.

## Project Goals

This project is being built to demonstrate:

- REST API development
- PostgreSQL data modeling
- Apache Kafka event streaming
- Event-driven microservices
- Transactional outbox pattern
- Idempotent consumers
- Retry and dead-letter queues
- Real-time data ingestion
- AWS cloud infrastructure
- Infrastructure as Code with Terraform
- CI/CD
- Monitoring and observability

## Architecture

                  CLIENT
                    │
                    ▼
              ┌───────────┐
              │  FastAPI  │
              │Order API  │
              └─────┬─────┘
                    │
                    ▼
              ┌───────────┐
              │ PostgreSQL│
              │  Orders   │
              └─────┬─────┘
                    │
            Transactional Outbox
                    │
                    ▼
            ┌───────────────┐
            │     Kafka     │
            │  AWS MSK      │
            └───────┬───────┘
                    │
        ┌───────────┼────────────┐
        ▼           ▼            ▼
    Payment      Inventory   Notification
    Service       Service       Service
        │           │            │
        └───────────┼────────────┘
                    │
                    ▼
             DATA PIPELINE
                    │
           ┌────────┴────────┐
           ▼                 ▼
        S3 Data Lake     Analytics DB
                              │
                              ▼
                       BI / Reporting


The system will evolve from a local Docker-based environment into an
AWS-based production architecture using ECS, RDS, MSK, S3, and Terraform.

### Key design decisions

- **Transactional outbox, not dual writes** — `order-service` writes the
  order and its event to Postgres in one transaction, then a background
  worker polls the outbox table and publishes to Kafka. Avoids the DB-write
  -succeeds-but-Kafka-publish-fails failure mode without distributed
  transactions.
- **Polling publisher over Debezium/CDC** — keeps the pipeline explainable
  end-to-end without relying on Kafka Connect internals. Swapping in
  Debezium later is a reasonable v2; the atomicity guarantee is the same
  either way.
- **Local Kafka in KRaft mode** — no Zookeeper. Topics are created
  explicitly by a one-shot `kafka-init` container rather than relying on
  Kafka's auto-create, so topic ownership is visible and versioned.

## Status

🚧 Project under development

| Component | Status |
|---|---|
| `order-service` — orders API + transactional outbox → Kafka | ✅ Done, verified locally |
| `payment-service` | ⬜ Not started |
| `inventory-service` | ⬜ Not started |
| `notification-service` | ⬜ Not started |
| `data-pipeline` — Kafka → data lake + analytics DB | ⬜ Not started |
| Idempotent consumers / retry / DLQ | ⬜ Not started |
| Terraform / AWS deployment | ⬜ Not started |
| CI/CD | ⬜ Not started |
| Monitoring / observability | ⬜ Not started |

### Current Stage

Stage 2 — `order-service` complete (transactional outbox verified against
local Kafka). Next: `payment-service`.

## Repository layout
real-time-ecommerce-platform/
├── docker-compose.yml # orchestrates Postgres, Kafka (KRaft), topic init, order-service
├── Makefile # make up / down / logs / topics / test
└── services/
└── order-service/ # built — see services/order-service/README.md

## Running locally

Requires Docker and Docker Compose.

```bash
git clone <this-repo>
cd real-time-ecommerce-platform
cp services/order-service/.env.example services/order-service/.env
make up
```

- `order-service` → http://localhost:8000 (docs at `/docs`, health at `/health`)
- `make topics` — verify the `order-created` topic was created
- `make logs` — tail order-service logs
- `make down` / `make clean` — stop (optionally wiping volumes)

Create an order and confirm the event reaches Kafka:

```bash
curl -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{"customer_id": "11111111-1111-1111-1111-111111111111", "total_amount": "49.99"}'

docker compose exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic order-created \
  --from-beginning
```

## Running tests

```bash
make test
```