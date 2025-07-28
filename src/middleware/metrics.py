"""FastAPI middleware for Prometheus metrics collection.

Adds per-request counters and latency histograms using the shared metrics
objects in ``src.core.metrics``.
"""
from __future__ import annotations

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.core.metrics import increment_request, observe_request_latency


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware that records an entry for every incoming HTTP request."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        method = request.method
        path = request.url.path

        start = time.perf_counter()
        response: Response = await call_next(request)
        duration = time.perf_counter() - start

        status_code = response.status_code

        # Record metrics
        increment_request(method, path, status_code)
        observe_request_latency(method, path, status_code, duration)

        return response 