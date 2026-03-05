import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.models.schemas import JobStatus
from app.utils.job_manager import job_manager
from loguru import logger

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/{job_id}")
async def download_export(job_id: str):
    """Download the exported file for a completed job."""
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed yet (status: {job.status})"
        )

    if not job.file_path or not os.path.exists(job.file_path):
        raise HTTPException(status_code=404, detail="Export file not found on server")

    filename = os.path.basename(job.file_path)
    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if filename.endswith(".xlsx")
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    logger.info(f"Serving export for job {job_id}: {filename}")

    return FileResponse(
        path=job.file_path,
        filename=filename,
        media_type=media_type,
    )


@router.get("/{job_id}/metadata")
async def get_export_metadata(job_id: str):
    """Get metadata about the exported file."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job not completed")

    return {
        "job_id": job.job_id,
        "filename": os.path.basename(job.file_path) if job.file_path else None,
        "format": job.output_format,
        "rows": job.rows_extracted,
        "file_size_bytes": job.file_size_bytes,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
