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


_configured: bool = False


class JsonFormatter(logging.Formatter):
    """Format log records as JSON for machine consumption."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        # Basic structured payload – extend as needed (e.g. trace / request IDs)
        payload = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
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
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    # Reset default handlers to avoid duplicate logs when re-configured (e.g. in tests).
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)
    root.addHandler(handler)

    # Reduce noise from common noisy libraries unless explicitly overridden.
    logging.getLogger("uvicorn.access").setLevel(os.getenv("UVICORN_LOG_LEVEL", "WARNING"))

    _configured = True


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger with the given *name*, ensuring global config is applied."""

    _configure_root_logger()
    return logging.getLogger(name or __name__) 