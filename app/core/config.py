from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    env: str = "prod"
    debug: bool = False
    log_level: str = "INFO"
    origins: str = "localhost"
    database_url: str = "sqlite+aiosqlite:///db.sqlite3"
    redis_url: str = "memory://"
    sentry_dsn: str = ""
    ratelimit_enabled: bool = True
    ratelimit_guest: str = "6/minute"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings():
    return Settings()


# Instantiate settings for easy import elsewhere
settings = get_settings()
