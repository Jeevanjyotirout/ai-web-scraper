from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.models.schemas import ScrapeRequest, JobCreatedResponse, JobStatus
from app.utils.job_manager import job_manager
from app.services.pipeline import ScrapingPipeline
from app.core.config import settings
from datetime import datetime
from loguru import logger

router = APIRouter(prefix="/api", tags=["scrape"])
_pipeline = ScrapingPipeline()


@router.post("/scrape", response_model=JobCreatedResponse)
async def start_scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """Start a new scraping job."""
    # Check active job count
    active = sum(
        1 for j in job_manager.list_jobs()
        if j.status in (JobStatus.PENDING, JobStatus.SCRAPING, JobStatus.PROCESSING, JobStatus.EXPORTING)
    )
    if active >= settings.MAX_CONCURRENT_JOBS:
        raise HTTPException(
            status_code=429,
            detail=f"Too many active jobs ({active}/{settings.MAX_CONCURRENT_JOBS}). Try again shortly."
        )

    job = job_manager.create_job(
        url=request.url,
        instructions=request.instructions,
        output_format=request.output_format,
    )

    # Start job asynchronously
    await job_manager.run_job(
        job=job,
        worker=_pipeline.run,
        max_concurrent=settings.MAX_CONCURRENT_JOBS,
    )

    logger.info(f"Scrape job started: {job.job_id} → {request.url}")

    return JobCreatedResponse(
        job_id=job.job_id,
        status=job.status,
        message="Job started successfully",
        created_at=job.created_at,
    )
