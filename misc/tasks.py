"""
app/workers/tasks.py
─────────────────────
Celery task definitions.

Tasks are intentionally thin — they delegate to module classes.
All state mutations go through JobStore (Redis).

Main task:  run_scraping_job
  1. Validate & parse instructions
  2. Scrape target URL(s)
  3. Run AI processing
  4. Build dataset
  5. Export file
  6. Persist result metadata in Redis
"""

from __future__ import annotations

import asyncio
import os
import traceback
from datetime import datetime
from typing import Any, Dict

import redis
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger
from loguru import logger

from app.core.config import settings
from app.core.exceptions import AppBaseError
from app.modules.ai_processing import AIProcessingEngine
from app.modules.dataset_builder import DatasetBuilder
from app.modules.export_engine import ExportEngine
from app.modules.instruction_parser import InstructionParser
from app.modules.scraping_engine import ScrapingEngine
from app.workers.celery_app import celery_app

# Synchronous Redis client for use inside Celery (non-async)
_sync_redis = redis.Redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
)
_TASK_LOGGER = get_task_logger(__name__)


# ── Progress helper ───────────────────────────────────────────────────────────

def _update_job(job_id: str, **fields: Any) -> None:
    """
    Synchronously update a job's Redis hash.
    Called from inside Celery task (sync context).
    """
    import json

    key = f"job:{job_id}"
    mapping: Dict[str, str] = {}
    for k, v in fields.items():
        mapping[k] = json.dumps(v) if not isinstance(v, str) else v
    mapping["updated_at"] = datetime.utcnow().isoformat()

    try:
        _sync_redis.hset(key, mapping=mapping)
        _sync_redis.expire(key, 60 * 60 * 48)
    except redis.RedisError as exc:
        _TASK_LOGGER.warning("Failed to update Redis job", job_id=job_id, error=str(exc))


def _set_progress(job_id: str, progress: int, step: str, status: str, message: str) -> None:
    _update_job(
        job_id,
        progress=str(progress),
        current_step=step,
        status=status,
        status_message=message,
    )
    logger.info("Job progress", job_id=job_id, progress=progress, step=step)


# ── Base task with retry behaviour ────────────────────────────────────────────

class BaseTask(Task):
    abstract = True

    def on_failure(
        self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: object
    ) -> None:
        job_id = kwargs.get("job_id") or (args[0] if args else "unknown")
        _update_job(
            job_id,
            status="failed",
            status_message=str(exc)[:500],
            error=str(exc)[:1000],
            error_traceback=traceback.format_exc()[:3000],
        )
        logger.error("Task on_failure", job_id=job_id, exc=str(exc))

    def on_retry(
        self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: object
    ) -> None:
        job_id = kwargs.get("job_id") or (args[0] if args else "unknown")
        retry_count = self.request.retries
        _update_job(job_id, retry_count=str(retry_count), status_message=f"Retrying ({retry_count})")
        logger.warning("Task retrying", job_id=job_id, attempt=retry_count)


# ── Main scraping pipeline task ───────────────────────────────────────────────

