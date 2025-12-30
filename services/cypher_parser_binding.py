"""Thin wrapper for loading the libcypher-parser shared library.

This module is the foundation for the upcoming AST-based tenant guard.
It does **not** expose full parsing capabilities yet; for now we only
verify that the native library can be located and loaded at runtime.

The Docker image ships the `libcypher-parser-dev` package so the shared
library should be available under Linux.  On macOS developers can install
it via Homebrew (`brew install libcypher-parser`).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


class CypherParserUnavailable(RuntimeError):
    """Raised when libcypher-parser cannot be loaded."""


@lru_cache(maxsize=1)
def load_library() -> Optional[ctypes.CDLL]:
    """Load and memoise the libcypher-parser shared library.

    Returns
    -------
    ctypes.CDLL | None
        The loaded library, or ``None`` if it could not be found.
    """

    libname = ctypes.util.find_library("cypher-parser")
    if not libname:
        logger.debug("libcypher-parser: shared library not found on system path")
        return None

    try:
        library = ctypes.CDLL(libname)
    except OSError as exc:  # pragma: no cover - platform specific
        logger.warning("libcypher-parser: failed to load %s: %s", libname, exc)
        return None

    logger.debug("libcypher-parser: loaded %s", libname)
    return library


def ensure_available() -> ctypes.CDLL:
    """Return the loaded library or raise a helpful error."""

    library = load_library()
    if library is None:
        raise CypherParserUnavailable(
            "libcypher-parser is required for AST tenant rewriting. "
            "Install it via your OS package manager (e.g. `apt-get install "
            "libcypher-parser-dev` or `brew install libcypher-parser`)."
        )
    return library


def is_available() -> bool:
    """Quick availability probe used by integration tests and feature flags."""

    return load_library() is not None



