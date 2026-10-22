"""Creates the Kafka topics this platform uses.

Locally, docker-compose's kafka-init container does this. MSK has no such
hook, Terraform has no resource for Kafka topics, and the brokers sit in
private subnets — so this runs as a one-off ECS task inside the VPC:

    aws ecs run-task \
      --cluster ecommerce-demo-cluster \
      --task-definition ecommerce-demo-order-service \
      --launch-type FARGATE \
      --network-configuration "awsvpcConfiguration={subnets=[...],securityGroups=[...]}" \
      --overrides '{"containerOverrides":[{"name":"order-service",
                    "command":["python","-m","app.create_topics"]}]}' \
      --region eu-south-2

It deliberately reuses this service's own Kafka settings and
kafka_client_kwargs(), so it authenticates exactly the way the running
services do — if topic creation works, their connections will too.
"""

import asyncio
import logging

from aiokafka.admin import AIOKafkaAdminClient, NewTopic

from app.config import settings
from app.kafka_auth import kafka_client_kwargs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Must match kafka-init in docker-compose.yml.
TOPICS = [
    "order-created",
    "payment-processed",
    "inventory-reserved",
    "order-confirmed",
    "order-cancelled",
]

PARTITIONS = 3
# 2 matches the MSK broker count. Locally this is 1, since there is one broker.
REPLICATION_FACTOR = 2


async def main() -> None:
    admin = AIOKafkaAdminClient(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        **kafka_client_kwargs(),
    )
    await admin.start()
    try:
        existing = set(await admin.list_topics())
        missing = [t for t in TOPICS if t not in existing]

        for topic in TOPICS:
            if topic in existing:
                logger.info("exists: %s", topic)

        if not missing:
            logger.info("nothing to create")
            return

        await admin.create_topics([
            NewTopic(
                name=t,
                num_partitions=PARTITIONS,
                replication_factor=REPLICATION_FACTOR,
            )
            for t in missing
        ])
        for t in missing:
            logger.info("created: %s", t)

        logger.info("topics now: %s", sorted(await admin.list_topics()))
    finally:
        await admin.close()


if __name__ == "__main__":
    asyncio.run(main())
