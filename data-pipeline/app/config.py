# app/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_security_protocol: str = "PLAINTEXT"

    consumer_group_id: str = "data-pipeline"
    consume_topics: list[str] = [
        "order-created",
        #"order-cancelled",
        "payment-processed",
        "inventory-reserved",
    ]

    # Data lake sink. Set sink_mode to "s3" and configure the bucket/endpoint
    # to write to real S3 (or LocalStack for local dev); "local" writes
    # newline-delimited JSON files under local_data_dir instead — useful for
    # running the whole stack without any AWS account at all.
    sink_mode: str = "local"  # "local" | "s3"
    local_data_dir: str = "/data/lake"

    s3_bucket: str = "ecommerce-platform-data-lake"
    s3_endpoint_url: str | None = None  # set for LocalStack, e.g. http://localstack:4566
    aws_region: str = "eu-south-2"

    # How many records to buffer before flushing a batch to the sink.
    flush_batch_size: int = 100
    flush_interval_seconds: float = 10.0


settings = Settings()