# Payment Service

Part of [`real-time-ecommerce-platform`](../../README.md). Consumes `order-created`, simulates payment processing, publishes the result to `payment-processed`.

No real payment provider is integrated — `app/consumer.py` simulates success/failure via `SIMULATED_FAILURE_RATE` so you can exercise error paths without a real integration. Swap in a real provider call where noted.

Consumer uses manual offset commit *after* a successful publish (at-least-once delivery) — see the docstring in `app/consumer.py` for the trade-off.

Run as part of the full stack via the root `docker-compose.yml` / `Makefile` — see the [root README](../../README.md#running-locally).