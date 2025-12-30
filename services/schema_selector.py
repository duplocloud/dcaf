"""Dynamic schema selection using ChromaDB for semantic vector search.

This service is **query-only**: it retrieves a relevant schema subset from a
pre-populated ChromaDB collection and formats it for LLM context injection.

Index building (extracting Neo4j schema, enriching properties, embedding, and
writing to ChromaDB) is handled by a separate application/job.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar
from urllib.parse import urlparse

import chromadb
from chromadb import DEFAULT_DATABASE, DEFAULT_TENANT
from chromadb.config import Settings

T = TypeVar("T")


class RateLimiter:
    """Simple rate limiter to throttle requests to external services."""
    
    def __init__(self, requests_per_second: float = 1.0):
        """
        Initialize rate limiter.
        
        Args:
            requests_per_second: Maximum requests per second (e.g., 1.0 = 1 req/sec, 0.5 = 1 req/2sec)
        """
        self.min_interval = 1.0 / requests_per_second
        self.last_request_time = 0.0
        self._lock = None  # Lazy init for thread safety
    
    def _get_lock(self):
        """Lazy initialize lock (avoids issues with module-level instantiation)."""
        if self._lock is None:
            import threading
            self._lock = threading.Lock()
        return self._lock
    
    def wait(self):
        """Wait if necessary to respect the rate limit."""
        with self._get_lock():
            now = time.time()
            elapsed = now - self.last_request_time
            
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                logger.debug("Rate limiting: sleeping %.2fs before ChromaDB request", sleep_time)
                time.sleep(sleep_time)
            
            self.last_request_time = time.time()


# Global rate limiter for ChromaDB requests
# Configurable via VECTOR_DB_REQUESTS_PER_SECOND env var (default: 2 requests/second)
_chromadb_rate_limiter: Optional[RateLimiter] = None


def get_chromadb_rate_limiter() -> RateLimiter:
    """Get or create the global ChromaDB rate limiter."""
    global _chromadb_rate_limiter
    if _chromadb_rate_limiter is None:
        rps = float(os.getenv("VECTOR_DB_REQUESTS_PER_SECOND", "2.0"))
        _chromadb_rate_limiter = RateLimiter(requests_per_second=rps)
        logger.info("ChromaDB rate limiter initialized: %.1f requests/second", rps)
    return _chromadb_rate_limiter


def retry_with_backoff(
    func: Callable[[], T],
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple = (Exception,),
) -> T:
    """
    Execute a function with exponential backoff retry logic.
    
    Args:
        func: The function to execute (no arguments)
        max_attempts: Maximum number of attempts before giving up
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff calculation
        jitter: Add random jitter to prevent thundering herd
        retryable_exceptions: Tuple of exception types to retry on
    
    Returns:
        The result of the function call
    
    Raises:
        The last exception if all retries fail
    """
    last_exception = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except retryable_exceptions as e:
            last_exception = e
            
            if attempt == max_attempts:
                logger.error(
                    "All %d retry attempts failed for ChromaDB operation: %s",
                    max_attempts,
                    str(e),
                )
                raise
            
            # Calculate delay with exponential backoff
            delay = min(base_delay * (exponential_base ** (attempt - 1)), max_delay)
            
            # Add jitter (±25%) to prevent thundering herd
            if jitter:
                delay = delay * (0.75 + random.random() * 0.5)
            
            logger.warning(
                "ChromaDB operation failed (attempt %d/%d): %s. Retrying in %.1fs...",
                attempt,
                max_attempts,
                str(e),
                delay,
            )
            time.sleep(delay)
    
    # Should never reach here, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic error")

from utils.safe_logging import safe_log_warning

logger = logging.getLogger(__name__)


DEFAULT_COLLECTION_NAME = "duploservices-arch-agent"


class SchemaIndexer:
    """
    Query-only schema accessor for ChromaDB.

    The name is kept for backwards compatibility, but this class no longer builds
    or refreshes the schema index in ChromaDB.
    """

    def __init__(
        self,
        neo4j_client: Any | None = None,  # kept for compatibility; unused
        cache_dir: Path | None = None,
        collection_name: str | None = None,
    ):
        self.neo4j_client = neo4j_client
        self.cache_dir = cache_dir or Path(os.getenv("VECTOR_DB_CACHE_DIR", ".schema_cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Allow remote vector DB (Chroma server) via env var, fallback to local persistence
        self.vector_db_url = os.getenv("VECTOR_DB_URL")
        self.chroma_client = self._create_chroma_client()

        env_collection = os.getenv("VECTOR_DB_COLLECTION_NAME")
        self.collection_name = collection_name or env_collection or DEFAULT_COLLECTION_NAME
        self.collection: Any | None = None

    def _create_chroma_client(self):
        """Create a Chroma client, supporting remote or local persistence."""
        if self.vector_db_url:
            # Rate limit + retry logic for remote connections
            rate_limiter = get_chromadb_rate_limiter()
            max_retries = int(os.getenv("VECTOR_DB_MAX_RETRIES", "5"))
            base_delay = float(os.getenv("VECTOR_DB_RETRY_BASE_DELAY", "2.0"))
            
            def create_with_rate_limit():
                rate_limiter.wait()
                return self._create_remote_client(self.vector_db_url)
            
            # Catch a wide range of errors for retry:
            # - ChromaError: ChromaDB-specific errors (429, pool timeout, etc.)
            # - ConnectionError/TimeoutError: Network issues
            # - ValueError: ChromaDB wraps 503/500 errors as ValueError
            # - Exception: Catch-all for unexpected HTTP errors
            return retry_with_backoff(
                func=create_with_rate_limit,
                max_attempts=max_retries,
                base_delay=base_delay,
                max_delay=30.0,
                retryable_exceptions=(
                    chromadb.errors.ChromaError,
                    ConnectionError,
                    TimeoutError,
                    ValueError,  # ChromaDB wraps 503/500 as ValueError
                    OSError,     # Network-level errors
                ),
            )

        return chromadb.Client(
            Settings(
                persist_directory=str(self.cache_dir),
                anonymized_telemetry=False,
            )
        )

    def _create_remote_client(self, vector_db_url: str):
        """Create a client that points at a remote Chroma server."""
        parsed = urlparse(vector_db_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("VECTOR_DB_URL must be http or https")

        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        use_ssl = parsed.scheme == "https"

        if parsed.path not in {"", "/"}:
            logger.warning(
                "VECTOR_DB_URL has a path component (%s) which will be ignored; "
                "Chroma server is expected at the root path.",
                parsed.path,
            )

        # Token is now optional - only use if provided
        token = os.getenv("VECTOR_DB_API_TOKEN")

        tenant = os.getenv("VECTOR_DB_TENANT") or DEFAULT_TENANT
        database = os.getenv("VECTOR_DB_DATABASE") or DEFAULT_DATABASE

        logger.info(
            "Using remote ChromaDB server at %s (host=%s port=%s ssl=%s tenant=%s database=%s auth=%s)",
            vector_db_url,
            host,
            port,
            use_ssl,
            tenant,
            database,
            "token" if token else "none",
        )

        # Only include auth credentials if token is provided
        settings_kwargs = {"anonymized_telemetry": False}
        if token:
            settings_kwargs["chroma_client_auth_credentials"] = token

        settings = Settings(**settings_kwargs)

        return chromadb.HttpClient(
            host=host,
            port=port,
            ssl=use_ssl,
            settings=settings,
            tenant=tenant,
            database=database,
        )

    def ensure_collection(self) -> Any:
        """
        Ensure the ChromaDB collection handle is available.

        Note: `get_or_create_collection` will create an empty collection if it does
        not exist. In production, the index-builder should pre-populate it.
        """
        if self.collection is not None:
            return self.collection

        def do_get():
            get_chromadb_rate_limiter().wait()
            return self.chroma_client.get_or_create_collection(name=self.collection_name)

        try:
            self.collection = retry_with_backoff(
                func=do_get,
                max_attempts=3,
                base_delay=1.0,
                max_delay=10.0,
                retryable_exceptions=(
                    chromadb.errors.ChromaError,
                    ConnectionError,
                    TimeoutError,
                    ValueError,
                    OSError,
                ),
            )
            return self.collection
        except Exception as exc:
            logger.exception("Failed to get ChromaDB collection")
            raise RuntimeError(f"ChromaDB collection access failed: {exc}") from exc

    def search(
        self,
        query: str,
        n_results: int = 15,
        filter_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant schema elements using semantic similarity.

        Args:
            query: User's natural language query
            n_results: Number of results to return
            filter_type: Optional filter by element type ('node', 'relationship', 'pattern')

        Returns:
            List of relevant schema elements with metadata
        """
        collection = self.ensure_collection()

        # Build where clause for filtering
        where = None
        if filter_type:
            where = {"type": filter_type}

        def do_query():
            # Rate limit before each query attempt
            get_chromadb_rate_limiter().wait()
            return collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
            )

        try:
            # Rate limit + retry logic for ChromaDB queries
            results = retry_with_backoff(
                func=do_query,
                max_attempts=3,  # Fewer retries for queries (user is waiting)
                base_delay=1.0,
                max_delay=10.0,
                retryable_exceptions=(
                    chromadb.errors.ChromaError,
                    ConnectionError,
                    TimeoutError,
                    ValueError,  # ChromaDB wraps 503/500 as ValueError
                    OSError,     # Network-level errors
                ),
            )

            # Convert ChromaDB results to our format
            elements = []
            if results and results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    document = results["documents"][0][i] if results["documents"] else ""
                    distance = results["distances"][0][i] if results.get("distances") else 0

                    elements.append(
                        {
                            "id": doc_id,
                            "type": metadata.get("type", ""),
                            "label": metadata.get("label", ""),
                            "rel_type": metadata.get("rel_type", ""),
                            "from_label": metadata.get("from_label", ""),
                            "to_label": metadata.get("to_label", ""),
                            "description": document,
                            "properties": json.loads(metadata.get("properties", "{}")),
                            "similarity": float(1 - distance) if distance else 0,  # Convert distance to similarity
                        }
                    )

            return elements

        except Exception as exc:
            logger.exception("Schema search failed")
            raise RuntimeError(f"Schema search failed: {exc}") from exc


