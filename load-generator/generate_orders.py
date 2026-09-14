"""
Continuously creates realistic fake orders against order-service's
POST /orders, so the rest of the pipeline has real, continuous traffic
to test instead of one manually-curled order at a time.

Usage:
    python generate_orders.py
    python generate_orders.py --rate 5 --duration 60
"""

import argparse
import logging
import random
import time
import uuid
from decimal import Decimal, ROUND_HALF_UP

import httpx
from faker import Faker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

fake = Faker()
CUSTOMER_POOL_SIZE = 25

def build_customer_pool(size: int) -> list[dict]:
    return [
        {"id": str(uuid.uuid4()), "name": fake.name(), "email": fake.email()}
        for _ in range(size)
    ]

def random_order_amount() -> str:
    if random.random() < 0.85:
        amount = random.uniform(9.99, 89.99)
    else:
        amount = random.uniform(90.00, 349.99)
    return str(Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def create_order(client: httpx.Client, base_url: str, customer_id: str) -> None:
    payload = {"customer_id": customer_id, "total_amount": random_order_amount()}
    try:
        response = client.post(f"{base_url}/orders", json=payload, timeout=5.0)
        response.raise_for_status()
        order = response.json()
        logger.info("created order id=%s customer=%s amount=%s",
                     order["id"], customer_id, payload["total_amount"])
    except httpx.HTTPStatusError as exc:
        logger.error("failed to create order (%s): %s", exc.response.status_code, exc.response.text)
    except httpx.HTTPError as exc:
        logger.error("failed to create order: %s", exc)


def run(base_url: str, rate: float, duration: float | None) -> None:
    customers = build_customer_pool(CUSTOMER_POOL_SIZE)
    interval = 1.0 / rate if rate > 0 else 1.0

    logger.info("starting load generator: url=%s rate=%.2f orders/sec duration=%s",
                base_url, rate, f"{duration}s" if duration else "unlimited")

    start = time.monotonic()
    with httpx.Client() as client:
        while duration is None or (time.monotonic() - start) < duration:
            customer = random.choice(customers)
            create_order(client, base_url, customer["id"])
            time.sleep(interval)

    logger.info("load generator finished")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--rate", type=float, default=1.0)
    parser.add_argument("--duration", type=float, default=None)
    args = parser.parse_args()

    try:
        run(args.url, args.rate, args.duration)
    except KeyboardInterrupt:
        logger.info("stopped by user")


if __name__ == "__main__":
    main()