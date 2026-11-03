from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Values come from env vars or `.env`. See `/.env.example`."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_path: Path = Path("data/portfolio.db")
    cors_origin: str = "http://localhost:4321"


@lru_cache
def get_settings() -> Settings:
    return Settings()
