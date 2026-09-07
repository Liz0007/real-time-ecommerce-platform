from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/orders"
    
    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_security_protocol: str = "PLAINTEXT"  # later: "SASL_SSL" for MSK

    # Outbox publisher worker
    outbox_poll_interval_seconds: float = 2.0
    outbox_batch_size: int = 50
    outbox_max_attempts: int = 5
    
    
settings = Settings()