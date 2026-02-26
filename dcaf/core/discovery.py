"""
Discovery module for emitting graph data to the UI's Discovery panel.

Provides models for graph nodes/edges, a context-var-based queue for
emitting discovery events from tools, and a parser for Neo4j results.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
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


# =============================================================================
# Neo4j Result Parser
# =============================================================================


def neo4j_result_to_discovery(result: Any) -> DiscoveryPayload:
    """
    Convert a neo4j run_cypher_query result to a DiscoveryPayload.

    The result from Neo4jTools.run_cypher_query() is typically a list of dicts
    from neo4j's session.run(query).data(). Each dict represents a row, where
    values can be node dicts (properties only -- id/labels lost by .data()).

    This parser:
    - Treats each dict-valued field in each row as a node
    - Generates deterministic IDs from the node content
    - Uses the column name as a default label
    - Deduplicates nodes by ID

    Args:
        result: The return value from run_cypher_query (list[dict] or str)

    Returns:
        DiscoveryPayload with extracted nodes (edges require explicit relationships)
    """
    if not isinstance(result, list):
        return DiscoveryPayload(nodes=[], edges=[])

    seen_ids: set[str] = set()
    nodes: list[DiscoveryNode] = []

    for row in result:
        if not isinstance(row, dict):
            continue
        for col_name, value in row.items():
            if not isinstance(value, dict):
                continue
            # Generate deterministic ID from content
            node_id = _make_node_id(value)
            if node_id in seen_ids:
                continue
            seen_ids.add(node_id)

            # Use column name as label hint (e.g., "n" -> "Node", "service" -> "Service")
            label = col_name.capitalize() if len(col_name) > 1 else "Node"
            nodes.append(
                DiscoveryNode(
                    id=node_id,
                    labels=[label],
                    properties=value,
                )
            )

    return DiscoveryPayload(nodes=nodes, edges=[])


def _make_node_id(properties: dict[str, Any]) -> str:
    """Generate a deterministic ID from node properties."""
    # Use name if available, otherwise hash the full properties
    name = properties.get("name")
    if name:
        return f"node-{name}"
    content = json.dumps(properties, sort_keys=True, default=str)
    return f"node-{hashlib.sha256(content.encode()).hexdigest()[:12]}"
