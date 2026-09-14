# Load Generator

Not part of the event-driven architecture itself — a small standalone
script that continuously creates fake orders against order-service's
`POST /orders`, so the rest of the pipeline (payment-service,
inventory-service, notification-service, data-pipeline) has real,
continuous traffic to demo.

Uses a fixed pool of 25 fake customer UUIDs (regenerated each run) rather
than a brand-new customer per order, so the data looks like a real
customer base with repeat buyers rather than one-off strangers. Order
amounts skew toward smaller values (85% under $90) with occasional larger
orders, for a vaguely realistic distribution.

## Running locally (without Docker)

```bash
pip install -r requirements.txt
python generate_orders.py --url http://localhost:8000 --rate 1.0
```

## Running as part of the stack

Not started by `make up` — it's an opt-in Compose profile:

```bash
make load-gen                    # 1 order/sec, runs until Ctrl+C
make load-gen RATE=3             # 3 orders/sec
make load-gen RATE=0.5 DURATION=120   # one order every 2s, stops after 2 minutes
```
