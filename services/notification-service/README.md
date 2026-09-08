# Notification Service

Part of [`real-time-ecommerce-platform`](../../README.md). Consumes
`payment-processed` and `inventory-reserved`, simulates sending a customer
notification for each (logged, not actually sent).

This is the terminal consumer in the event flow — it doesn't publish
further events. Replace the log line in `app/consumer.py` with a real
email/SMS/push integration.

Run as part of the full stack via the root `docker-compose.yml` / `Makefile` — see the [root README](../../README.md#running-locally).
