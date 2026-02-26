"""
Discovery module for emitting graph data to the UI's Discovery panel.

Provides models for graph nodes/edges, a context-var-based queue for
emitting discovery events from tools, and a parser for Neo4j results.
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# =============================================================================
# Discovery Models
# =============================================================================


class DiscoveryNode(BaseModel):
    """A node in the discovery graph."""

    id: str
    labels: list[str]
    properties: dict[str, Any]


class DiscoveryEdge(BaseModel):
    """An edge (relationship) in the discovery graph."""

    id: str
    type: str
    startNode: str
    endNode: str
    properties: dict[str, Any] = Field(default_factory=dict)


class DiscoveryPayload(BaseModel):
    """Complete graph payload with nodes and edges."""

    nodes: list[DiscoveryNode]
    edges: list[DiscoveryEdge]


# =============================================================================
# Context Var Queue
# =============================================================================

_discovery_queue: contextvars.ContextVar[list[DiscoveryPayload] | None] = contextvars.ContextVar(
    "discovery_queue", default=None
)


def emit_discovery(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
) -> None:
    """
    Emit discovery graph data from a tool or interceptor.

    Pushes a DiscoveryPayload onto a context-var queue. The streaming
    pipeline drains this queue and yields DiscoveryEvents to the client.

    Args:
        nodes: List of node dicts with id, labels, properties.
        edges: List of edge dicts with id, type, startNode, endNode, properties.
    """
    payload = DiscoveryPayload(
        nodes=[DiscoveryNode(**n) for n in nodes],
        edges=[DiscoveryEdge(**e) for e in (edges or [])],
    )
    queue = _discovery_queue.get(None)
    if queue is None:
        queue = [payload]
        _discovery_queue.set(queue)
    else:
        queue.append(payload)
    logger.debug(
        f"Discovery payload queued: {len(payload.nodes)} nodes, {len(payload.edges)} edges"
    )


def drain_discovery_queue() -> list[DiscoveryPayload]:
    """
    Drain all pending discovery payloads from the queue.

    Returns the list and clears the queue. Called by the streaming
    pipeline after tool completions.
    """
    queue = _discovery_queue.get(None)
    if queue is None:
        return []
    payloads = list(queue)
    _discovery_queue.set(None)
    return payloads


def reset_discovery_queue() -> None:
    """Reset the discovery queue. Used in tests."""
    _discovery_queue.set(None)
