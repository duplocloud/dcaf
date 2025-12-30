"""Metrics and evaluation tracking for dynamic schema selection.

This module provides logging and metrics for evaluating the effectiveness
of the dynamic schema selection system.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SchemaMetricsCollector:
    """Collects and tracks metrics for schema selection performance."""

    def __init__(self, metrics_file: Path | None = None):
        self.metrics_file = metrics_file or Path(".schema_cache/metrics.jsonl")
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

    def log_selection(
        self,
        query: str,
        elements_selected: int,
        selection_time_ms: float,
        element_types: Dict[str, int],
        avg_similarity: float,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """
        Log a schema selection event.

        Args:
            query: User's natural language query
            elements_selected: Number of schema elements selected
            selection_time_ms: Time taken for selection in milliseconds
            element_types: Count by type (nodes, relationships, patterns)
            avg_similarity: Average similarity score of selected elements
            success: Whether selection succeeded
            error: Error message if failed
        """
        metric = {
            "timestamp": datetime.utcnow().isoformat(),
            "query": query[:200],  # Truncate for privacy
            "elements_selected": elements_selected,
            "selection_time_ms": round(selection_time_ms, 2),
            "element_types": element_types,
            "avg_similarity": round(avg_similarity, 3),
            "success": success,
            "error": error,
        }

        try:
            with open(self.metrics_file, "a") as f:
                f.write(json.dumps(metric) + "\n")
        except Exception as exc:
            logger.warning(f"Failed to log metric: {exc}")

    def log_query_result(
        self,
        query: str,
        cypher_success: bool,
        result_count: int,
        cypher_error: Optional[str] = None,
    ) -> None:
        """
        Log the result of executing a Cypher query.

        Args:
            query: Original user query
            cypher_success: Whether Cypher execution succeeded
            result_count: Number of results returned
            cypher_error: Error message if failed
        """
        metric = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "query_result",
            "query": query[:200],
            "cypher_success": cypher_success,
            "result_count": result_count,
            "cypher_error": cypher_error,
        }

        try:
            with open(self.metrics_file, "a") as f:
                f.write(json.dumps(metric) + "\n")
        except Exception as exc:
            logger.warning(f"Failed to log query result: {exc}")

    def get_summary_stats(self, hours: int = 24) -> Dict[str, Any]:
        """
        Calculate summary statistics for recent selections.

        Args:
            hours: Number of hours to analyze (default 24)

        Returns:
            Summary statistics including averages, success rate, etc.
        """
        if not self.metrics_file.exists():
            return {"error": "No metrics collected yet"}

        try:
            from datetime import timedelta

            cutoff = datetime.utcnow() - timedelta(hours=hours)
            metrics: List[Dict] = []

            with open(self.metrics_file, "r") as f:
                for line in f:
                    try:
                        metric = json.loads(line)
                        timestamp = datetime.fromisoformat(metric["timestamp"])
                        if timestamp >= cutoff:
                            metrics.append(metric)
                    except Exception:
                        continue

            if not metrics:
                return {"error": f"No metrics in the last {hours} hours"}

            # Calculate stats
            selection_metrics = [m for m in metrics if "elements_selected" in m]
            query_metrics = [m for m in metrics if m.get("type") == "query_result"]

            total_selections = len(selection_metrics)
            successful_selections = sum(1 for m in selection_metrics if m.get("success", True))

            avg_elements = (
                sum(m["elements_selected"] for m in selection_metrics) / total_selections
                if total_selections > 0
                else 0
            )

            avg_time = (
                sum(m["selection_time_ms"] for m in selection_metrics) / total_selections
                if total_selections > 0
                else 0
            )

            avg_similarity = (
                sum(m["avg_similarity"] for m in selection_metrics) / total_selections
                if total_selections > 0
                else 0
            )

            total_queries = len(query_metrics)
            successful_queries = sum(1 for m in query_metrics if m.get("cypher_success", True))

            return {
                "period_hours": hours,
                "total_selections": total_selections,
                "successful_selections": successful_selections,
                "success_rate": (
                    round(successful_selections / total_selections * 100, 1)
                    if total_selections > 0
                    else 0
                ),
                "avg_elements_selected": round(avg_elements, 1),
                "avg_selection_time_ms": round(avg_time, 1),
                "avg_similarity_score": round(avg_similarity, 3),
                "total_queries": total_queries,
                "successful_queries": successful_queries,
                "query_success_rate": (
                    round(successful_queries / total_queries * 100, 1) if total_queries > 0 else 0
                ),
            }

        except Exception as exc:
            logger.exception("Failed to calculate summary stats")
            return {"error": str(exc)}


# Singleton instance
_metrics_collector: Optional[SchemaMetricsCollector] = None


def get_metrics_collector() -> SchemaMetricsCollector:
    """Get or create singleton metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = SchemaMetricsCollector()
    return _metrics_collector

