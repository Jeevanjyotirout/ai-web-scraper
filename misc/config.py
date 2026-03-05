"""
app/core/config.py
──────────────────
Central configuration management via Pydantic Settings.
All values are read from environment variables or .env file.
"""

from __future__ import annotations

import os
from typing import List
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str = "AI Scraper Backend"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str = "please-change-me-in-production"

    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 20
    REDIS_SOCKET_TIMEOUT: int = 5

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_MAX_RETRIES: int = 3
    CELERY_TASK_SOFT_TIME_LIMIT: int = 600
    CELERY_TASK_TIME_LIMIT: int = 700

    # ── Scraping ──────────────────────────────────────────────────────────────
    SCRAPE_MAX_PAGES: int = 50
    SCRAPE_MAX_DEPTH: int = 3
    SCRAPE_TIMEOUT: int = 30
    SCRAPE_CONCURRENCY: int = 5
    SCRAPE_DELAY_MIN: float = 0.5
    SCRAPE_DELAY_MAX: float = 2.0
    SCRAPE_BROWSER_HEADLESS: bool = True
    SCRAPE_RESPECT_ROBOTS: bool = True

    # ── AI ────────────────────────────────────────────────────────────────────
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "tinyllama"
    OLLAMA_TIMEOUT: int = 120
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    FAISS_TOP_K: int = 25

    # ── Export ────────────────────────────────────────────────────────────────
    OUTPUT_DIR: str = "./outputs"
    MAX_ROWS_EXCEL: int = 50000
    MAX_ROWS_WORD: int = 1000
    FILE_TTL_HOURS: int = 24

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "./logs"
    LOG_ROTATION: str = "50 MB"
    LOG_RETENTION: str = "14 days"

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # ── Derived Properties ────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @model_validator(mode="after")
    def _create_directories(self) -> "Settings":
        """Ensure required directories exist at startup."""
        for directory in [self.OUTPUT_DIR, self.LOG_DIR]:
            os.makedirs(directory, exist_ok=True)
        return self

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}")
        return v.upper()


# Singleton — import this everywhere
settings = Settings()
