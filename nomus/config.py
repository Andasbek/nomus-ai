"""Конфигурация из переменных окружения (Приложение Б ТЗ)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "nomus_kz_legal_v1"
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    retrieval_top_k: int = 20
    rerank_top_k: int = 5
    relevance_threshold: float = 0.35
    db_path: str = "./data/nomus.db"
    log_level: str = "INFO"

    # Веб-часть
    bot_username: str = "nomus_law_bot"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "*"
    rate_limit_per_hour: int = 30
    # Включать, только если сервис реально стоит за прокси (cloudflared, nginx):
    # иначе клиент подделает X-Forwarded-For и обойдёт rate limit.
    trusted_proxy: bool = False

    @property
    def bot_url(self) -> str:
        return f"https://t.me/{self.bot_username}"


settings = Settings()
