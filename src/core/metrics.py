"""Prometheus metrics helpers shared across the application.

This module centralises metric object creation so that importing modules
refer to the *same* Counter/Histogram instances, preventing duplication
in the Prometheus registry.
"""
from __future__ import annotations

import time
from typing import Callable

from prometheus_client import Counter, Histogram

# --------------------------------------------------------------------------------------
# Metric objects (labels are defined at observation time)
# --------------------------------------------------------------------------------------
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total number of HTTP requests processed.",
    ["method", "path", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds",
    "Latency of HTTP requests in seconds.",
    ["method", "path", "status_code"],
)

LLM_LATENCY = Histogram(
    "bedrock_llm_latency_seconds",
    "Latency of AWS Bedrock LLM invocations in seconds.",
    ["model_id"],
)

# --------------------------------------------------------------------------------------
# Helper functions / decorators
# --------------------------------------------------------------------------------------

def increment_request(method: str, path: str, status_code: int | str) -> None:
    """Increment the request counter."""
    REQUEST_COUNT.labels(method=method, path=path, status_code=str(status_code)).inc()


def observe_request_latency(
    method: str, path: str, status_code: int | str, latency: float
) -> None:
    """Record request latency in seconds."""
    REQUEST_LATENCY.labels(method=method, path=path, status_code=str(status_code)).observe(latency)


def observe_llm_latency(model_id: str, latency: float) -> None:
    """Record Bedrock LLM latency in seconds."""
    LLM_LATENCY.labels(model_id=model_id).observe(latency)


# Decorator for timing arbitrary callables ------------------------------------------------

def time_function(metric: Histogram | None = None) -> Callable[[Callable[..., _T]], Callable[..., _T]]:  # type: ignore[name-defined]
    """Decorator to time a function and record the duration in *metric* if given.

    If *metric* is None, no observation is recorded (useful for quick timing without metrics).
    """

    def decorator(func: Callable[..., _T]) -> Callable[..., _T]:
        def wrapper(*args, **kwargs):  # type: ignore[override]
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start
                if metric is not None:
                    metric.observe(duration)

        return wrapper  # type: ignore[return-value]

    return decorator


# Generic helper ------------------------------------------------

_T = type("_T", (), {})  # runtime-only generic placeholder 