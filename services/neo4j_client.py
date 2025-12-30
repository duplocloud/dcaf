"""Thin wrapper around the Neo4j Python driver used by the chat workflow.

The URI, username and password are taken from environment variables:

* ``NEO4J_URI``
* ``NEO4J_USERNAME``
* ``NEO4J_PASSWORD``

If the variables are absent, import-time errors are *not* raised; instead, the
client constructor will raise ``RuntimeError`` when attempting to connect. This
makes local development easier for engineers who do not need database access.
"""
from __future__ import annotations

import logging
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from services.performance_tracker import get_current_request_id, get_tracker
from utils.safe_logging import safe_log_info, safe_log_json

# Load environment variables from project-root .env.local when available.
# This makes the client usable in tests/CLI without going through FastAPI app startup.
try:  # pragma: no cover – trivial env bootstrap
    from dotenv import find_dotenv, load_dotenv

    env_path = find_dotenv(".env.local", usecwd=True)
    if env_path:
        load_dotenv(env_path, override=False)
except Exception:
    pass

from neo4j import READ_ACCESS, AsyncDriver, AsyncGraphDatabase, Record
from neo4j.exceptions import ServiceUnavailable, SessionExpired

logger = logging.getLogger("services.neo4j")


def _normalize_record(rec: Any) -> Dict[str, Any]:
    """Return *rec* as a plain ``dict`` regardless of Neo4j driver/JSON shape.

    The Neo4j Python driver normally yields ``Record`` instances which convert
    cleanly via ``dict(record)``.  In some execution paths we now receive the
    JSON-serialised representation of a ``Record`` produced by FastAPI
    (list of dicts with ``keys`` / ``_fields`` / ``_fieldLookup``).  This helper
    gracefully converts both shapes to a flat ``dict`` so that calling code can
    rely on standard key access (e.g. ``d["name"]``).
    """

    # Case 1 – real ``Record`` from the async driver
    try:
        if isinstance(rec, Record):
            return _normalize_values(dict(rec))
    except Exception:  # pragma: no cover – Record may not be importable in tests
        pass

    # Case 2 – JSON serialised version with keys / _fields arrays
    if isinstance(rec, dict) and "keys" in rec and "_fields" in rec:
        keys = rec.get("keys", [])
        fields = rec.get("_fields", [])
        mapped = {k: fields[i] for i, k in enumerate(keys) if i < len(fields)}
        return _normalize_values(mapped)

    # Case 3 – already a mapping we can work with directly
    if isinstance(rec, dict):
        return _normalize_values(rec)

    # Fallback – last resort conversion
    try:
        return _normalize_values(dict(rec))
    except Exception:
        return _normalize_values({"value": rec})


def _combine_neo4j_int(value: Any) -> Any:
    """Combine Neo4j JS-style 64-bit integers {low, high} to a Python int.

    If the input is not of that shape, return it unchanged.
    """
    if (
        isinstance(value, dict)
        and "low" in value
        and "high" in value
        and isinstance(value["low"], int)
        and isinstance(value["high"], int)
    ):
        low = value["low"] & 0xFFFFFFFF
        high = value["high"] & 0xFFFFFFFF
        combined = (high << 32) | low
        # Interpret as signed 64-bit
        if combined >= 2**63:
            combined -= 2**64
        return combined
    return value


def _normalize_node_like(obj: Dict[str, Any]) -> Dict[str, Any] | None:
    """Normalize a Node/Relationship-like dict produced by FastAPI/driver JSON.

    - Node shape typically has: identity, labels, properties, elementId
    - Relationship shape typically has: identity, start, end, type, properties, elementId
    Return a simplified mapping or None if not matching.
    """
    # Node
    if {"labels", "properties"}.issubset(obj.keys()) and (
        "identity" in obj or "elementId" in obj
    ):
        node_id = obj.get("elementId")
        if node_id is None:
            node_id = _combine_neo4j_int(obj.get("identity"))
        return {
            "id": node_id,
            "labels": list(obj.get("labels", [])),
            "properties": _normalize_values(obj.get("properties", {})),
        }

    # Relationship
    if {"start", "end", "type", "properties"}.issubset(obj.keys()):
        rel_id = obj.get("elementId")
        if rel_id is None:
            rel_id = _combine_neo4j_int(obj.get("identity"))
        return {
            "id": rel_id,
            "type": obj.get("type"),
            "start": _combine_neo4j_int(obj.get("start")),
            "end": _combine_neo4j_int(obj.get("end")),
            "properties": _normalize_values(obj.get("properties", {})),
        }

    # Path (best-effort)
    if "segments" in obj and isinstance(obj["segments"], list):
        segments = obj.get("segments", [])
        norm_segments = _normalize_values(segments)
        return {"segments": norm_segments}

    return None


