"""Performance tracking service using SQLite with WAL mode for concurrent access.

Stores request-level metrics (total time, agent time) and individual database query
metrics, correlated by request_id. All logging operations are wrapped in try/except
to ensure failures don't break actual requests.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("services.performance")

# Context variable for request_id propagation through async call stack
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


class PerformanceTracker:
    """SQLite-based performance metrics tracker with WAL mode for concurrency."""

    def __init__(self, db_path: str = "./performance.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create SQLite connection with WAL mode enabled."""
        if self._conn is None:
            # Create parent directory if needed
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

            # Use timeout to handle concurrent initialization by multiple workers
            self._conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0  # Wait up to 30 seconds for database lock
            )
            self._conn.row_factory = sqlite3.Row  # Return rows as dicts

            # Enable WAL mode for better concurrency
            self._conn.execute('PRAGMA journal_mode=WAL')
            self._conn.execute('PRAGMA synchronous=NORMAL')  # Faster, still safe

            logger.info(f"Performance tracker initialized with database: {self.db_path}")

        return self._conn

    def init_database(self) -> None:
        """Create tables and indexes if they don't exist."""
        try:
            conn = self._get_connection()

            # Main requests table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    query_text TEXT,
                    tenant_id TEXT,
                    user_role TEXT,
                    total_time_ms REAL NOT NULL,
                    agent_time_ms REAL,
                    error TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Individual database queries table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS db_queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    cypher_query TEXT,
                    duration_ms REAL NOT NULL,
                    records_returned INTEGER,
                    error TEXT,
                    FOREIGN KEY (request_id) REFERENCES requests(request_id)
                )
            """)

            # Create indexes for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_requests_timestamp
                ON requests(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_requests_tenant
                ON requests(tenant_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_db_queries_request
                ON db_queries(request_id)
            """)

            conn.commit()
            logger.info("Performance tracking database initialized successfully")

        except Exception as exc:
            logger.exception(f"Failed to initialize performance database: {exc}")
            raise

    def log_request(
        self,
        request_id: str,
        query_text: str,
        total_time_ms: float,
        agent_time_ms: Optional[float] = None,
        tenant_id: Optional[str] = None,
        user_role: Optional[str] = None,
        error: Optional[str] = None
    ) -> None:
        """Log request-level performance metrics.

        Args:
            request_id: Unique identifier for this request
            query_text: User's query text
            total_time_ms: Total request processing time
            agent_time_ms: Agent/LLM invocation time
            tenant_id: Tenant identifier
            user_role: User role (Administrator, User)
            error: Error message if request failed
        """
        try:
            conn = self._get_connection()
            timestamp = datetime.now(timezone.utc).isoformat()

            conn.execute("""
                INSERT INTO requests (
                    request_id, timestamp, query_text, tenant_id, user_role,
                    total_time_ms, agent_time_ms, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request_id, timestamp, query_text, tenant_id, user_role,
                total_time_ms, agent_time_ms, error
            ))
            conn.commit()

            logger.debug(f"Logged request metrics for {request_id}")

        except Exception as exc:
            # Never fail the request if logging fails
            logger.warning(f"Failed to log request metrics: {exc}")

    def log_db_query(
        self,
        request_id: str,
        cypher_query: str,
        duration_ms: float,
        records_returned: int,
        error: Optional[str] = None
    ) -> None:
        """Log individual database query metrics.

        Args:
            request_id: Associated request identifier
            cypher_query: Cypher query text
            duration_ms: Query execution time
            records_returned: Number of records returned
            error: Error message if query failed
        """
        try:
            conn = self._get_connection()
            timestamp = datetime.now(timezone.utc).isoformat()

            conn.execute("""
                INSERT INTO db_queries (
                    request_id, timestamp, cypher_query, duration_ms,
                    records_returned, error
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                request_id, timestamp, cypher_query, duration_ms,
                records_returned, error
            ))
            conn.commit()

            logger.debug(f"Logged DB query metrics for request {request_id}")

        except Exception as exc:
            # Never fail the query if logging fails
            logger.warning(f"Failed to log DB query metrics: {exc}")

    def get_recent_requests(
        self,
        limit: int = 10,
        min_duration_ms: Optional[float] = None,
        tenant_id: Optional[str] = None,
        include_db_queries: bool = True
    ) -> List[Dict[str, Any]]:
        """Query recent request metrics with optional filtering.

        Args:
            limit: Maximum number of requests to return (capped at 100)
            min_duration_ms: Only return requests slower than this threshold
            tenant_id: Filter by specific tenant
            include_db_queries: Include associated DB queries for each request

        Returns:
            List of request dictionaries with optional nested db_queries
        """
        try:
            conn = self._get_connection()

            # Cap limit at 100 for safety
            limit = min(limit, 100)

            # Build query with filters
            query = "SELECT * FROM requests WHERE 1=1"
            params: List[Any] = []

            if min_duration_ms is not None:
                query += " AND total_time_ms >= ?"
                params.append(min_duration_ms)

            if tenant_id is not None:
                query += " AND tenant_id = ?"
                params.append(tenant_id)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            requests = [dict(row) for row in cursor.fetchall()]

            # Optionally fetch associated DB queries
            if include_db_queries:
                for request in requests:
                    request_id = request['request_id']
                    cursor = conn.execute("""
                        SELECT * FROM db_queries
                        WHERE request_id = ?
                        ORDER BY timestamp
                    """, (request_id,))
                    request['db_queries'] = [dict(row) for row in cursor.fetchall()]

            logger.debug(f"Retrieved {len(requests)} recent requests")
            return requests

        except Exception as exc:
            logger.exception(f"Failed to query performance metrics: {exc}")
            return []

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            try:
                self._conn.close()
                self._conn = None
                logger.debug("Performance tracker connection closed")
            except Exception as exc:
                logger.warning(f"Error closing performance tracker: {exc}")


# Global singleton instance
_tracker: Optional[PerformanceTracker] = None


def get_tracker() -> PerformanceTracker:
    """Get or create the global performance tracker instance."""
    global _tracker
    if _tracker is None:
        db_path = os.getenv("PERFORMANCE_DB_PATH", "./performance.db")
        _tracker = PerformanceTracker(db_path)
        _tracker.init_database()
    return _tracker


def get_current_request_id() -> Optional[str]:
    """Get the current request_id from context."""
    return request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set the request_id in context for the current async task."""
    request_id_var.set(request_id)

