"""Application configuration using pydantic-settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Inventory Management API"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = (
        "A production-style REST API for inventory management built with "
        "FastAPI, SQLite, and JWT authentication."
    )
    DATABASE_URL: str = "sqlite:///./inventory.db"
    SECRET_KEY: str = "a9f8d7e6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
