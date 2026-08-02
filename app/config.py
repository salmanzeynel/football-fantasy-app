from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TEMPLATE_DIR = DATA_DIR / "templates"
INBOX_DIR = DATA_DIR / "inbox"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{BASE_DIR / 'fantasy.db'}"
    secret_key: str = "dev-only-insecure-key"
    debug: bool = True
    timezone: str = "Europe/Istanbul"


@lru_cache
def get_settings() -> Settings:
    return Settings()
