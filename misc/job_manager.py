import asyncio
import uuid
from datetime import datetime
from typing import Dict, Optional, Callable, AsyncIterator
from app.models.schemas import JobStatus, OutputFormat, ProgressEvent
from loguru import logger


class Job:
    def __init__(self, job_id: str, url: str, instructions: str, output_format: OutputFormat):
        self.job_id = job_id
        self.url = url
        self.instructions = instructions
        self.output_format = output_format
        self.status = JobStatus.PENDING
        self.progress = 0
        self.message = "Job queued"
        self.step = "init"
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.completed_at: Optional[datetime] = None
        self.error: Optional[str] = None
        self.rows_extracted: Optional[int] = None
        self.file_path: Optional[str] = None
        self.file_size_bytes: Optional[int] = None
        self._subscribers: list[asyncio.Queue] = []
        self._task: Optional[asyncio.Task] = None

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subscribers.discard(q) if hasattr(self._subscribers, 'discard') else None
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def emit(self, status: JobStatus, progress: int, message: str, step: str, **kwargs):
        self.status = status
        self.progress = progress
        self.message = message
        self.step = step
        self.updated_at = datetime.utcnow()

        event = ProgressEvent(
            job_id=self.job_id,
            status=status,
            progress=progress,
            message=message,
            step=step,
            **kwargs,
        )
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def stream_events(self) -> AsyncIterator[ProgressEvent]:
        q = self.subscribe()
        try:
            # Send current state immediately
            yield ProgressEvent(
                job_id=self.job_id,
                status=self.status,
                progress=self.progress,
                message=self.message,
                step=self.step,
            )
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield event
                    if event.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                        break
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ProgressEvent(
                        job_id=self.job_id,
                        status=self.status,
                        progress=self.progress,
                        message=self.message,
                        step="keepalive",
                    )
        finally:
            self.unsubscribe(q)


class JobManager:
    """In-memory job registry (swap for Redis in production)."""

    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._semaphore: Optional[asyncio.Semaphore] = None

    def _get_semaphore(self, max_concurrent: int) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(max_concurrent)
        return self._semaphore

    def create_job(self, url: str, instructions: str, output_format: OutputFormat) -> Job:
        job_id = str(uuid.uuid4())
        job = Job(job_id, url, instructions, output_format)
        self._jobs[job_id] = job
        logger.info(f"Job created: {job_id}")
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        return list(self._jobs.values())

    def delete_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        if job._task and not job._task.done():
            job._task.cancel()
        del self._jobs[job_id]
        return True

    async def run_job(self, job: Job, worker: Callable, max_concurrent: int = 3):
        sem = self._get_semaphore(max_concurrent)
        
        async def _run():
            async with sem:
                try:
                    await worker(job)
                except asyncio.CancelledError:
                    await job.emit(JobStatus.CANCELLED, job.progress, "Job cancelled", "cancelled")
                    logger.info(f"Job cancelled: {job.job_id}")
                except Exception as e:
                    logger.exception(f"Job failed: {job.job_id}")
                    job.error = str(e)
                    await job.emit(JobStatus.FAILED, job.progress, f"Job failed: {str(e)}", "error", error=str(e))

        job._task = asyncio.create_task(_run())


# Singleton
job_manager = JobManager()
