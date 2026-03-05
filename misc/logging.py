"""
app/core/logging.py
────────────────────
Structured logging with Loguru.

Features:
- Console output with colour formatting
- Rotating file output (JSON for production, human-readable for dev)
- Per-request correlation IDs
- Celery task logging integration
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Optional

from loguru import logger

from app.core.config import settings

# ── Correlation ID context var (set per-request in middleware) ────────────────
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


# ── Intercept stdlib logging so third-party libs flow through Loguru ──────────
class _InterceptHandler(logging.Handler):
    """Route all stdlib log records into Loguru."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno  # type: ignore[assignment]

        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _correlation_id_patcher(record: dict) -> None:
    """Inject the current request/task correlation ID into every log record."""
    record["extra"]["request_id"] = request_id_var.get() or "—"


def setup_logging() -> None:
    """Configure Loguru for the entire application. Call once at startup."""

    logger.remove()  # Remove default sink

    # ── Console sink ─────────────────────────────────────────────────────────
    console_fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
        "| <level>{level: <8}</level> "
        "| <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
        "| <dim>rid={extra[request_id]}</dim> "
        "— <level>{message}</level>"
    )
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format=console_fmt,
        colorize=True,
        backtrace=settings.DEBUG,
        diagnose=settings.DEBUG,
        patch=_correlation_id_patcher,
    )

    # ── Rotating file sink ────────────────────────────────────────────────────
    file_fmt = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} "
        "| {level: <8} "
        "| {name}:{function}:{line} "
        "| rid={extra[request_id]} "
        "— {message}"
    )
    logger.add(
        f"{settings.LOG_DIR}/app.log",
        level=settings.LOG_LEVEL,
        format=file_fmt,
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        compression="zip",
        backtrace=True,
        diagnose=True,
        enqueue=True,                # Thread-safe async writes
        patch=_correlation_id_patcher,
    )

    # ── Error-only file sink ──────────────────────────────────────────────────
    logger.add(
        f"{settings.LOG_DIR}/errors.log",
        level="ERROR",
        format=file_fmt,
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        compression="zip",
        backtrace=True,
        diagnose=True,
        enqueue=True,
        patch=_correlation_id_patcher,
    )

    # ── Route stdlib → Loguru ─────────────────────────────────────────────────
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "celery"):
        logging.getLogger(name).handlers = [_InterceptHandler()]
        logging.getLogger(name).propagate = False

    logger.info(
        "Logging configured",
        env=settings.APP_ENV,
        level=settings.LOG_LEVEL,
    )


# Re-export for convenience
__all__ = ["logger", "setup_logging", "request_id_var"]
