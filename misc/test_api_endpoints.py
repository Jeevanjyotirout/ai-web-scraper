"""
tests/test_api_endpoints.py
─────────────────────────────
Integration tests for the three API endpoints.

Uses httpx.AsyncClient with fakeredis to avoid real Redis/Celery.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.core.redis_client import _client as _redis_module


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app():
    return create_app()


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def patch_redis(monkeypatch):
    """Replace the global Redis client with FakeRedis."""
    fake = FakeRedis(decode_responses=True)

    import app.core.redis_client as rc
    monkeypatch.setattr(rc, "_client", fake)
    yield fake
    await fake.aclose()


# ── POST /create-job ──────────────────────────────────────────────────────────

class TestCreateJob:
    valid_payload = {
        "url": "https://example.com",
        "instructions": "Extract all product names and prices",
        "output_format": "excel",
    }

    @pytest.mark.asyncio
    async def test_create_job_success(self, client):
        with patch("app.api.routes.jobs.run_scraping_job") as mock_task:
            mock_task.apply_async.return_value = MagicMock(id="test-celery-id")
            response = await client.post("/api/v1/create-job", json=self.valid_payload)

        assert response.status_code == 202
        body = response.json()
        assert "job_id" in body
        assert body["status"] == "pending"
        assert body["message"] != ""

    @pytest.mark.asyncio
    async def test_create_job_missing_url(self, client):
        response = await client.post(
            "/api/v1/create-job",
            json={"instructions": "Extract titles"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_job_short_instructions(self, client):
        response = await client.post(
            "/api/v1/create-job",
            json={"url": "https://example.com", "instructions": "hi"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_job_invalid_url(self, client):
        response = await client.post(
            "/api/v1/create-job",
            json={"url": "not-a-url", "instructions": "Extract all prices from page"},
        )
        assert response.status_code == 422


# ── GET /job-status ───────────────────────────────────────────────────────────

class TestJobStatus:

    @pytest.mark.asyncio
    async def test_status_not_found(self, client):
        response = await client.get(
            "/api/v1/job-status",
            params={"job_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_status_pending(self, client, patch_redis):
        job_id = "11111111-1111-1111-1111-111111111111"
        # Seed fake Redis directly
        await patch_redis.hset(f"job:{job_id}", mapping={
            "status":       "pending",
            "status_message": "Queued",
            "progress":     "0",
            "current_step": "init",
            "url":          "https://example.com",
            "instructions": "Extract titles",
            "output_format": "excel",
            "mode":         "single",
            "pages_scraped": "0",
            "rows_extracted": "0",
            "error_count":  "0",
            "retry_count":  "0",
            "created_at":   "2024-01-01T00:00:00",
            "updated_at":   "2024-01-01T00:00:00",
        })

        response = await client.get(
            "/api/v1/job-status", params={"job_id": job_id}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"
        assert body["progress"] == 0
        assert body["download_available"] is False


# ── GET /download-file ────────────────────────────────────────────────────────

class TestDownloadFile:

    @pytest.mark.asyncio
    async def test_download_not_found(self, client):
        response = await client.get(
            "/api/v1/download-file",
            params={"job_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_download_not_completed(self, client, patch_redis):
        job_id = "22222222-2222-2222-2222-222222222222"
        await patch_redis.hset(f"job:{job_id}", mapping={
            "status": "scraping",
            "url": "https://example.com",
        })
        response = await client.get(
            "/api/v1/download-file", params={"job_id": job_id}
        )
        assert response.status_code == 400


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:

    @pytest.mark.asyncio
    async def test_liveness(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
