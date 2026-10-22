"""Конфигурация приложения. Все параметры задаются переменными окружения (12-factor)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Alfa Smart Credit Cabinet"
    environment: str = "local"

    database_url: str = "sqlite:///./local.db"

    # Подпись JWT. В проде берётся из secret storage (Vault / K8s Secret).
    jwt_secret: str = "change-me-in-production-please-32b"
    jwt_ttl_minutes: int = 12 * 60

    # Внешние сервисы (в демо — локальные моки в отдельном контейнере)
    egrul_url: str = "http://localhost:8090/egrul"
    fns_url: str = "http://localhost:8090/fns"
    bki_url: str = "http://localhost:8090/bki"
    integration_timeout_s: float = 2.0
    integration_retries: int = 3

    # Конвейер
    pipeline_step_delay_s: float = 2.5
    run_worker_in_process: bool = False
    worker_poll_interval_s: float = 1.0
    # Лимит автоматического решения: выше — только андеррайтер
    auto_decision_limit: int = 10_000_000

    # LLM (только open-weights модели, локально через Ollama)
    llm_enabled: bool = False
    llm_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:3b"
    llm_timeout_s: float = 45.0

    storage_dir: str = "./storage"
    max_upload_mb: int = 10
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    seed_demo_data: bool = True
    # Однокомпонентный запуск (публичное демо): API сам отдаёт собранный фронтенд из этой папки
    static_dir: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
