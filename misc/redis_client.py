"""
app/core/redis_client.py
─────────────────────────
Async Redis client for job metadata storage.

Uses redis.asyncio for non-blocking operations inside FastAPI.
Provides a typed wrapper around common job-state operations.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import redis.asyncio as aioredis
from loguru import logger

from app.core.config import settings

# ── Module-level pool (initialised in lifespan) ───────────────────────────────
_pool: Optional[aioredis.ConnectionPool] = None
_client: Optional[aioredis.Redis] = None


async def init_redis() -> None:
    """Create the connection pool. Called once during app startup."""
    global _pool, _client

    _pool = aioredis.ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        decode_responses=True,
    )
    _client = aioredis.Redis(connection_pool=_pool)

    # Verify connectivity
    await _client.ping()
    logger.info("Redis connection pool initialised", url=settings.REDIS_URL)


async def close_redis() -> None:
    """Drain the pool. Called during app shutdown."""
    global _pool, _client
    if _client:
        await _client.aclose()
    if _pool:
        await _pool.aclose()
    logger.info("Redis connection pool closed")


def get_redis() -> aioredis.Redis:
    """Return the shared client. Raises if not yet initialised."""
    if _client is None:
        raise RuntimeError("Redis not initialised — call init_redis() first")
    return _client


# ── Key schema ────────────────────────────────────────────────────────────────
_JOB_KEY = "job:{job_id}"
_JOB_TTL = 60 * 60 * 48   # 48 hours


class JobStore:
    """
    Typed helpers for reading/writing job metadata in Redis.

    Each job is stored as a Redis Hash under key  job:<job_id>.
    """

    def __init__(self, client: Optional[aioredis.Redis] = None) -> None:
        self._client = client or get_redis()

    def _key(self, job_id: str) -> str:
        return _JOB_KEY.format(job_id=job_id)

    # ── Write ─────────────────────────────────────────────────────────────────

    async def create(self, job_id: str, data: Dict[str, Any]) -> None:
        """Persist initial job data and set a TTL."""
        key = self._key(job_id)
        # Serialise nested objects as JSON strings
        serialised = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in data.items()}
        await self._client.hset(key, mapping=serialised)
        await self._client.expire(key, _JOB_TTL)
        logger.debug("Job created in Redis", job_id=job_id)

    async def update(self, job_id: str, fields: Dict[str, Any]) -> None:
        """Partial update — only touches the provided fields."""
        key = self._key(job_id)
        serialised = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in fields.items()}
        await self._client.hset(key, mapping=serialised)
        # Reset TTL on every meaningful update
        await self._client.expire(key, _JOB_TTL)

    async def set_status(self, job_id: str, status: str, message: str = "") -> None:
        await self.update(
            job_id,
            {
                "status": status,
                "status_message": message,
                "updated_at": datetime.utcnow().isoformat(),
            },
        )

    async def set_progress(self, job_id: str, progress: int, step: str) -> None:
        await self.update(job_id, {"progress": str(progress), "current_step": step})

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Return all fields or None if key not found."""
        key = self._key(job_id)
        raw: Dict[str, str] = await self._client.hgetall(key)
        if not raw:
            return None

        result: Dict[str, Any] = {}
        for k, v in raw.items():
            try:
                result[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                result[k] = v
        return result

    async def exists(self, job_id: str) -> bool:
        return bool(await self._client.exists(self._key(job_id)))

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete(self, job_id: str) -> None:
        await self._client.delete(self._key(job_id))
        logger.debug("Job deleted from Redis", job_id=job_id)
