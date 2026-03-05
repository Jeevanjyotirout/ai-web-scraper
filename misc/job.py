"""
app/models/job.py
──────────────────
All Pydantic models that represent a scraping job throughout its lifecycle.

Separation of concerns:
  JobCreateRequest  — what the API consumer sends
  Job               — full internal representation
  JobStatusResponse — what GET /job-status returns
  DownloadResponse  — what GET /download-file returns
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


# ── Enumerations ──────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    PENDING    = "pending"
    VALIDATING = "validating"
    SCRAPING   = "scraping"
    PARSING    = "parsing"
    PROCESSING = "processing"
    BUILDING   = "building"
    EXPORTING  = "exporting"
    COMPLETED  = "completed"
    FAILED     = "failed"
    CANCELLED  = "cancelled"


class OutputFormat(str, Enum):
    EXCEL    = "excel"
    WORD     = "word"
    CSV      = "csv"
    JSON     = "json"


class ScrapeMode(str, Enum):
    SINGLE   = "single"     # One page only
    CRAWL    = "crawl"      # Follow internal links
    SITEMAP  = "sitemap"    # Parse sitemap.xml first


# ── Request models ────────────────────────────────────────────────────────────

class ScrapingInstruction(BaseModel):
    """
    A single extraction rule inside a job request.

    Example:
        {"field": "price", "selector": ".product-price", "type": "text"}
    """

    field: str = Field(..., min_length=1, max_length=64, description="Output column / key name")
    selector: Optional[str] = Field(None, description="CSS selector (optional if relying on AI)")
    xpath: Optional[str] = Field(None, description="XPath expression (alternative to CSS)")
    description: Optional[str] = Field(None, max_length=256, description="Natural-language hint for the AI")
    type: str = Field("text", description="Value type: text | href | src | html | number | date")
    required: bool = Field(False, description="Raise an error if this field cannot be found")
    transform: Optional[str] = Field(None, description="Post-extraction transform: strip | lower | upper | int | float")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"text", "href", "src", "html", "number", "date", "bool"}
        if v not in allowed:
            raise ValueError(f"type must be one of {allowed}")
        return v


class JobCreateRequest(BaseModel):
    """Payload for POST /create-job."""

    url: str = Field(..., description="Target website URL")
    instructions: str = Field(
        ...,
        min_length=10,
        max_length=4096,
        description="Natural-language description of what to extract",
    )
    structured_instructions: Optional[List[ScrapingInstruction]] = Field(
        None,
        description="Optional explicit field-level extraction rules",
    )
    output_format: OutputFormat = Field(OutputFormat.EXCEL, description="Export file format")
    mode: ScrapeMode = Field(ScrapeMode.SINGLE, description="Scraping strategy")
    max_pages: Optional[int] = Field(None, ge=1, le=100, description="Override default max pages")
    max_depth: Optional[int] = Field(None, ge=1, le=5, description="Override crawl depth")
    tags: Optional[List[str]] = Field(None, max_length=10, description="Optional job labels")
    webhook_url: Optional[str] = Field(None, description="POST callback when job completes")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    @field_validator("instructions")
    @classmethod
    def validate_instructions(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Instructions must be at least 10 characters")
        return v

    @model_validator(mode="after")
    def validate_max_pages_mode(self) -> "JobCreateRequest":
        if self.mode == ScrapeMode.SINGLE and self.max_pages and self.max_pages > 1:
            raise ValueError("max_pages > 1 requires mode='crawl' or mode='sitemap'")
        return self


# ── Internal job model ────────────────────────────────────────────────────────

class Job(BaseModel):
    """Full internal representation stored in Redis."""

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    instructions: str
    structured_instructions: Optional[List[ScrapingInstruction]] = None
    output_format: OutputFormat = OutputFormat.EXCEL
    mode: ScrapeMode = ScrapeMode.SINGLE
    max_pages: int = 1
    max_depth: int = 1
    tags: Optional[List[str]] = None
    webhook_url: Optional[str] = None

    # Runtime state
    status: JobStatus = JobStatus.PENDING
    status_message: str = "Job queued and waiting for a worker"
    progress: int = Field(0, ge=0, le=100)
    current_step: str = "init"
    celery_task_id: Optional[str] = None

    # Metrics
    pages_scraped: int = 0
    rows_extracted: int = 0
    error_count: int = 0
    retry_count: int = 0

    # File info (populated when status == COMPLETED)
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    file_size_bytes: Optional[int] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    # Error info
    error: Optional[str] = None
    error_traceback: Optional[str] = None


# ── API response models ───────────────────────────────────────────────────────

class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str
    created_at: datetime
    estimated_duration_seconds: Optional[int] = None


class JobStatusResponse(BaseModel):
    job_id: str
    url: str
    status: JobStatus
    status_message: str
    progress: int
    current_step: str
    output_format: OutputFormat
    mode: ScrapeMode

    # Metrics
    pages_scraped: int
    rows_extracted: int
    error_count: int
    retry_count: int

    # Timestamps
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    # Error
    error: Optional[str] = None

    # Download info (only when completed)
    download_available: bool = False
    file_name: Optional[str] = None
    file_size_bytes: Optional[int] = None


class DownloadMetadata(BaseModel):
    job_id: str
    file_name: str
    file_size_bytes: int
    output_format: OutputFormat
    rows_extracted: int
    completed_at: Optional[datetime] = None


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: Optional[str] = None
    request_id: Optional[str] = None
