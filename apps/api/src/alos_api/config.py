"""Application settings.

Integrations default to MOCK mode (ADR-0006) so the whole flow runs with zero
real external access in dev and CI.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ALOS_", extra="ignore")

    app_name: str = "ALOS API"
    environment: str = "dev"  # dev | staging | prod

    # Storage backend for the event + audit stores. "memory" is the default for
    # dev/CI; "postgres" enables the RLS-backed durable stores (ADR-0002/0003).
    storage: str = "memory"  # memory | postgres
    database_url: str = "postgresql://alos_app:alos_pw@127.0.0.1:5432/alos"

    # ADR-0006: mock-first. Never silently default to real adapters.
    integration_mode: str = "mock"  # mock | sandbox | prod

    # AI provider for the Credit-Memo agent. Default "none" = no AI running, so
    # the agent falls back to a deterministic template memo (set "mock" to demo
    # the AI path, or a real provider name in production).
    llm_provider: str = "none"  # none | mock | openai | anthropic

    # Resilience knobs for the adapter framework.
    adapter_max_retries: int = 3
    circuit_breaker_threshold: int = 5  # consecutive failures before opening


@lru_cache
def get_settings() -> Settings:
    return Settings()
