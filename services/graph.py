"""In-memory graph utilities operating on AWSResource collections.

This avoids pulling in Neo4j for basic POC behaviour. Functions:
• build_adjacency – create adjacency dict
• reachable_from – breadth-first traversal
• shortest_path – BFS shortest path between two nodes
"""
from __future__ import annotations

from collections import deque
from typing import Dict, Iterable, List

from models import AWSResource

Adjacency = Dict[str, List[str]]


def build_adjacency(resources: Iterable[AWSResource]) -> Adjacency:
    """Return adjacency list (outgoing) keyed by resource_id."""
    adj: Adjacency = {}
    for res in resources:
        adj.setdefault(res.resource_id, [])
        for rel in res.relationships:
            target = rel["to"]
            # forward
            adj[res.resource_id].append(target)
            # reverse (treat graph as undirected for impact/path)
            adj.setdefault(target, []).append(res.resource_id)
    return adj


def reachable_from(start: str, adj: Adjacency) -> List[str]:
    """Return all nodes (including *start*) reachable via outgoing edges."""
    seen: set[str] = {start}
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        for neighbor in adj.get(node, []):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return list(seen)


def shortest_path(src: str, dst: str, adj: Adjacency) -> List[str]:
    """Return list of node ids representing shortest path src→dst (inclusive).

    Empty list if no path exists.
    """
    if src == dst:
        return [src]
    queue: deque[list[str]] = deque([[src]])
    visited: set[str] = {src}
    while queue:
        path = queue.popleft()
        last = path[-1]
        for neighbor in adj.get(last, []):
            if neighbor == dst:
                return path + [dst]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(path + [neighbor])
    return []

__all__: list[str] = ["build_adjacency", "reachable_from", "shortest_path", "Adjacency"]
