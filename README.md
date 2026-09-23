# Real-Time E-Commerce Data Platform

A production-oriented event-driven e-commerce platform built with Python,
FastAPI, PostgreSQL, Apache Kafka, and AWS — with an AI agent layer on top
that answers questions about orders, payments, and inventory using the
platform's own services as tools.

## Project Goals

This project is being built to demonstrate:

- REST API development
- PostgreSQL data modeling
- Apache Kafka event streaming
- Event-driven microservices
- Transactional outbox pattern
- Choreography sagas / eventual consistency across services
- AI agent tool-use and function calling (LangGraph)
- Retrieval-augmented generation (RAG) over internal docs
- Idempotent consumers
- Real-time data ingestion
- AWS cloud infrastructure
- Infrastructure as Code with Terraform
- CI/CD
- Monitoring and observability

## Architecture

```
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
                  │  Orders + │
                  │ Fulfillment│
                  │   State   │
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
            ▼           ▼            │
        Payment      Inventory       │
        Service       Service        │
            │           │            │
            └─────┬─────┘            │
                  ▼                  │
          order-service syncs        │
       orders.status, publishes      │
      order-confirmed/-cancelled     │
                  │                  │
                  ▼                  │
          Notification Service ◄─────┘
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

          ┌─────────────────────────┐
          │   AI Agent Service      │
          │  (LangGraph + Claude)   │◄── Streamlit UI (agent-ui)
          │                         │
          │  tools: order, payment, │
          │  inventory, RAG         │
          └───────────┬─────────────┘
                       │  reads via HTTP
                       ▼
        order-service / payment-service / inventory-service
```

The system will evolve from a local Docker-based environment into an
AWS-based production architecture using ECS, RDS, MSK, S3, and Terraform.

### Key design decisions

- **Transactional outbox, not dual writes** — `order-service` writes the
  order and its event to Postgres in one transaction, then a background
  worker polls the outbox table and publishes to Kafka. Avoids the
  DB-write-succeeds-but-Kafka-publish-fails failure mode without
  distributed transactions.
- **Polling publisher over Debezium/CDC** — keeps the pipeline explainable
  end-to-end without relying on Kafka Connect internals. Swapping in
  Debezium later is a reasonable v2; the atomicity guarantee is the same
  either way.
- **Choreography saga, with fulfillment state kept separate from the order
  entity** — `payment-service` and `inventory-service` each independently
  react to `order-created`; neither knows about the other. `order-service`
  consumes both of their results and tracks "have I heard from each"
  in a dedicated `order_fulfillment_state` table — not as extra columns on
  `orders` — so the order's own schema stays about the order, not about
  coordination bookkeeping. Once both results are in, `order-service`
  computes the order's real status and publishes a single consolidated
  `order-confirmed`/`order-cancelled` event, rather than downstream
  consumers having to piece together two separate raw events themselves.
- **Local Kafka in KRaft mode** — no Zookeeper. Topics are created
  explicitly by a one-shot `kafka-init` container rather than relying on
  Kafka's auto-create, so topic ownership is visible and versioned.
- **Database per service** — `order-service`, `payment-service`, and
  `inventory-service` each have their own Postgres instance; no service
  queries another's tables directly. Cross-service questions go through
  Kafka events or (for the AI agent) each service's own HTTP API.
- **AI agent has no direct DB access** — `ai-agent-service` answers
  questions about specific orders only by calling the same HTTP APIs a
  human could call, not by querying databases directly. This is what
  makes the system prompt's "cite what you checked" requirement
  enforceable rather than just a suggestion.

## Status

🚧 Project under development

| Component | Status |
|---|---|
| `order-service` — orders API, transactional outbox → Kafka, fulfillment sync | ✅ Done, verified locally |
| `payment-service` — payment processing, persisted results | ✅ Done, verified locally |
| `inventory-service` — stock reservation, persisted results | ✅ Done, verified locally |
| `notification-service` — consumes consolidated order-confirmed/-cancelled | ✅ Done, verified locally |
| `data-pipeline` — Kafka → local/S3 data lake | ✅ Done, verified locally |
| `load-generator` — continuous synthetic order traffic | ✅ Done |
| `ai-agent-service` — LangGraph agent, order/payment/inventory tools, RAG | ✅ Done, verified locally |
| `agent-ui` — Streamlit front-end for the agent | ✅ Done |
| Analytics DB batch loader (lake → Postgres for BI) | ⬜ Not built — deferred |
| Inventory reservation auto-expiry/release | ⬜ Not built — deferred (documented as a known gap) |
| Terraform / AWS deployment | ⬜ Not started |
| CI/CD | ⬜ Not started |
| AI agent observability (LangSmith tracing) | ✅ Done |
| Platform observability (metrics, dashboards, alerting) | ⬜ Not started |

### Current Stage

Full local event pipeline complete, including consolidated order-status
tracking and the AI agent layer (tool-use + RAG) on top of it. Next:
Terraform for AWS deployment.

## Repository layout

```
real-time-ecommerce-platform/
├── docker-compose.yml       # orchestrates Postgres (x3), Kafka (KRaft), topic init, all services
├── Makefile                  # make up / down / logs / topics / test / load-analytics / load-gen
├── services/
│   ├── order-service/        # orders API, transactional outbox, fulfillment-state sync
│   ├── payment-service/      # Kafka consumer/producer, own Postgres
│   ├── inventory-service/    # Kafka consumer/producer, own Postgres
│   ├── notification-service/ # consumes order-confirmed/-cancelled
│   ├── ai-agent-service/     # LangGraph agent, tools, RAG — see its own README
│   └── agent-ui/             # Streamlit front-end for the agent
├── data-pipeline/            # Kafka consumer → data lake, + analytics DB batch loader (loader deferred)
├── load-generator/           # generates continuous fake order traffic for demos
└── terraform/                # AWS deployment (not yet built)
```

## Kafka topics

| Topic                | Produced by                          | Consumed by                                         |
|-----------------------|-----------------------------------------|--------------------------------------------------------|
| `order-created`        | order-service (via outbox)             | payment-service, inventory-service, data-pipeline      |
| `payment-processed`    | payment-service                        | order-service, data-pipeline                           |
| `inventory-reserved`   | inventory-service                      | order-service, data-pipeline                           |
| `order-confirmed`      | order-service (on status transition)   | notification-service                                   |
| `order-cancelled`      | order-service (on status transition)   | notification-service                                   |

## Running locally

Requires Docker and Docker Compose.

```bash
git clone <this-repo>
cd real-time-ecommerce-platform
cp services/order-service/.env.example services/order-service/.env
cp services/ai-agent-service/.env.example services/ai-agent-service/.env  # needs ANTHROPIC_API_KEY
make up
```

- `order-service` → http://localhost:8000 (`/docs`, `/health`)
- `payment-service` → http://localhost:8001
- `inventory-service` → http://localhost:8002
- `notification-service` → http://localhost:8003
- `data-pipeline` → http://localhost:8004
- `ai-agent-service` → http://localhost:8010 (`/docs`)
- `agent-ui` (Streamlit) → http://localhost:8501
- `make topics` — list Kafka topics
- `make logs` — tail order-service logs
- `make load-gen RATE=1` — generate continuous fake order traffic
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

Ask the agent about it once it's confirmed (via http://localhost:8501, or
directly):

```bash
curl -X POST http://localhost:8010/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What'\''s the status of order <the-order-id>?", "enabled_tools": ["order"]}'
```

## Running tests

```bash
make test
```

See [`services/ai-agent-service/README.md`](services/ai-agent-service/README.md)
for that service's architecture, tools, RAG setup, and eval cases in detail.