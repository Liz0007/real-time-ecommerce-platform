# app/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_security_protocol: str = "PLAINTEXT"

    consumer_group_id: str = "inventory-service"
    consume_topic: str = "order-created"
    publish_topic: str = "inventory-reserved"

    # Simulated stock check — replace with a real inventory DB lookup.
    simulated_out_of_stock_rate: float = 0.0  # 0.0-1.0


settings = Settings()
