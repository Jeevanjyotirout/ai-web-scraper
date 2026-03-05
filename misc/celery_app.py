"""
app/workers/celery_app.py
──────────────────────────
Celery application factory and configuration.

Broker  : Redis (CELERY_BROKER_URL)
Backend : Redis (CELERY_RESULT_BACKEND)

Queue layout:
    scrape_jobs   — main scraping pipeline (high concurrency)
    export_jobs   — export-only tasks (low concurrency, I/O bound)
    default       — everything else
"""

from __future__ import annotations

from celery import Celery
from celery.signals import task_failure, task_postrun, task_prerun, worker_ready
from loguru import logger

from app.core.config import settings
from app.core.logging import setup_logging


def create_celery_app() -> Celery:
    app = Celery(
        "ai_scraper",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=["app.workers.tasks"],
    )

    app.conf.update(
        # Serialisation
        task_serializer        = settings.CELERY_TASK_SERIALIZER,
        accept_content         = ["json"],
        result_serializer      = "json",
        # Timezone
        timezone               = "UTC",
        enable_utc             = True,
        # Timeouts
        task_soft_time_limit   = settings.CELERY_TASK_SOFT_TIME_LIMIT,
        task_time_limit        = settings.CELERY_TASK_TIME_LIMIT,
        # Retry
        task_max_retries       = settings.CELERY_MAX_RETRIES,
        task_acks_late         = True,       # Ack after execution, not pickup
        task_reject_on_worker_lost = True,   # Re-queue if worker crashes
        # Result persistence
        result_expires         = 60 * 60 * 48,   # 48 hours
        # Worker
        worker_prefetch_multiplier = 1,      # Fair dispatch for long tasks
        # Queue routing
        task_routes = {
            "app.workers.tasks.run_scraping_job": {"queue": "scrape_jobs"},
            "app.workers.tasks.run_export_only":  {"queue": "export_jobs"},
        },
        task_default_queue = "default",
        # Beat schedule (optional background cleanup)
        beat_schedule = {
            "cleanup-old-outputs": {
                "task":     "app.workers.tasks.cleanup_old_outputs",
                "schedule": 60 * 60,    # Every hour
            },
        },
    )

    return app


celery_app = create_celery_app()


# ── Celery signal hooks ────────────────────────────────────────────────────────

@worker_ready.connect
def on_worker_ready(**kwargs: object) -> None:
    setup_logging()
    logger.info("Celery worker ready", broker=settings.CELERY_BROKER_URL)


@task_prerun.connect
def on_task_prerun(task_id: str, task: object, **kwargs: object) -> None:
    logger.info("Task started", task_id=task_id, task_name=getattr(task, "name", "?"))


@task_postrun.connect
def on_task_postrun(task_id: str, task: object, retval: object, state: str, **kwargs: object) -> None:
    logger.info("Task finished", task_id=task_id, state=state)


@task_failure.connect
def on_task_failure(
    task_id: str, exception: Exception, traceback: object, **kwargs: object
) -> None:
    logger.error("Task failed", task_id=task_id, exception=str(exception))
