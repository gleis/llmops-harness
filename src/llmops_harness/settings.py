"""Runtime configuration. Everything lives in env / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Providers — LiteLLM reads these from env directly, but we expose them
    # here so they can be surfaced in /health and logs.
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # Budgets
    budget_max_tokens_per_request: int = 8000
    budget_max_cost_usd_per_request: float = 0.25
    budget_max_cost_usd_per_session: float = 5.00

    # Observability
    otel_service_name: str = "llmops-harness"
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    prometheus_port: int = 9464

    # Server
    log_level: str = "INFO"


settings = Settings()
