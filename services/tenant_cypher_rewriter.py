"""Tenant-aware Cypher rewriting using libcypher-parser.

This module provides the first cut of a structural query rewriter that ensures
tenant predicates are applied to every query part.  It currently implements a
very small slice of the full behaviour (parse + echo), and scaffolds the
classes and error types we will flesh out as we iterate.

The goal is to replace the brittle regex approach with AST rewrites.  For now
we expose a `rewrite_cypher` function that simply verifies the parser can be
invoked and round-trips the Cypher string untouched.  Subsequent commits will
add real AST traversal and predicate injection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from .cypher_parser_binding import CypherParserUnavailable, ensure_available

logger = logging.getLogger(__name__)


class TenantRewriteError(RuntimeError):
    """Raised when tenant rewriting fails."""


@dataclass(slots=True)
class RewriteConfig:
    """Configuration for tenant-aware rewriting."""

    tenant_id: str
    role: str = "User"
    forbidden_labels: List[str] = field(default_factory=list)
    enforce_primary_alias: str = "n"


@dataclass(slots=True)
class RewriterOutput:
    """Result of rewriting the Cypher query."""

    cypher: str
    security_hints: List[str] = field(default_factory=list)


def rewrite_cypher(cypher: str, config: RewriteConfig) -> RewriterOutput:
    """Rewrite *cypher* to enforce tenant scoping.

    Parameters
    ----------
    cypher:
        The incoming Cypher string.
    config:
        Runtime configuration including tenant id and caller role.

    Returns
    -------
    str
        For now, returns the original Cypher string untouched. Future
        iterations will inject tenant predicates.
    """

    if not isinstance(cypher, str) or not cypher.strip():
        raise TenantRewriteError("Cypher query must be a non-empty string")

    try:
        # Ensure the native library is present.  We don't yet use it, but this
        # confirms the environment is configured correctly and allows early
        # feedback if the dependency is missing.
        ensure_available()
    except CypherParserUnavailable as exc:  # pragma: no cover - env-specific
        raise TenantRewriteError(str(exc)) from exc

    logger.debug(
        "Tenant rewriter invoked (tenant_id=%s, role=%s)",
        config.tenant_id,
        config.role,
    )

    # TODO: Parse the query with libcypher-parser, walk the AST, and inject the
    # tenant predicate.  For now we simply return the original query to keep the
    # system functional while we build out the remaining logic.
    security_hints: List[str] = []
    if config.forbidden_labels:
        security_hints.append(
            "Tenant guard configured with forbidden labels: "
            + ", ".join(config.forbidden_labels)
        )
    security_hints.append(
        f"Primary alias enforcement: {config.enforce_primary_alias!r}"
    )

    return RewriterOutput(cypher=cypher, security_hints=security_hints)
