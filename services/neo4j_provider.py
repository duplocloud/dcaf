"""Abstract interface for Neo4j client implementations.

Defines a Protocol that both Bolt and HTTP clients must implement,
allowing the application to switch between connection types via configuration.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Protocol

logger = logging.getLogger("services.neo4j")


class Neo4jProvider(Protocol):
    """Protocol defining the interface all Neo4j client implementations must follow.

    This allows the application to use either Bolt or HTTP protocol transparently.
    """

    async def run_cypher(
        self, cypher: str, params: Dict[str, Any] | None = None
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query and return results as list of dicts.

        Args:
            cypher: Cypher query string
            params: Optional parameters to bind in the query

        Returns:
            List of result rows, each as a normalized dict

        Raises:
            ValueError: If query contains mutating keywords (CREATE/MERGE/DELETE/SET)
            Exception: On connection or execution errors
        """
        ...

    async def search_nodes(self, term: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for nodes by name containing the given term.

        Args:
            term: Search term (case-insensitive)
            limit: Maximum number of results to return

        Returns:
            List of matching nodes with id, type, and name
        """
        ...

    async def get_dependencies(
        self, node_id: int, max_hops: int = 2
    ) -> List[str]:
        """Get names of nodes related to the given node within max_hops.

        Includes children (outgoing), parents (incoming), and siblings (shared parent).

        Args:
            node_id: ID of the node to find dependencies for
            max_hops: Maximum traversal depth

        Returns:
            List of node names
        """
        ...

    async def close(self) -> None:
        """Close the client connection and release resources."""
        ...


# Singleton instance cache
_client_instance: Neo4jProvider | None = None


def _detect_protocol_from_uri(uri: str) -> str:
    """Detect protocol type from NEO4J_URI.

    Args:
        uri: Neo4j connection URI

    Returns:
        Either "bolt" or "http" based on URI scheme
    """
    if not uri:
        return "bolt"  # Default fallback

    uri_lower = uri.lower().strip()

    # Check if it's an HTTP/HTTPS URI
    if uri_lower.startswith("http://") or uri_lower.startswith("https://"):
        return "http"

    # Check if it's a Bolt/Neo4j protocol URI
    if (uri_lower.startswith("bolt://") or uri_lower.startswith("bolt+s://") or
        uri_lower.startswith("neo4j://") or uri_lower.startswith("neo4j+s://")):
        return "bolt"

    # Default to bolt for unknown schemes
    return "bolt"


def get_neo4j_client() -> Neo4jProvider:
    """Factory function to get the Neo4j client based on URI scheme.

    Automatically detects the client type from NEO4J_URI:
    - bolt://, bolt+s://, neo4j://, neo4j+s:// → Bolt client (official driver)
    - http://, https:// → HTTP client (REST API)

    Returns singleton instance.

    Returns:
        Neo4j client implementing the Neo4jProvider protocol

    Raises:
        RuntimeError: If client initialization fails
    """
    global _client_instance

    if _client_instance is not None:
        return _client_instance

    # Auto-detect protocol from URI scheme
    neo4j_uri = os.getenv("NEO4J_URI", "")
    client_type = _detect_protocol_from_uri(neo4j_uri)

    logger.info("Detected Neo4j protocol: %s (from URI: %s)", client_type, neo4j_uri)

    if client_type == "bolt":
        from services.neo4j_client import BoltNeo4jClient
        logger.info("Using Bolt Neo4j client (binary protocol, port 7687)")
        _client_instance = BoltNeo4jClient()
    elif client_type == "http":
        from services.neo4j_http_client import HttpNeo4jClient
        logger.info("Using HTTP Neo4j client (REST API, port 7474)")
        _client_instance = HttpNeo4jClient()
    else:
        raise RuntimeError(
            f"Unexpected protocol detection result: '{client_type}'. This should not happen."
        )

    return _client_instance


def reset_client() -> None:
    """Reset the singleton instance. Useful for testing."""
    global _client_instance
    _client_instance = None

