"""
app/api/routes/jobs.py
───────────────────────
Three core REST endpoints:

  POST /create-job      — Validate request, persist job, dispatch Celery task
  GET  /job-status      — Return real-time job state from Redis
  GET  /download-file   — Stream the exported file to the client
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from loguru import logger

from app.core.config import settings
from app.core.exceptions import (
    JobNotFoundError,
    JobQueueFullError,
)
from app.core.redis_client import JobStore, get_redis
from app.models.job import (
    DownloadMetadata,
    Job,
    JobCreateRequest,
    JobCreateResponse,
    JobStatus,
    JobStatusResponse,
    OutputFormat,
    ScrapeMode,
)
from app.workers.tasks import run_scraping_job

router = APIRouter(prefix="/api/v1", tags=["jobs"])


# ── Dependency ────────────────────────────────────────────────────────────────

def get_job_store() -> JobStore:
    return JobStore(get_redis())


# ── Helper: queue depth guard ─────────────────────────────────────────────────

_MAX_QUEUE_DEPTH = 50  # Soft cap on total active jobs


async def _check_queue_capacity(store: JobStore) -> None:
    """Raise if too many jobs are already running."""
    # We do a lightweight scan of active job keys
    redis_client = get_redis()
    active_keys  = await redis_client.keys("job:*")
    if len(active_keys) >= _MAX_QUEUE_DEPTH:
        raise JobQueueFullError(
            f"Queue is full ({len(active_keys)}/{_MAX_QUEUE_DEPTH} active jobs). "
            "Please try again later.",
        )


# ── POST /create-job ──────────────────────────────────────────────────────────

@router.post(
    "/create-job",
    response_model=JobCreateResponse,
    status_code=202,
    summary="Create a new scraping job",
    description=(
        "Validates the request, persists the job to Redis, and dispatches "
        "a Celery task. Returns immediately with the job ID."
    ),
)
async def create_job(
    body: JobCreateRequest,
    store: JobStore = Depends(get_job_store),
) -> JobCreateResponse:

    await _check_queue_capacity(store)

    # Resolve max_pages / max_depth
    max_pages = body.max_pages or (1 if body.mode == ScrapeMode.SINGLE else settings.SCRAPE_MAX_PAGES)
    max_depth = body.max_depth or (1 if body.mode == ScrapeMode.SINGLE else settings.SCRAPE_MAX_DEPTH)

    # Build internal Job object
    job = Job(
        url                    = body.url,
        instructions           = body.instructions,
        structured_instructions = body.structured_instructions,
        output_format          = body.output_format,
        mode                   = body.mode,
        max_pages              = max_pages,
        max_depth              = max_depth,
        tags                   = body.tags,
        webhook_url            = body.webhook_url,
    )

    # Persist to Redis (status = pending)
    await store.create(job.job_id, job.model_dump(mode="json"))
    logger.info("Job created", job_id=job.job_id, url=body.url)

    # Dispatch Celery task
    celery_task = run_scraping_job.apply_async(
        kwargs={
            "job_id":                   job.job_id,
            "url":                      job.url,
            "instructions":             job.instructions,
            "structured_instructions":  [
                si.model_dump() for si in (job.structured_instructions or [])
            ],
            "output_format":            job.output_format.value,
            "mode":                     job.mode.value,
            "max_pages":                job.max_pages,
            "max_depth":                job.max_depth,
        },
        task_id=job.job_id,         # Reuse job_id as Celery task ID
        queue="scrape_jobs",
    )

    # Store Celery task ID back into Redis
    await store.update(job.job_id, {"celery_task_id": celery_task.id})

    # Rough duration estimate: ~30s per page + 15s AI overhead
    estimated = (job.max_pages * 30) + 15

    return JobCreateResponse(
        job_id=job.job_id,
        status=JobStatus.PENDING,
        message="Job accepted and queued for processing",
        created_at=job.created_at,
        estimated_duration_seconds=estimated,
    )


# ── GET /job-status ───────────────────────────────────────────────────────────

@router.get(
    "/job-status",
    response_model=JobStatusResponse,
    summary="Get the current status of a scraping job",
)
async def get_job_status(
    job_id: str = Query(..., min_length=36, max_length=36, description="Job UUID"),
    store:  JobStore = Depends(get_job_store),
) -> JobStatusResponse:

    data = await store.get(job_id)
    if data is None:
        raise JobNotFoundError(f"Job '{job_id}' not found")

    status        = JobStatus(data.get("status", "pending"))
    is_completed  = status == JobStatus.COMPLETED

    return JobStatusResponse(
        job_id           = job_id,
        url              = data.get("url", ""),
        status           = status,
        status_message   = data.get("status_message", ""),
        progress         = int(data.get("progress", 0)),
        current_step     = data.get("current_step", "init"),
        output_format    = OutputFormat(data.get("output_format", "excel")),
        mode             = ScrapeMode(data.get("mode", "single")),
        pages_scraped    = int(data.get("pages_scraped", 0)),
        rows_extracted   = int(data.get("rows_extracted", 0)),
        error_count      = int(data.get("error_count", 0)),
        retry_count      = int(data.get("retry_count", 0)),
        created_at       = _parse_dt(data.get("created_at")),
        updated_at       = _parse_dt(data.get("updated_at")),
        completed_at     = _parse_dt(data.get("completed_at")) if is_completed else None,
        error            = data.get("error"),
        download_available = is_completed and bool(data.get("file_path")),
        file_name        = data.get("file_name") if is_completed else None,
        file_size_bytes  = int(data.get("file_size_bytes", 0)) if is_completed else None,
    )


# ── GET /download-file ────────────────────────────────────────────────────────

@router.get(
    "/download-file",
    summary="Download the exported dataset file",
    response_description="Binary file stream",
)
async def download_file(
    job_id: str = Query(..., min_length=36, max_length=36, description="Job UUID"),
    store:  JobStore = Depends(get_job_store),
) -> FileResponse:

    data = await store.get(job_id)
    if data is None:
        raise JobNotFoundError(f"Job '{job_id}' not found")

    status = JobStatus(data.get("status", "pending"))
    if status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed yet (current status: {status.value}). "
                   "Poll /job-status until status is 'completed'.",
        )

    file_path = data.get("file_path")
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(
            status_code=404,
            detail="Export file not found on server. It may have expired.",
        )

    file_name = data.get("file_name", os.path.basename(file_path))
    media_type = _media_type_for(file_name)

    logger.info("File download requested", job_id=job_id, file=file_name)

    return FileResponse(
        path=file_path,
        filename=file_name,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "X-Job-ID":            job_id,
        },
    )


# ── GET /download-file/metadata ───────────────────────────────────────────────

@router.get(
    "/download-file/metadata",
    response_model=DownloadMetadata,
    summary="Get export file metadata without downloading",
)
async def get_download_metadata(
    job_id: str = Query(..., min_length=36, max_length=36),
    store:  JobStore = Depends(get_job_store),
) -> DownloadMetadata:

    data = await store.get(job_id)
    if data is None:
        raise JobNotFoundError(f"Job '{job_id}' not found")

    if JobStatus(data.get("status", "pending")) != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job not completed yet")

    return DownloadMetadata(
        job_id          = job_id,
        file_name       = data.get("file_name", ""),
        file_size_bytes = int(data.get("file_size_bytes", 0)),
        output_format   = OutputFormat(data.get("output_format", "excel")),
        rows_extracted  = int(data.get("rows_extracted", 0)),
        completed_at    = _parse_dt(data.get("completed_at")),
    )


# ── DELETE /job ───────────────────────────────────────────────────────────────

@router.delete(
    "/job",
    status_code=204,
    summary="Cancel and delete a job",
)
async def delete_job(
    job_id: str = Query(..., min_length=36, max_length=36),
    store:  JobStore = Depends(get_job_store),
) -> None:

    exists = await store.exists(job_id)
    if not exists:
        raise JobNotFoundError(f"Job '{job_id}' not found")

    # Best-effort: revoke the Celery task
    from app.workers.celery_app import celery_app as _celery
    _celery.control.revoke(job_id, terminate=True)

    await store.delete(job_id)
    logger.info("Job deleted", job_id=job_id)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _parse_dt(value: Optional[str]) -> datetime:
    if not value:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return datetime.utcnow()


def _media_type_for(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    return {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "csv":  "text/csv",
        "json": "application/json",
    }.get(ext, "application/octet-stream")
