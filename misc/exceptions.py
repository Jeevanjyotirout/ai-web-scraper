"""
app/core/exceptions.py
───────────────────────
Domain-specific exception hierarchy.

All custom exceptions inherit from  AppBaseError  which carries:
- A human-readable message
- An optional error code (for API responses)
- Optional contextual data
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class AppBaseError(Exception):
    """Root for all application-level exceptions."""

    http_status: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        *,
        detail: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or message
        self.context = context or {}


# ── Job exceptions ────────────────────────────────────────────────────────────

class JobNotFoundError(AppBaseError):
    http_status = 404
    error_code = "JOB_NOT_FOUND"


class JobAlreadyExistsError(AppBaseError):
    http_status = 409
    error_code = "JOB_ALREADY_EXISTS"


class JobQueueFullError(AppBaseError):
    http_status = 429
    error_code = "JOB_QUEUE_FULL"


class JobCancelledError(AppBaseError):
    http_status = 409
    error_code = "JOB_CANCELLED"


# ── Scraping exceptions ───────────────────────────────────────────────────────

class ScrapingError(AppBaseError):
    http_status = 502
    error_code = "SCRAPING_FAILED"


class RobotsBlockedError(ScrapingError):
    http_status = 403
    error_code = "ROBOTS_BLOCKED"


class PageRenderError(ScrapingError):
    error_code = "PAGE_RENDER_ERROR"


class RateLimitedError(ScrapingError):
    http_status = 429
    error_code = "TARGET_RATE_LIMITED"


class MaxPagesReachedError(ScrapingError):
    http_status = 422
    error_code = "MAX_PAGES_REACHED"


# ── Parsing exceptions ────────────────────────────────────────────────────────

class InstructionParseError(AppBaseError):
    http_status = 422
    error_code = "INVALID_INSTRUCTIONS"


class UnsupportedInstructionError(InstructionParseError):
    error_code = "UNSUPPORTED_INSTRUCTION"


# ── AI exceptions ─────────────────────────────────────────────────────────────

class AIProcessingError(AppBaseError):
    http_status = 503
    error_code = "AI_PROCESSING_FAILED"


class OllamaUnavailableError(AIProcessingError):
    error_code = "OLLAMA_UNAVAILABLE"


class EmbeddingError(AIProcessingError):
    error_code = "EMBEDDING_FAILED"


# ── Export exceptions ─────────────────────────────────────────────────────────

class ExportError(AppBaseError):
    http_status = 500
    error_code = "EXPORT_FAILED"


class UnsupportedFormatError(ExportError):
    http_status = 422
    error_code = "UNSUPPORTED_FORMAT"


class FileTooLargeError(ExportError):
    http_status = 413
    error_code = "FILE_TOO_LARGE"


# ── Storage exceptions ────────────────────────────────────────────────────────

class FileNotFoundError(AppBaseError):  # noqa: A001 (shadows builtin intentionally)
    http_status = 404
    error_code = "FILE_NOT_FOUND"


class StorageError(AppBaseError):
    error_code = "STORAGE_ERROR"
