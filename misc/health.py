"""
app/api/routes/health.py
─────────────────────────
Health & readiness endpoints for load balancers and monitoring.

GET /health         — lightweight liveness probe
GET /health/ready   — deep readiness: checks Redis + Ollama
GET /health/metrics — Prometheus scrape endpoint (via instrumentator)
"""

from __future__ import annotations

from datetime import datetime

import ollama
import redis.asyncio as aioredis
from fastapi import APIRouter
from loguru import logger

from app.core.config import settings
from app.core.redis_client import get_redis

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def liveness() -> dict:
    return {
        "status": "ok",
        "app":    settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/ready", summary="Readiness probe (deep check)")
async def readiness() -> dict:
    checks: dict[str, str] = {}
    healthy = True

    # Redis check
    try:
        redis_client = get_redis()
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        healthy = False
        logger.warning("Redis readiness check failed", error=str(exc))

    # Ollama check
    try:
        client = ollama.Client(host=settings.OLLAMA_HOST)
        models = client.list()
        available = [m.model for m in models.models]
        if any(settings.OLLAMA_MODEL in m for m in available):
            checks["ollama"] = f"ok ({settings.OLLAMA_MODEL})"
        else:
            checks["ollama"] = f"model '{settings.OLLAMA_MODEL}' not found; available: {available}"
            healthy = False
    except Exception as exc:
        checks["ollama"] = f"unreachable: {exc}"
        # Ollama being down is a warning, not fatal — scraper still works without LLM
        logger.warning("Ollama readiness check failed", error=str(exc))

    return {
        "status":    "ok" if healthy else "degraded",
        "checks":    checks,
        "timestamp": datetime.utcnow().isoformat(),
    }
