"""
app/api/middleware.py
──────────────────────
FastAPI middleware stack.

1. CorrelationIDMiddleware   — injects a unique request ID into every request
2. TimingMiddleware          — logs request duration
3. Global exception handler  — maps domain exceptions → clean JSON responses
"""

from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.exceptions import AppBaseError
from app.core.logging import request_id_var
from app.models.job import ErrorResponse


# ── Correlation ID middleware ──────────────────────────────────────────────────

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Reads  X-Request-ID  header (or generates one) and makes it available
    via the  request_id_var  context variable used by the logger.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(request_id)

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token)


# ── Timing middleware ──────────────────────────────────────────────────────────

class TimingMiddleware(BaseHTTPMiddleware):
    """Log each request's method, path, status code and duration."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start    = time.perf_counter()
        response = await call_next(request)
        elapsed  = (time.perf_counter() - start) * 1000

        logger.info(
            "HTTP request",
            method  = request.method,
            path    = request.url.path,
            status  = response.status_code,
            ms      = round(elapsed, 1),
        )
        response.headers["X-Response-Time-Ms"] = str(round(elapsed, 1))
        return response


# ── Exception handlers ─────────────────────────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:
    """Attach global exception handlers to the FastAPI app."""

    @app.exception_handler(AppBaseError)
    async def handle_app_error(request: Request, exc: AppBaseError) -> JSONResponse:
        request_id = request_id_var.get()
        logger.warning(
            "Domain error",
            error_code=exc.error_code,
            message=exc.message,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.http_status,
            content=ErrorResponse(
                error_code=exc.error_code,
                message=exc.message,
                detail=exc.detail,
                request_id=request_id,
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def handle_generic_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = request_id_var.get()
        logger.exception("Unhandled exception", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error_code="INTERNAL_ERROR",
                message="An unexpected error occurred",
                detail=str(exc) if not False else None,   # hide in prod
                request_id=request_id,
            ).model_dump(),
        )
