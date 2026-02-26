"""
Discovery module for emitting graph data to the UI's Discovery panel.

Provides models for graph nodes/edges, a context-var-based queue for
emitting discovery events from tools, and a parser for Neo4j results.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

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
