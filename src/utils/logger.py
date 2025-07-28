"""
Centralised logging helper for the Service Desk Agents project.

This module configures a single root logger that can emit either human-readable
console logs (default) or structured JSON logs suitable for production log
aggregators. The desired format and log-level are controlled with environment
variables so that behaviour can be switched without code changes.

Usage
-----
from src.utils.logger import get_logger
logger = get_logger(__name__)
logger.info("Something happened")
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
import atexit

# Context variables for correlation IDs
from src.utils.request_context import current_request_id, current_user_id


_configured: bool = False


class JsonFormatter(logging.Formatter):
    """Format log records as JSON for machine consumption."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        # Basic structured payload – extend as needed (e.g. trace / request IDs)
        payload: dict[str, object] = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        req_id = current_request_id.get(None)
        if req_id is not None:
            payload["request_id"] = req_id

        user_id = current_user_id.get(None)
        if user_id is not None:
            payload["user_id"] = user_id
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


def _configure_root_logger() -> None:
    """Initialise the root logger exactly once."""

    global _configured
    if _configured:
        return

    # Determine runtime config from environment variables.
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "console").lower()

    handler: logging.Handler = logging.StreamHandler(sys.stdout)
    
    # Filter to inject context vars into LogRecord for console formatting
    class ContextFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
            record.request_id = current_request_id.get(None)
            record.user_id = current_user_id.get(None)
            return True

    context_filter = ContextFilter()

    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)s | %(name)s | %(request_id)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    # Reset default handlers to avoid duplicate logs when re-configured (e.g. in tests).
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)
    root.addHandler(handler)
    root.addFilter(context_filter)

    # Reduce noise from common noisy libraries unless explicitly overridden.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.setLevel(os.getenv("UVICORN_LOG_LEVEL", "WARNING"))
    access_logger.addFilter(context_filter)

    _configured = True

    # Ensure handlers flush on interpreter exit
    atexit.register(logging.shutdown)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger with the given *name*, ensuring global config is applied."""

    _configure_root_logger()
    return logging.getLogger(name or __name__)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def reset_logging_for_tests() -> None:
    """Clear handlers/filters so tests can reconfigure logging cleanly."""

    global _configured
    logging.shutdown()
    root = logging.getLogger()
    root.handlers.clear()
    root.filters.clear()
    _configured = False 