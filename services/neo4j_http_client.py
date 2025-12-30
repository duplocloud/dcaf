"""HTTP-based Neo4j client using the Neo4j HTTP API.

This client implements the Neo4jProvider protocol using HTTP requests instead of
the Bolt protocol. Useful in Kubernetes environments where Bolt traffic may be blocked.
Uses httpx for async HTTP with connection pooling.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List
from urllib.parse import urlparse

try:
    import httpx
except ImportError as exc:
    raise RuntimeError(
        "httpx package must be installed to use HttpNeo4jClient - add it to your dependencies."
    ) from exc

try:
    from dotenv import find_dotenv, load_dotenv
    env_path = find_dotenv(".env.local", usecwd=True)
    if env_path:
        load_dotenv(env_path, override=False)
except Exception:
    pass

# Import normalization utilities from the Bolt client
from services.neo4j_client import (
    _normalize_values,
)

logger = logging.getLogger("services.neo4j")


class HttpNeo4jClient:
    """Neo4j client using HTTP API instead of Bolt protocol.

    Implements the Neo4jProvider protocol for interchangeability with BoltNeo4jClient.
    Uses httpx for async HTTP requests with connection pooling.
    """

    def __init__(self) -> None:
        """Initialize HTTP client from environment variables.

        Reads NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD from environment.
        NEO4J_URI must use http:// or https:// scheme.

        Raises:
            RuntimeError: If required environment variables are missing
            ValueError: If NEO4J_URI is not an HTTP/HTTPS URL
        """
        uri = os.getenv("NEO4J_URI")
        username = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")

        if uri is None or username is None or password is None:
            raise RuntimeError(
                "NEO4J_URI, NEO4J_USERNAME and NEO4J_PASSWORD env vars must be set"
            )

        self._username = username
        self._password = password

        # Validate that URI is HTTP/HTTPS
        parsed = urlparse(uri)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"HttpNeo4jClient requires http:// or https:// URI, got: {uri}\n"
                f"Hint: Use NEO4J_URI=http://your-host:7474 for HTTP protocol"
            )

        # Use the URI directly (no derivation)
        self._base_url = uri.rstrip("/")
        self._database = os.getenv("NEO4J_DATABASE", "neo4j")
        self._tx_commit_url = f"{self._base_url}/db/{self._database}/tx/commit"

        # Log initialization
        logger.info("HttpNeo4jClient: Initialized with HTTP URI")
        logger.info("  Base URL: %s", self._base_url)
        logger.info("  Database: %s", self._database)
        logger.info("  Protocol: %s", parsed.scheme.upper())

        # Create httpx client with connection pooling
        # Use conservative timeout settings
        timeout = httpx.Timeout(
            connect=float(os.getenv("NEO4J_CONNECTION_TIMEOUT", "10")),
            read=float(os.getenv("NEO4J_READ_TIMEOUT", "30")),
            write=10.0,
            pool=5.0,
        )

        # Connection pool settings
        limits = httpx.Limits(
            max_keepalive_connections=int(os.getenv("NEO4J_MAX_CONNECTION_POOL_SIZE", "5")),
            max_connections=int(os.getenv("NEO4J_MAX_CONNECTION_POOL_SIZE", "5")) + 5,
            keepalive_expiry=float(os.getenv("NEO4J_MAX_CONNECTION_LIFETIME", "50")),
        )

        self._client = httpx.AsyncClient(
            auth=(self._username, self._password),
            timeout=timeout,
            limits=limits,
            follow_redirects=True,
        )

        logger.info("HttpNeo4jClient initialized successfully")
        logger.info("  Transaction endpoint: %s", self._tx_commit_url)

    async def close(self) -> None:
        """Close the HTTP client and release connections."""
        await self._client.aclose()

    async def _execute_cypher_http(
        self, cypher: str, params: Dict[str, Any] | None = None
    ) -> List[Dict[str, Any]]:
        """Execute Cypher via HTTP API and return normalized results.

        Args:
            cypher: Cypher query string
            params: Optional parameters to bind

        Returns:
            List of normalized result rows

        Raises:
            ValueError: On authentication or validation errors
            Exception: On connection or server errors
        """
        request_body = {
            "statements": [
                {
                    "statement": cypher,
                    "parameters": params or {},
                }
            ]
        }

        # Log the HTTP request at INFO level so it's visible
        logger.info("Neo4j HTTP API: Sending request to %s", self._tx_commit_url)
        logger.debug("HTTP API request body: %s", json.dumps(request_body, indent=2))

        try:
            response = await self._client.post(
                self._tx_commit_url,
                json=request_body,
                headers={"Content-Type": "application/json"},
            )

            logger.info("Neo4j HTTP API: Received response with status %d", response.status_code)
            logger.debug("HTTP API response status: %d", response.status_code)

            # Handle HTTP errors
            if response.status_code == 401:
                raise ValueError("Neo4j authentication failed: invalid credentials")
            elif response.status_code == 404:
                raise ValueError("Neo4j database not found")
            elif response.status_code >= 400:
                error_text = response.text[:500]  # Limit error text
                raise ValueError(f"Neo4j HTTP API error ({response.status_code}): {error_text}")

            response_data = response.json()
            logger.debug("HTTP API response body: %s", json.dumps(response_data, indent=2, default=str))

            # Check for Cypher errors in response
            errors = response_data.get("errors", [])
            if errors:
                error_msg = errors[0].get("message", "Unknown error")
                error_code = errors[0].get("code", "")
                raise ValueError(f"Neo4j Cypher error [{error_code}]: {error_msg}")

            # Parse results
            results = response_data.get("results", [])
            if not results:
                return []

            # Extract data from first result
            result_data = results[0].get("data", [])

            # Normalize to match Bolt driver output format
            # HTTP API returns: {"row": [...values...], "meta": [...metadata...]}
            # We need to convert to dict format using column names
            columns = results[0].get("columns", [])

            normalized_rows = []
            for item in result_data:
                row_values = item.get("row", [])
                # Create dict mapping column names to values
                row_dict = {
                    col: row_values[i] if i < len(row_values) else None
                    for i, col in enumerate(columns)
                }
                # Apply same normalization as Bolt client
                normalized_rows.append(_normalize_values(row_dict))

            return normalized_rows

        except httpx.HTTPError as exc:
            logger.error("HTTP connection error when accessing %s: %s", self._tx_commit_url, str(exc))
            raise RuntimeError(f"Failed to connect to Neo4j HTTP API at {self._tx_commit_url}: {exc}") from exc

    async def run_cypher(
        self, cypher: str, params: Dict[str, Any] | None = None
    ) -> List[Dict[str, Any]]:
        """Execute *cypher* query with optional *params* and return records as dicts.

        The query is validated to be read-only via a simple keyword check to
        avoid accidental writes (CREATE/MERGE/DELETE/SET). Raises
        ValueError if a disallowed keyword is detected.

        Implements retry logic for transient failures (5xx errors, network issues).

        Args:
            cypher: Cypher query string
            params: Optional parameters to bind

        Returns:
            List of normalized result rows as dicts

        Raises:
            ValueError: If query contains mutating keywords
            Exception: On connection or execution errors
        """
        # Simple read-only guard (same as Bolt client)
        forbidden = re.compile(r"\b(CREATE|MERGE|DELETE|SET)\b", re.IGNORECASE)
        if forbidden.search(cypher or ""):
            logger.warning("Neo4j run_cypher rejected due to mutating keyword. query=%r", cypher)
            raise ValueError("Mutating Cypher statements are not allowed (CREATE/MERGE/DELETE/SET)")

        logger.info("Neo4j HTTP run_cypher (full):\n%s", cypher)
        logger.info("Neo4j HTTP run_cypher params: %s", params or {})

        # Retry logic for transient failures
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                results = await self._execute_cypher_http(cypher, params)
                logger.info(
                    "Neo4j HTTP run_cypher output (full JSON):\n%s",
                    json.dumps(results, indent=2, default=str),
                )
                return results
            except ValueError:
                # Don't retry validation or auth errors
                raise
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Neo4j HTTP run_cypher attempt %d failed: %s",
                    attempt + 1,
                    str(exc),
                )
                if attempt == 0:
                    # Retry once on transient errors
                    continue
                logger.exception("Neo4j HTTP run_cypher failed after retry")
                raise

        # Should not reach here; re-raise last exception defensively
        if last_exc is not None:
            raise last_exc
        return []

    async def search_nodes(self, term: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Return up to *limit* nodes whose ``name`` contains *term* (case-insensitive).

        Args:
            term: Search term (case-insensitive substring match)
            limit: Maximum number of results

        Returns:
            List of dicts with id, type, name fields
        """
        query = (
            "MATCH (n) "
            "WHERE toLower(n.name) CONTAINS toLower($term) "
            "RETURN id(n) AS id, labels(n)[0] AS type, n.name AS name "
            "LIMIT $limit"
        )

        logger.info("Neo4j HTTP search_nodes query (full):\n%s", query)
        logger.info("Neo4j HTTP search_nodes params: %s", {"term": term, "limit": limit})

        results = await self._execute_cypher_http(query, {"term": term, "limit": limit})

        logger.info("Neo4j HTTP search_nodes output (full JSON):\n%s", json.dumps(results, indent=2, default=str))
        return results

    async def get_dependencies(
        self, node_id: int, max_hops: int = 2
    ) -> List[str]:
        """Return distinct names of nodes reachable within *max_hops* outgoing hops.

        Includes children (outgoing), parents (incoming), and siblings (shared parent).

        Args:
            node_id: Node ID to find dependencies for
            max_hops: Maximum traversal depth

        Returns:
            List of node names
        """
        hop_range = f"1..{max_hops}"

        query = f"""
// Children (nodes this one depends on)
MATCH (n)-[r*{hop_range}]->(child)
WHERE id(n) = $id
RETURN child.name AS name, 'child' AS relationship_type

UNION ALL

// Parents (nodes that depend on this one)
MATCH (n)<-[r*{hop_range}]-(parent)
WHERE id(n) = $id
RETURN parent.name AS name, 'parent' AS relationship_type

UNION ALL

// Siblings (nodes that share the same parent)
MATCH (n)<-[r1]-(shared_parent)-[r2]->(sibling)
WHERE id(n) = $id AND id(sibling) <> $id
RETURN sibling.name AS name, 'sibling' AS relationship_type
        """

        logger.info("Neo4j HTTP get_dependencies query (full):\n%s", query)
        logger.info("Neo4j HTTP get_dependencies params: %s", {"id": node_id, "max_hops": max_hops})

        results = await self._execute_cypher_http(query, {"id": node_id})

        logger.info("Neo4j HTTP get_dependencies output (full JSON):\n%s", json.dumps(results, indent=2, default=str))
        return [r["name"] for r in results if "name" in r]

