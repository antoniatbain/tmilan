from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    test_database_url: str | None = None

    llm_model: str = "claude-opus-5"
    llm_timeout_seconds: float = 120.0
    llm_max_attempts: int = 2
    llm_max_turns: int = 3
    anthropic_api_key: SecretStr | None = None

    max_transcript_chars: int = 200_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
