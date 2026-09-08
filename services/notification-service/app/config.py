# app/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_security_protocol: str = "PLAINTEXT"

    consumer_group_id: str = "notification-service"
    consume_topics: list[str] = ["payment-processed", "inventory-reserved"]


settings = Settings()