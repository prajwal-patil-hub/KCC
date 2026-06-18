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

    # ADR-0006: mock-first. Never silently default to real adapters.
    integration_mode: str = "mock"  # mock | sandbox | prod

    # Resilience knobs for the adapter framework.
    adapter_max_retries: int = 3
    circuit_breaker_threshold: int = 5  # consecutive failures before opening


@lru_cache
def get_settings() -> Settings:
    return Settings()
