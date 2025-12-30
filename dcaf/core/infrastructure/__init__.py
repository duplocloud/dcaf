"""
Infrastructure Layer - Cross-cutting Concerns.

This layer contains infrastructure code that supports the application:
    - Configuration management
    - Logging setup
    - Shared utilities
"""

from .config import CoreConfig
from .logging import setup_logging

__all__ = [
    "CoreConfig",
    "setup_logging",
]
