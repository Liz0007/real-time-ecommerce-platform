# Inventory Service

Part of [`real-time-ecommerce-platform`](../../README.md). Consumes
`order-created`, simulates a stock reservation check, publishes the result to `inventory-reserved`.

No real inventory database is integrated — `app/consumer.py` simulates in-stock/out-of-stock via `SIMULATED_OUT_OF_STOCK_RATE`. Replace with a real stock lookup/reservation where noted.

Run as part of the full stack via the root `docker-compose.yml` / `Makefile` — see the [root README](../../README.md#running-locally).