class DynamicSchemaSelector:
    """Orchestrates semantic search and graph expansion for optimal schema selection."""

    def __init__(self, neo4j_client: Any | None = None):
        # kept for backwards compatibility; unused in query-only selector
        self.neo4j_client = neo4j_client
        self.indexer = SchemaIndexer(neo4j_client=self.neo4j_client)

        # Configuration from environment
        self.top_k = int(os.getenv("VECTOR_DB_TOP_K", "15"))
        self.similarity_threshold = float(os.getenv("VECTOR_DB_SIMILARITY_THRESHOLD", "0.3"))
        self.enable_expansion = os.getenv("VECTOR_DB_ENABLE_EXPANSION", "true").lower() == "true"

    # Query expansion mappings for common terms that may not match well semantically
    # Maps user terms to additional search queries to try
    QUERY_EXPANSION_TERMS = {
        "service": ["KubernetesService", "KubernetesPod", "workload", "deployment"],
        "services": ["KubernetesService", "KubernetesPod", "workload", "deployment"],
        "pod": ["KubernetesPod", "KubernetesContainer", "workload"],
        "pods": ["KubernetesPod", "KubernetesContainer", "workload"],
        "dependency": ["DEPENDS_ON", "CONNECTS_TO", "USES", "relationship"],
        "dependencies": ["DEPENDS_ON", "CONNECTS_TO", "USES", "relationship"],
        "connection": ["CONNECTS_TO", "network", "KubernetesService"],
        "connections": ["CONNECTS_TO", "network", "KubernetesService"],
        "container": ["KubernetesContainer", "KubernetesPod", "docker"],
        "containers": ["KubernetesContainer", "KubernetesPod", "docker"],
        "database": ["RDSInstance", "database", "storage"],
        "databases": ["RDSInstance", "database", "storage"],
        "tenant": ["DuploTenant", "namespace", "environment"],
        "tenants": ["DuploTenant", "namespace", "environment"],
    }

    def _expand_query_terms(self, user_query: str) -> List[str]:
        """
        Generate additional search queries based on keywords in the user query.
        
        This helps when the user's natural language doesn't match well with
        the technical schema terms in ChromaDB embeddings.
        """
        queries = [user_query]  # Always include original
        query_lower = user_query.lower()
        
        for term, expansions in self.QUERY_EXPANSION_TERMS.items():
            if term in query_lower:
                for expansion in expansions:
                    # Create expanded query
                    expanded = f"{expansion} {user_query}"
                    if expanded not in queries:
                        queries.append(expanded)
        
        return queries[:5]  # Limit to 5 queries to avoid too many ChromaDB calls

    def get_relevant_elements(self, user_query: str) -> List[Dict[str, Any]]:
        """
        Return raw schema elements for accumulation/merging.

        This is the lower-level method that returns unformatted elements,
        suitable for caching and merging across conversation turns.

        Uses query expansion to improve results when user terms don't match
        schema terminology well.

        Args:
            user_query: Natural language query from user

        Returns:
            List of schema element dicts with id, type, label, properties, etc.
        """
        # Expand query with related technical terms
        queries = self._expand_query_terms(user_query)
        
        # Collect elements from all queries, deduplicating by ID
        all_elements: Dict[str, Dict[str, Any]] = {}
        
        for query in queries:
            try:
                elements = self.indexer.search(query=query, n_results=self.top_k)
                for elem in elements:
                    elem_id = elem.get("id", "")
                    if elem_id and elem_id not in all_elements:
                        all_elements[elem_id] = elem
                    elif elem_id and elem.get("similarity", 0) > all_elements[elem_id].get("similarity", 0):
                        # Keep higher similarity version
                        all_elements[elem_id] = elem
            except Exception as e:
                logger.warning(f"Query expansion search failed for '{query}': {e}")
                continue
        
        # Convert back to list and sort by similarity
        elements = sorted(
            all_elements.values(),
            key=lambda x: x.get("similarity", 0),
            reverse=True
        )
        
        # Filter by threshold
        filtered = [e for e in elements if e.get("similarity", 0) >= self.similarity_threshold]
        if not filtered:
            logger.warning(
                f"No schema elements above threshold {self.similarity_threshold} - "
                f"using top {min(5, len(elements))} results"
            )
            filtered = elements[:5]
        
        # Limit to top_k after combining
        filtered = filtered[:self.top_k]
        
        if self.enable_expansion:
            filtered = self._expand_schema(filtered)
        
        logger.info(
            f"Query expansion: {len(queries)} queries, {len(all_elements)} unique elements, "
            f"{len(filtered)} after filtering"
        )
        
        return filtered

    def format_schema_for_llm(self, elements: List[Dict[str, Any]]) -> str:
        """
        Format elements as markdown for LLM context injection.

        Public wrapper around _format_schema_for_llm for use by chat_service_unified.

        Args:
            elements: List of schema element dicts

        Returns:
            Formatted markdown string
        """
        return self._format_schema_for_llm(elements)

    def get_relevant_schema(self, user_query: str) -> str:
        """
        Main entry point: Get relevant schema subset for a user query.

        Args:
            user_query: Natural language query from user

        Returns:
            Formatted schema markdown for LLM context
        """
        from datetime import datetime
        start_time = datetime.now()

        try:
            # Semantic search for initial candidates
            elements = self.indexer.search(query=user_query, n_results=self.top_k)

            # Filter by similarity threshold
            filtered_elements = [
                e for e in elements if e.get("similarity", 0) >= self.similarity_threshold
            ]

            if not filtered_elements:
                logger.warning(
                    f"No schema elements above threshold {self.similarity_threshold} - "
                    f"using top {min(5, len(elements))} results"
                )
                filtered_elements = elements[:5]

            # Optional: expand via graph relationships
            if self.enable_expansion:
                filtered_elements = self._expand_schema(filtered_elements)

            # Format for LLM
            formatted_schema = self._format_schema_for_llm(filtered_elements)

            # Calculate metrics
            selection_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            element_types = {
                "nodes": sum(1 for e in filtered_elements if e.get("type") == "node"),
                "relationships": sum(1 for e in filtered_elements if e.get("type") == "relationship"),
                "patterns": sum(1 for e in filtered_elements if e.get("type") == "pattern"),
            }
            avg_similarity = (
                sum(e.get("similarity", 0) for e in filtered_elements) / len(filtered_elements)
                if filtered_elements else 0
            )

            logger.info(
                f"Selected {len(filtered_elements)} schema elements for query in {selection_time_ms:.1f}ms "
                f"(similarity threshold: {self.similarity_threshold}, avg similarity: {avg_similarity:.3f})"
            )

            # Log metrics
            try:
                from services.schema_metrics import get_metrics_collector
                metrics = get_metrics_collector()
                metrics.log_selection(
                    query=user_query,
                    elements_selected=len(filtered_elements),
                    selection_time_ms=selection_time_ms,
                    element_types=element_types,
                    avg_similarity=avg_similarity,
                    success=True,
                )
            except Exception as e:
                safe_log_warning(logger, "Failed to log schema selection metrics: %s", str(e))

            return formatted_schema

        except Exception as exc:
            logger.exception("Failed to get relevant schema")

            # Log failure metrics
            try:
                selection_time_ms = (datetime.now() - start_time).total_seconds() * 1000
                from services.schema_metrics import get_metrics_collector
                metrics = get_metrics_collector()
                metrics.log_selection(
                    query=user_query,
                    elements_selected=0,
                    selection_time_ms=selection_time_ms,
                    element_types={},
                    avg_similarity=0,
                    success=False,
                    error=str(exc),
                )
            except Exception as e:
                safe_log_warning(logger, "Failed to log schema selection failure metrics: %s", str(e))

            # Fallback: return minimal schema or raise
            raise RuntimeError(f"Schema selection failed: {exc}") from exc

    def _expand_schema(self, elements: List[Dict]) -> List[Dict]:
        """
        Expand schema selection by including connected relationships.

        If we selected a node, include its common relationships.
        If we selected a relationship, ensure both endpoint nodes are included.
        """
        # Extract selected labels
        selected_nodes = {e["label"] for e in elements if e["type"] == "node" and e["label"]}
        {e["rel_type"] for e in elements if e["type"] == "relationship" and e["rel_type"]}

        # Ensure endpoint nodes for selected relationships
        for elem in elements:
            if elem["type"] == "relationship":
                if elem.get("from_label"):
                    selected_nodes.add(elem["from_label"])
                if elem.get("to_label"):
                    selected_nodes.add(elem["to_label"])

        # Find relationships connecting selected nodes (1-hop expansion)
        # This is a simplified version - could query Neo4j for actual patterns
        expanded_elements = list(elements)  # Start with original

        # Search for relationships between selected nodes
        for node_label in selected_nodes:
            try:
                rel_candidates = self.indexer.search(
                    query=f"relationships involving {node_label}",
                    n_results=5,
                    filter_type="relationship",
                )

                for rel in rel_candidates:
                    # Include if it connects two selected nodes
                    from_label = rel.get("from_label", "")
                    to_label = rel.get("to_label", "")

                    if from_label in selected_nodes or to_label in selected_nodes:
                        if rel not in expanded_elements:
                            expanded_elements.append(rel)
            except Exception as e:
                safe_log_warning(logger, "Failed to expand schema for node %s: %s", node_label, str(e))
                continue  # Skip expansion errors

        return expanded_elements

    def _format_schema_for_llm(self, elements: List[Dict]) -> str:
        """Format selected schema elements as markdown for LLM context."""
        # Group by type
        nodes = [e for e in elements if e["type"] == "node"]
        relationships = [e for e in elements if e["type"] == "relationship"]
        patterns = [e for e in elements if e["type"] == "pattern"]

        output = ["", "## Relevant Neo4j Schema Subset", "", "### Node Types", ""]

        # Format nodes
        if nodes:
            for node in nodes:
                label = node.get("label", "Unknown")
                props = node.get("properties", {})

                output.append(f"**{label}**")
                if props:
                    output.append("Properties:")
                    for prop_name, prop_type in list(props.items())[:10]:  # Limit properties
                        output.append(f"  - {prop_name}: {prop_type}")
                output.append("")
        else:
            output.append("(No specific node types identified for this query)")
            output.append("")

        # Format relationships
        output.append("### Relationships")
        output.append("")

        if relationships:
            for rel in relationships:
                rel_type = rel.get("rel_type", "UNKNOWN")
                from_label = rel.get("from_label", "")
                to_label = rel.get("to_label", "")
                props = rel.get("properties", {})

                output.append(f"**{rel_type}**")
                output.append(f"  - Pattern: ({from_label})-[{rel_type}]->({to_label})")

                if props:
                    output.append("  - Properties:")
                    for prop_name, prop_type in list(props.items())[:5]:
                        output.append(f"    - {prop_name}: {prop_type}")
                output.append("")
        else:
            output.append("(No specific relationships identified for this query)")
            output.append("")

        # Format patterns
        if patterns:
            output.append("### Common Patterns")
            output.append("")
            for pattern in patterns[:5]:  # Limit to top 5 patterns
                pattern_str = pattern.get("pattern", "")
                output.append(f"- `{pattern_str}`")
            output.append("")

        return "\n".join(output)


# Singleton instance for easy access
_selector: Optional[DynamicSchemaSelector] = None


def get_schema_selector() -> DynamicSchemaSelector:
    """Get or create singleton schema selector instance."""
    global _selector
    if _selector is None:
        _selector = DynamicSchemaSelector()
    return _selector