@celery_app.task(
    name="app.workers.tasks.run_scraping_job",
    bind=True,
    base=BaseTask,
    max_retries=settings.CELERY_MAX_RETRIES,
    default_retry_delay=30,
    queue="scrape_jobs",
    acks_late=True,
)
def run_scraping_job(
    self: Task,
    *,
    job_id: str,
    url: str,
    instructions: str,
    structured_instructions: Any,
    output_format: str,
    mode: str,
    max_pages: int,
    max_depth: int,
) -> Dict[str, Any]:
    """
    Full end-to-end pipeline task.

    Accepts a flat dict of primitives (JSON-serialisable).
    Progress is written to Redis at each stage.
    """
    logger.info("run_scraping_job started", job_id=job_id, url=url)

    try:
        # ── Stage 1: Validate & parse instructions (2%) ────────────────────
        _set_progress(job_id, 2, "validating", "validating", "Validating instructions...")

        parser = InstructionParser()
        valid, issues = parser.validate(instructions)
        if not valid:
            raise ValueError(f"Invalid instructions: {'; '.join(issues)}")

        plan = parser.parse(instructions)
        logger.info("Instruction plan ready", job_id=job_id, fields=[f.name for f in plan.fields])

        # ── Stage 2: Scraping (5–50%) ─────────────────────────────────────
        _set_progress(job_id, 5, "scraping", "scraping", f"Launching browser for {url}...")

        async def _async_scrape():
            async with ScrapingEngine() as engine:
                async def _progress_cb(done: int, total: int) -> None:
                    pct = 5 + int((done / max(total, 1)) * 45)
                    _set_progress(
                        job_id, pct, "scraping", "scraping",
                        f"Scraped {done}/{total} pages..."
                    )

                return await engine.scrape(
                    url=url,
                    plan=plan,
                    max_pages=max_pages,
                    max_depth=max_depth,
                    progress_callback=_progress_cb,
                )

        scrape_result = asyncio.run(_async_scrape())

        _update_job(
            job_id,
            pages_scraped=str(len(scrape_result.pages)),
            error_count=str(len(scrape_result.failed_urls)),
        )

        if not scrape_result.pages:
            raise ScrapingError(f"No pages scraped from {url}")

        _set_progress(
            job_id, 52, "processing",
            "processing",
            f"Scraping done ({len(scrape_result.pages)} pages). Running AI...",
        )

        # ── Stage 3: AI processing (52–80%) ──────────────────────────────
        ai_engine = AIProcessingEngine()
        ai_result = ai_engine.process(scrape_result.pages, plan)

        _update_job(job_id, rows_extracted=str(ai_result.records.__len__()))

        if not ai_result.records:
            logger.warning("AI returned no records", job_id=job_id)

        _set_progress(
            job_id, 82, "building",
            "building",
            f"AI done ({len(ai_result.records)} records). Building dataset...",
        )

        # ── Stage 4: Dataset build (82–90%) ──────────────────────────────
        builder = DatasetBuilder()
        dataset = builder.build(
            records=ai_result.records,
            plan=plan,
            source_url=url,
            scraped_at=datetime.utcnow(),
        )

        _set_progress(
            job_id, 90, "exporting",
            "exporting",
            f"Building file ({dataset.stats.total_rows} rows)...",
        )

        # ── Stage 5: Export (90–98%) ──────────────────────────────────────
        from app.models.job import OutputFormat as OF
        fmt    = OF(output_format)
        engine = ExportEngine()
        result = engine.export(dataset, job_id, url, instructions, fmt)

        # ── Stage 6: Finalise ─────────────────────────────────────────────
        _update_job(
            job_id,
            status="completed",
            status_message="Job completed successfully",
            progress="100",
            current_step="done",
            file_path=result.file_path,
            file_name=result.file_name,
            file_size_bytes=str(result.file_size_bytes),
            rows_extracted=str(result.rows_written),
            completed_at=datetime.utcnow().isoformat(),
        )

        logger.info(
            "run_scraping_job completed",
            job_id=job_id,
            rows=result.rows_written,
            file=result.file_name,
        )

        return {
            "job_id":       job_id,
            "rows":         result.rows_written,
            "file_name":    result.file_name,
            "file_size":    result.file_size_bytes,
        }

    except SoftTimeLimitExceeded:
        _update_job(
            job_id,
            status="failed",
            status_message="Job exceeded time limit",
            error="SoftTimeLimitExceeded",
        )
        raise

    except AppBaseError as exc:
        logger.error("Domain error in task", job_id=job_id, error=str(exc))
        try:
            raise self.retry(exc=exc, countdown=30)
        except self.MaxRetriesExceededError:
            _update_job(
                job_id,
                status="failed",
                status_message=exc.message,
                error=exc.message,
            )
        raise

    except Exception as exc:
        logger.exception("Unexpected error in task", job_id=job_id)
        try:
            raise self.retry(exc=exc, countdown=60)
        except self.MaxRetriesExceededError:
            _update_job(
                job_id,
                status="failed",
                status_message=str(exc)[:500],
                error=str(exc)[:1000],
                error_traceback=traceback.format_exc()[:3000],
            )
        raise


# ── Maintenance task ──────────────────────────────────────────────────────────

@celery_app.task(name="app.workers.tasks.cleanup_old_outputs")
def cleanup_old_outputs() -> Dict[str, int]:
    """Delete export files older than FILE_TTL_HOURS from the output directory."""
    import time

    cutoff  = time.time() - (settings.FILE_TTL_HOURS * 3600)
    removed = 0
    errors  = 0

    output_dir = settings.OUTPUT_DIR
    if not os.path.isdir(output_dir):
        return {"removed": 0, "errors": 0}

    for fname in os.listdir(output_dir):
        fpath = os.path.join(output_dir, fname)
        try:
            if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                os.remove(fpath)
                removed += 1
        except OSError as exc:
            logger.warning("Could not delete old file", path=fpath, error=str(exc))
            errors += 1

    logger.info("Output cleanup done", removed=removed, errors=errors)
    return {"removed": removed, "errors": errors}


# ── Import guard ──────────────────────────────────────────────────────────────
from app.core.exceptions import ScrapingError  # noqa: E402 (used in task body)
