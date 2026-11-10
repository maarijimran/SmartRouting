from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./smartroute.db"
    jwt_secret: str = "development-only-change-me"
    key_vault_master_key: str = ""
    ollama_url: str = "http://localhost:11434"
    frontend_origin: str = "http://localhost:3000"
    admin_email: str = ""
    privacy_gate_required: bool = True
    # When true every model (local and cloud) is served by the deterministic fake
    # adapter. Used by tests, CI and the laptop demo; never contacts any provider.
    fake_providers: bool = False
    # Connection test and cloud calls give up after this many seconds.
    provider_timeout_s: float = 60.0
    # Per-user limits (requests per minute) for the expensive endpoints.
    chat_rate_per_min: int = 30
    upload_rate_per_min: int = 20

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
