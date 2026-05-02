from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "peer_learning"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:latest"
    ollama_timeout: int = 120
    redis_url: str = "redis://localhost:6379"
    app_secret_key: str = "change-me-in-production"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False
    notification_ttl_seconds: int = 60
    waiting_queue_poll_interval: int = 10
    compatibility_threshold: int = 60
    mastery_threshold: int = 90
    group_session_mastery_threshold: int = 90
    verification_consecutive_sessions: int = 3
    improved_pool_group_trigger: int = 3

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