def _normalize_values(value: Any) -> Any:
    """Recursively normalize values for LLM-friendly consumption.

    - Convert Neo4j JS-style ints {low, high} to Python int
    - Simplify Node/Relationship/Path dict shapes
    - Recurse into lists and dicts
    """
    # Primitive fast-path
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    # Combine JS-style 64-bit integer representation
    if isinstance(value, dict) and "low" in value and "high" in value:
        return _combine_neo4j_int(value)

    # Dicts
    if isinstance(value, dict):
        simplified = _normalize_node_like(value)
        if simplified is not None:
            return simplified
        return {k: _normalize_values(v) for k, v in value.items()}

    # Lists / tuples
    if isinstance(value, (list, tuple)):
        return [_normalize_values(v) for v in value]

    # Fallback: try to coerce to dict then recurse
    try:
        return _normalize_values(dict(value))
    except Exception:
        return value


class BoltNeo4jClient:
    """Async helper around Neo4j driver with minimal query helpers.

    This is the Bolt protocol implementation of the Neo4jProvider interface.
    Uses the official Neo4j Python driver (port 7687).
    """

    def __init__(self) -> None:
        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")
        if uri is None or user is None or password is None:
            raise RuntimeError(
                "NEO4J_URI, NEO4J_USERNAME and NEO4J_PASSWORD env vars must be set"
            )

        # Persist credentials for potential driver recreation
        self._uri = uri
        self._user = user
        self._password = password

        self._driver: AsyncDriver = self._build_driver()
        self._connectivity_verified: bool = False

    async def close(self) -> None:
        await self._driver.close()

    @asynccontextmanager
    async def _get_session(self):
        # Verify connectivity once per process lifetime to avoid starting with a stale pool
        if not self._connectivity_verified:
            try:
                await self._driver.verify_connectivity()
                self._connectivity_verified = True
            except Exception:
                # Attempt one driver recreation before surfacing
                await self._recreate_driver()
                await self._driver.verify_connectivity()
                self._connectivity_verified = True

        async with self._driver.session(default_access_mode=READ_ACCESS) as session:
            yield session

    def _build_driver(self) -> AsyncDriver:
        """Create a configured AsyncDriver with conservative pool settings.

        Uses a guarded application of optional kwargs to remain compatible with
        different neo4j-driver versions.
        """
        max_conn_lifetime = int(os.getenv("NEO4J_MAX_CONNECTION_LIFETIME", "50"))  # seconds
        conn_timeout = int(os.getenv("NEO4J_CONNECTION_TIMEOUT", "10"))
        pool_size = int(os.getenv("NEO4J_MAX_CONNECTION_POOL_SIZE", "1"))

        driver_kwargs: Dict[str, Any] = {
            "auth": (self._user, self._password),
            # Proactively recycle connections before typical LB/network idle timeouts (e.g., 60s)
            "max_connection_lifetime": max_conn_lifetime,
            # Reasonable timeouts to avoid hanging operations
            "connection_timeout": conn_timeout,
            # Keep pool tiny to avoid reusing idle sockets when behind LB/NAT
            "max_connection_pool_size": pool_size,
        }
        # Some driver versions expose keep_alive; add it defensively
        try:
            return AsyncGraphDatabase.driver(self._uri, keep_alive=True, **driver_kwargs)
        except TypeError:
            # Fallback: remove keep_alive
            try:
                return AsyncGraphDatabase.driver(self._uri, **driver_kwargs)
            except TypeError:
                # Fallback: remove pool size if unsupported
                driver_kwargs.pop("max_connection_pool_size", None)
                return AsyncGraphDatabase.driver(self._uri, **driver_kwargs)

    async def _recreate_driver(self) -> None:
        """Close and recreate the underlying driver safely."""
        try:
            await self._driver.close()
        except Exception:
            # Ignore close errors; we're replacing the driver anyway
            pass
        self._driver = self._build_driver()

    async def search_nodes(self, term: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Return up to *limit* nodes whose ``name`` contains *term* (case-insensitive)."""
        query_start_time = time.perf_counter()

        query = (
            "MATCH (n) "
            "WHERE toLower(n.name) CONTAINS toLower($term) "
            "RETURN id(n) AS id, labels(n)[0] AS type, n.name AS name "
            "LIMIT $limit"
        )
        async with self._get_session() as session:
            safe_log_info(logger, "Neo4j search_nodes query (full):\n%s", query)
            safe_log_json(logger.info, "Neo4j search_nodes params: %s", {"term": term, "limit": limit})

            async def work(tx):
                res = await tx.run(query, term=term, limit=limit)
                return await res.data()

            raw_records = await session.execute_read(work)

        records = [_normalize_record(r) for r in raw_records]
        query_elapsed_ms = (time.perf_counter() - query_start_time) * 1000
        logger.info(f"⏱️  PERFORMANCE: Neo4j search_nodes execution time: {query_elapsed_ms:.2f}ms (returned {len(records)} records)")

        safe_log_json(logger.info, "Neo4j search_nodes output (full JSON):\n%s", records)
        return records

    async def get_dependencies(
        self, node_id: int, max_hops: int = 2
    ) -> List[str]:
        """Return distinct names of nodes reachable within *max_hops* outgoing hops."""
        query_start_time = time.perf_counter()

        # Inject the hop range (e.g. 1..2) so callers can limit traversal depth.
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
        async with self._get_session() as session:
            safe_log_info(logger, "Neo4j get_dependencies query (full):\n%s", query)
            safe_log_json(logger.info, "Neo4j get_dependencies params: %s", {"id": node_id, "max_hops": max_hops})

            async def work(tx):
                res = await tx.run(query, id=node_id)
                return await res.data()

            raw_records = await session.execute_read(work)

        records = [_normalize_record(r) for r in raw_records]
        names = [r["name"] for r in records]
        query_elapsed_ms = (time.perf_counter() - query_start_time) * 1000
        logger.info(f"⏱️  PERFORMANCE: Neo4j get_dependencies execution time: {query_elapsed_ms:.2f}ms (returned {len(names)} dependencies)")

        safe_log_json(logger.info, "Neo4j get_dependencies output (full JSON):\n%s", records)
        return names

    # ------------------------------------------------------------------
    # New helper: run arbitrary *read-only* Cypher generated by Bedrock
    # ------------------------------------------------------------------
    async def run_cypher(self, cypher: str, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        """Execute *cypher* query with optional *params* and return records as dicts.

        The query is validated to be read-only via a simple keyword check to
        avoid accidental writes (CREATE/MERGE/DELETE/SET). Raise
        ``ValueError`` if a disallowed keyword is detected.
        """

        # Simple read-only guard
        forbidden = re.compile(r"\b(CREATE|MERGE|DELETE|SET)\b", re.IGNORECASE)
        if forbidden.search(cypher or ""):
            logger.warning("Neo4j run_cypher rejected due to mutating keyword. query=%r", cypher)
            raise ValueError("Mutating Cypher statements are not allowed (CREATE/MERGE/DELETE/SET)")

        # Lightweight retry for transient connection issues (stale pooled socket, etc.)
        last_exc: Exception | None = None
        for attempt in range(2):
            query_start_time = time.perf_counter()
            try:
                async with self._get_session() as session:
                    safe_log_info(logger, "Neo4j run_cypher (full):\n%s", cypher)
                    safe_log_json(logger.info, "Neo4j run_cypher params: %s", params or {})

                    async def work(tx):
                        res = await tx.run(cypher, **(params or {}))
                        return await res.data()

                    raw_records = await session.execute_read(work)
                    normalized_records = [_normalize_record(r) for r in raw_records]

                    query_elapsed_ms = (time.perf_counter() - query_start_time) * 1000

                    # DEBUG: Explicit logging that can't be silenced
                    logger.info(f"Neo4j run_cypher: Got {len(raw_records)} raw records, {len(normalized_records)} normalized")
                    if len(normalized_records) == 0:
                        logger.warning("Neo4j run_cypher returned EMPTY ARRAY (no records matched)")

                    # Get request_id from context for correlation
                    request_id = get_current_request_id()
                    logger.info(f"⏱️  PERFORMANCE: Neo4j query execution time: {query_elapsed_ms:.2f}ms (returned {len(normalized_records)} records, request_id={request_id})")

                    # Log to performance tracker if we have a request_id
                    if request_id:
                        try:
                            tracker = get_tracker()
                            tracker.log_db_query(
                                request_id=request_id,
                                cypher_query=cypher,
                                duration_ms=query_elapsed_ms,
                                records_returned=len(normalized_records),
                                error=None
                            )
                        except Exception as log_exc:
                            # Never fail the query if logging fails
                            logger.warning(f"Failed to log DB query metrics: {log_exc}")

                    safe_log_json(logger.info, "Neo4j run_cypher output (full JSON):\n%s", normalized_records)
                    return normalized_records
            except (ServiceUnavailable, SessionExpired, RuntimeError) as exc:
                # RuntimeError covers uvloop "handler is closed" seen during send_all
                last_exc = exc
                logger.warning(
                    "Neo4j run_cypher attempt %d failed with %s: %s", attempt + 1, type(exc).__name__, str(exc)
                )
                if attempt == 0:
                    # Recreate driver and retry once
                    await self._recreate_driver()
                    continue
                logger.exception("Neo4j run_cypher failed after retry")
                raise
            except Exception:
                # Non-transient errors – surface immediately
                logger.exception("Neo4j run_cypher failed")
                raise

        # Should not reach here; re-raise last exception defensively
        logger.error("Neo4j run_cypher: UNEXPECTED CONTROL FLOW - reached defensive return path!")
        logger.error(f"Neo4j run_cypher: last_exc={last_exc}, cypher={cypher[:200]}")
        if last_exc is not None:
            raise last_exc
        return []

# Convenience singleton for dependency injection in FastAPI
# Now delegates to the provider factory for automatic protocol selection
_client: BoltNeo4jClient | None = None


def get_client():
    """Get Neo4j client instance (delegates to provider factory).

    This function now uses the provider factory pattern to automatically
    select between Bolt and HTTP clients based on NEO4J_CLIENT_TYPE env var.

    For direct Bolt client access, use BoltNeo4jClient() directly.
    For provider abstraction, use get_neo4j_client() from neo4j_provider.

    Returns:
        Neo4j client implementing the Neo4jProvider protocol
    """
    from services.neo4j_provider import get_neo4j_client
    return get_neo4j_client()


# Backward compatibility: Keep old class name as alias
Neo4jClient = BoltNeo4jClient
