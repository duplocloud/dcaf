"""Logging setup for DCAF Core."""

import logging
import sys
from typing import Any


def setup_logging(
    level: str = "INFO",
    format_string: str | None = None,
    logger_name: str = "dcaf.core",
) -> logging.Logger:
    """
    Set up logging for the DCAF Core framework.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Optional custom format string
        logger_name: Name for the logger

    Returns:
        Configured logger

    Example:
        logger = setup_logging(level="DEBUG")
        logger.debug("Debug message")
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Create formatter
    formatter = logging.Formatter(format_string)

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Get or create logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid adding duplicate handlers
    if not logger.handlers:
        logger.addHandler(handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    Args:
        name: Module name (typically __name__)

    Returns:
        Logger for the module

    Example:
        logger = get_logger(__name__)
        logger.info("Processing request")
    """
    return logging.getLogger(f"dcaf.core.{name}")


class LoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter that adds context to log messages.

    Useful for adding conversation IDs or other context
    to all log messages from a component.

    Example:
        base_logger = get_logger(__name__)
        logger = LoggerAdapter(base_logger, {"conversation_id": "conv-123"})
        logger.info("Processing")  # Includes conversation_id in context
    """

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        """Process the logging message and add extra context."""
        extra = kwargs.get("extra", {})
        extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs
