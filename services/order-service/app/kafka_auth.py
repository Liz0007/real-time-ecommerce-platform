"""Kafka client authentication.

Local development uses PLAINTEXT against the Kafka container. AWS MSK with
IAM authentication uses SASL_SSL with the OAUTHBEARER mechanism, where the
"token" is a short-lived, pre-signed AWS request generated from whatever
credentials the process already has (locally an access key, on ECS the
task role).

Both are handled by one switch on KAFKA_SECURITY_PROTOCOL, so the same
image runs in both places with no code change — only configuration.
"""

import asyncio
import logging

from aiokafka.abc import AbstractTokenProvider

from app.config import settings

logger = logging.getLogger(__name__)


class MSKTokenProvider(AbstractTokenProvider):
    """Supplies MSK IAM auth tokens to aiokafka.

    Tokens are short-lived (~15 minutes), so aiokafka calls token() again
    whenever it needs to (re)authenticate a connection — this must stay
    cheap and must not cache beyond a single call.
    """

    def __init__(self, region: str) -> None:
        self.region = region

    async def token(self) -> str:
        # generate_auth_token() is synchronous and may perform credential
        # lookups (IMDS, STS), so it runs in a thread rather than blocking
        # the event loop that the consumers and producers share.
        return await asyncio.to_thread(self._generate)

    def _generate(self) -> str:
        # Imported lazily so services running against local Kafka don't
        # need the AWS signer library installed or importable.
        from aws_msk_iam_sasl_signer import MSKAuthTokenProvider

        token, _expiry_ms = MSKAuthTokenProvider.generate_auth_token(self.region)
        return token


def kafka_client_kwargs() -> dict:
    """Connection kwargs shared by every AIOKafkaProducer/AIOKafkaConsumer
    in this service. Spread into the constructor:

        AIOKafkaConsumer(topic, bootstrap_servers=..., **kafka_client_kwargs())
    """
    protocol = settings.kafka_security_protocol

    if protocol == "SASL_SSL":
        logger.info("kafka auth: SASL_SSL + OAUTHBEARER (MSK IAM), region=%s", settings.aws_region)
        return {
            "security_protocol": "SASL_SSL",
            "sasl_mechanism": "OAUTHBEARER",
            "sasl_oauth_token_provider": MSKTokenProvider(settings.aws_region),
        }

    logger.info("kafka auth: %s (no SASL)", protocol)
    return {"security_protocol": protocol}
