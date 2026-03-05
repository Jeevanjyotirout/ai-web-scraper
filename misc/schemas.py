from pydantic import BaseModel, HttpUrl, field_validator
from typing import Literal, Optional, Any
from datetime import datetime
from enum import Enum


class OutputFormat(str, Enum):
    EXCEL = "excel"
    WORD = "word"


class JobStatus(str, Enum):
    PENDING = "pending"
    SCRAPING = "scraping"
    PROCESSING = "processing"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── Requests ──────────────────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    url: str
    instructions: str
    output_format: OutputFormat = OutputFormat.EXCEL
    max_pages: int = 1

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v.strip()

    @field_validator("instructions")
    @classmethod
    def validate_instructions(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("Instructions must be at least 10 characters")
        return v.strip()

    @field_validator("max_pages")
    @classmethod
    def validate_max_pages(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("max_pages must be between 1 and 10")
        return v


# ── Responses ─────────────────────────────────────────────────────────────────

class JobCreatedResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str
    created_at: datetime


class ProgressEvent(BaseModel):
    job_id: str
    status: JobStatus
    progress: int          # 0–100
    message: str
    step: str
    data: Optional[Any] = None
    error: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int
    message: str
    url: str
    instructions: str
    output_format: OutputFormat
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    rows_extracted: Optional[int] = None
    file_size_bytes: Optional[int] = None


class ExportMetadata(BaseModel):
    job_id: str
    filename: str
    format: OutputFormat
    rows: int
    file_size_bytes: int
    created_at: datetime
