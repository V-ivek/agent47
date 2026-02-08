from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    kafka_brokers: str = "localhost:9092"
    kafka_topic: str = "clawderpunk.events.v1"
    kafka_consumer_group: str = "punk-records"

    database_url: str = "postgresql://clawderpunk:clawderpunk@localhost:5432/clawderpunk"

    punk_records_api_token: str = "changeme"

    log_level: str = "INFO"

    model_config = {"env_prefix": "", "case_sensitive": False}
