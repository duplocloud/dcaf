# Discovery Panel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable DCAF agents to emit graph data (nodes/edges) to the UI's Discovery panel, with automatic Neo4j interception, explicit `emit_discovery()` API, and @mentions support.

**Architecture:** New `dcaf/core/discovery.py` module holds models, context var queue, and neo4j parser. `DiscoveryEvent` added to stream event schemas. Agno adapter detects `Neo4jTools` and installs a tool hook that captures results and queues discovery payloads. `agent.py` updated to pass through Pydantic server events. ServerAdapter extracts mentions from requests and injects them into LLM context.

**Tech Stack:** Python 3.11+, Pydantic, contextvars, Agno SDK tool_hooks

**Design doc:** `docs/plans/2026-02-26-discovery-panel-design.md`

---

### Task 1: Discovery Models and Context Var

**Files:**
- Create: `dcaf/core/discovery.py`
- Test: `tests/core/test_discovery.py`

**Step 1: Write failing tests for discovery models**

```python
# tests/core/test_discovery.py
import pytest

from dcaf.core.discovery import (
    DiscoveryEdge,
    DiscoveryNode,
    DiscoveryPayload,
)


class TestDiscoveryModels:
    def test_discovery_node_creation(self):
        node = DiscoveryNode(
            id="n1",
            labels=["Service"],
            properties={"name": "web-api", "status": "running"},
        )
        assert node.id == "n1"
        assert node.labels == ["Service"]
        assert node.properties["name"] == "web-api"

    def test_discovery_edge_creation(self):
        edge = DiscoveryEdge(
            id="e1",
            type="CONNECTS_TO",
            startNode="n1",
            endNode="n2",
            properties={"port": 5432},
        )
        assert edge.id == "e1"
        assert edge.type == "CONNECTS_TO"
        assert edge.startNode == "n1"
        assert edge.endNode == "n2"

    def test_discovery_edge_empty_properties_default(self):
        edge = DiscoveryEdge(id="e1", type="RUNS_ON", startNode="n1", endNode="n2")
        assert edge.properties == {}

    def test_discovery_payload_creation(self):
        payload = DiscoveryPayload(
            nodes=[DiscoveryNode(id="n1", labels=["Service"], properties={"name": "web-api"})],
            edges=[
                DiscoveryEdge(
                    id="e1", type="CONNECTS_TO", startNode="n1", endNode="n2", properties={}
                )
            ],
        )
        assert len(payload.nodes) == 1
        assert len(payload.edges) == 1

    def test_discovery_payload_serialization_matches_ui_format(self):
        payload = DiscoveryPayload(
            nodes=[
                DiscoveryNode(
                    id="n1",
                    labels=["Service"],
                    properties={"name": "web-api", "replicas": 3},
                )
            ],
            edges=[
                DiscoveryEdge(
                    id="e1",
                    type="CONNECTS_TO",
                    startNode="n1",
                    endNode="n2",
                    properties={"port": 5432},
                )
            ],
        )
        data = payload.model_dump()
        assert data == {
            "nodes": [
                {"id": "n1", "labels": ["Service"], "properties": {"name": "web-api", "replicas": 3}}
            ],
            "edges": [
                {
                    "id": "e1",
                    "type": "CONNECTS_TO",
                    "startNode": "n1",
                    "endNode": "n2",
                    "properties": {"port": 5432},
                }
            ],
        }
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_discovery.py::TestDiscoveryModels -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dcaf.core.discovery'`

**Step 3: Write minimal implementation**

```python
# dcaf/core/discovery.py
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_discovery.py::TestDiscoveryModels -v`
Expected: PASS (all 5 tests)

**Step 5: Commit**

```bash
git add dcaf/core/discovery.py tests/core/test_discovery.py
git commit -m "feat(discovery): add discovery models

Add DiscoveryNode, DiscoveryEdge, and DiscoveryPayload Pydantic models
matching the UI's expected SSE format for the Discovery panel.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 2: emit_discovery() and Context Var Queue

**Files:**
- Modify: `dcaf/core/discovery.py`
- Test: `tests/core/test_discovery.py`

**Step 1: Write failing tests for emit_discovery and queue**

```python
# Append to tests/core/test_discovery.py

from dcaf.core.discovery import (
    drain_discovery_queue,
    emit_discovery,
    reset_discovery_queue,
)


class TestEmitDiscovery:
    def setup_method(self):
        reset_discovery_queue()

    def test_emit_discovery_queues_payload(self):
        emit_discovery(
            nodes=[{"id": "n1", "labels": ["Service"], "properties": {"name": "web-api"}}],
            edges=[],
        )
        payloads = drain_discovery_queue()
        assert len(payloads) == 1
        assert payloads[0].nodes[0].id == "n1"

    def test_emit_discovery_multiple_calls_queue_in_order(self):
        emit_discovery(
            nodes=[{"id": "n1", "labels": ["Service"], "properties": {"name": "first"}}],
            edges=[],
        )
        emit_discovery(
            nodes=[{"id": "n2", "labels": ["Database"], "properties": {"name": "second"}}],
            edges=[],
        )
        payloads = drain_discovery_queue()
        assert len(payloads) == 2
        assert payloads[0].nodes[0].properties["name"] == "first"
        assert payloads[1].nodes[0].properties["name"] == "second"

    def test_drain_clears_queue(self):
        emit_discovery(
            nodes=[{"id": "n1", "labels": ["Service"], "properties": {"name": "web-api"}}],
            edges=[],
        )
        drain_discovery_queue()
        payloads = drain_discovery_queue()
        assert len(payloads) == 0

    def test_drain_empty_queue_returns_empty_list(self):
        payloads = drain_discovery_queue()
        assert payloads == []

    def test_emit_discovery_with_edges(self):
        emit_discovery(
            nodes=[
                {"id": "n1", "labels": ["Service"], "properties": {"name": "web-api"}},
                {"id": "n2", "labels": ["Database"], "properties": {"name": "postgres"}},
            ],
            edges=[
                {
                    "id": "e1",
                    "type": "CONNECTS_TO",
                    "startNode": "n1",
                    "endNode": "n2",
                    "properties": {"port": 5432},
                }
            ],
        )
        payloads = drain_discovery_queue()
        assert len(payloads) == 1
        assert len(payloads[0].nodes) == 2
        assert len(payloads[0].edges) == 1
        assert payloads[0].edges[0].type == "CONNECTS_TO"

    def test_reset_clears_queue(self):
        emit_discovery(
            nodes=[{"id": "n1", "labels": ["Service"], "properties": {"name": "web-api"}}],
            edges=[],
        )
        reset_discovery_queue()
        payloads = drain_discovery_queue()
        assert payloads == []
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_discovery.py::TestEmitDiscovery -v`
Expected: FAIL with `ImportError: cannot import name 'emit_discovery'`

**Step 3: Add context var queue and emit_discovery to dcaf/core/discovery.py**

Append to `dcaf/core/discovery.py`:

```python
import contextvars
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# Context Var Queue
# =============================================================================

_discovery_queue: contextvars.ContextVar[list[DiscoveryPayload]] = contextvars.ContextVar(
    "discovery_queue", default=[]
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
    queue = _discovery_queue.get([])
    # ContextVar default returns the same list object, so copy-on-first-write
    if not queue:
        queue = [payload]
        _discovery_queue.set(queue)
    else:
        queue.append(payload)
    logger.debug(f"Discovery payload queued: {len(payload.nodes)} nodes, {len(payload.edges)} edges")


def drain_discovery_queue() -> list[DiscoveryPayload]:
    """
    Drain all pending discovery payloads from the queue.

    Returns the list and clears the queue. Called by the streaming
    pipeline after tool completions.
    """
    queue = _discovery_queue.get([])
    if not queue:
        return []
    payloads = list(queue)
    _discovery_queue.set([])
    return payloads


def reset_discovery_queue() -> None:
    """Reset the discovery queue. Used in tests."""
    _discovery_queue.set([])
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_discovery.py -v`
Expected: PASS (all 11 tests)

**Step 5: Commit**

```bash
git add dcaf/core/discovery.py tests/core/test_discovery.py
git commit -m "feat(discovery): add emit_discovery() and context var queue

Provides emit_discovery() for tools/interceptors to push graph data,
and drain_discovery_queue() for the streaming pipeline to consume it.
Uses contextvars for async-safe per-request isolation.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 3: DiscoveryEvent Stream Event

**Files:**
- Modify: `dcaf/core/schemas/events.py:93-97`
- Test: `tests/core/test_discovery.py`

**Step 1: Write failing test for DiscoveryEvent**

```python
# Append to tests/core/test_discovery.py

from dcaf.core.schemas.events import DiscoveryEvent


class TestDiscoveryEvent:
    def test_discovery_event_type(self):
        event = DiscoveryEvent(
            discovery=DiscoveryPayload(
                nodes=[DiscoveryNode(id="n1", labels=["Service"], properties={"name": "web-api"})],
                edges=[],
            )
        )
        assert event.type == "discovery"

    def test_discovery_event_serialization_matches_ui_format(self):
        event = DiscoveryEvent(
            discovery=DiscoveryPayload(
                nodes=[
                    DiscoveryNode(
                        id="n1",
                        labels=["Service"],
                        properties={"name": "web-api", "status": "running"},
                    )
                ],
                edges=[
                    DiscoveryEdge(
                        id="e1",
                        type="CONNECTS_TO",
                        startNode="n1",
                        endNode="n2",
                        properties={"port": 5432},
                    )
                ],
            )
        )
        data = event.model_dump()
        assert data["type"] == "discovery"
        assert "discovery" in data
        assert data["discovery"]["nodes"][0]["id"] == "n1"
        assert data["discovery"]["edges"][0]["type"] == "CONNECTS_TO"

    def test_discovery_event_json_serialization(self):
        """Verify model_dump_json() produces valid JSON the server can stream."""
        event = DiscoveryEvent(
            discovery=DiscoveryPayload(
                nodes=[DiscoveryNode(id="n1", labels=["Host"], properties={"name": "worker-1"})],
                edges=[],
            )
        )
        import json

        json_str = event.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["type"] == "discovery"
        assert parsed["discovery"]["nodes"][0]["properties"]["name"] == "worker-1"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_discovery.py::TestDiscoveryEvent -v`
Expected: FAIL with `ImportError: cannot import name 'DiscoveryEvent'`

**Step 3: Add DiscoveryEvent to dcaf/core/schemas/events.py**

At the top of `dcaf/core/schemas/events.py`, add to imports:

```python
from ..discovery import DiscoveryPayload
```

Before the comment on line 95, add:

```python
class DiscoveryEvent(StreamEvent):
    """Graph data for the Discovery panel (nodes and edges)."""

    type: Literal["discovery"] = "discovery"
    discovery: DiscoveryPayload
```

Update the comment at the bottom:

```python
# Total event types: 11
# They are: executed_commands, executed_tool_calls, text_delta, tool_calls, commands, approvals, executed_approvals, done, error, intermittent_update, discovery
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_discovery.py -v`
Expected: PASS (all 14 tests)

**Step 5: Run full test suite to check for regressions**

Run: `pytest tests/core/ -v`
Expected: PASS

**Step 6: Commit**

```bash
git add dcaf/core/schemas/events.py tests/core/test_discovery.py
git commit -m "feat(discovery): add DiscoveryEvent to stream event schemas

DiscoveryEvent wraps DiscoveryPayload and serializes to the format
the UI expects: {type: 'discovery', discovery: {nodes: [...], edges: [...]}}.
Flows through the existing NDJSON streaming pipeline automatically.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 4: Agent.py Passthrough for Server Events

**Files:**
- Modify: `dcaf/core/agent.py:1070-1131`
- Test: `tests/core/test_discovery.py`

The Agno adapter yields `CoreStreamEvent` (dataclass from `responses.py`), and `agent.py:_convert_stream_event` converts them to Pydantic server events. For discovery, the adapter will yield `DiscoveryEvent` (Pydantic) directly. We need `_convert_stream_event` to pass through Pydantic server events instead of dropping them.

**Step 1: Write failing test**

```python
# Append to tests/core/test_discovery.py

class TestAgentDiscoveryPassthrough:
    def test_convert_stream_event_passes_through_server_events(self):
        """DiscoveryEvent (Pydantic) should pass through _convert_stream_event unchanged."""
        from dcaf.core.agent import Agent
        from dcaf.core.schemas.events import StreamEvent as ServerStreamEvent

        agent = Agent(tools=[])
        event = DiscoveryEvent(
            discovery=DiscoveryPayload(
                nodes=[DiscoveryNode(id="n1", labels=["Service"], properties={"name": "api"})],
                edges=[],
            )
        )
        pending: list = []
        result = agent._convert_stream_event(event, pending)
        assert result is event
        assert isinstance(result, ServerStreamEvent)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_discovery.py::TestAgentDiscoveryPassthrough -v`
Expected: FAIL — `_convert_stream_event` returns `None` for unrecognized types

**Step 3: Update _convert_stream_event in dcaf/core/agent.py**

Add at the top of `_convert_stream_event` method (around line 1075, before the `CoreStreamEvent` check):

```python
# Pass through server-level Pydantic events (e.g., DiscoveryEvent)
if isinstance(internal_event, ServerStreamEvent):
    return internal_event
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_discovery.py::TestAgentDiscoveryPassthrough -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest tests/core/ -v`
Expected: PASS

**Step 6: Commit**

```bash
git add dcaf/core/agent.py tests/core/test_discovery.py
git commit -m "feat(discovery): pass through Pydantic server events in agent stream

Update _convert_stream_event to detect and pass through Pydantic
StreamEvent subclasses (like DiscoveryEvent) that the Agno adapter
yields directly, instead of dropping them as unrecognized types.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 5: Neo4j Result Parser

**Files:**
- Modify: `dcaf/core/discovery.py`
- Test: `tests/core/test_discovery.py`

The `run_cypher_query` tool returns `session.run(query).data()` — a list of dicts. Neo4j's `.data()` method serializes Node objects as dicts of their properties. The parser needs to extract nodes and relationships from these flattened results, generating stable IDs.

**Step 1: Write failing tests for neo4j parser**

```python
# Append to tests/core/test_discovery.py

from dcaf.core.discovery import neo4j_result_to_discovery


class TestNeo4jResultParser:
    def test_parse_simple_node_results(self):
        """Parse a result from MATCH (n:Service) RETURN n."""
        neo4j_data = [
            {"n": {"name": "web-api", "status": "running"}},
            {"n": {"name": "postgres", "engine": "PostgreSQL 15"}},
        ]
        payload = neo4j_result_to_discovery(neo4j_data)
        assert len(payload.nodes) == 2
        assert payload.nodes[0].properties["name"] == "web-api"
        assert payload.nodes[1].properties["name"] == "postgres"

    def test_nodes_get_deterministic_ids(self):
        """Same data should produce the same ID."""
        neo4j_data = [{"n": {"name": "web-api"}}]
        payload1 = neo4j_result_to_discovery(neo4j_data)
        payload2 = neo4j_result_to_discovery(neo4j_data)
        assert payload1.nodes[0].id == payload2.nodes[0].id

    def test_empty_result_returns_empty_payload(self):
        payload = neo4j_result_to_discovery([])
        assert payload.nodes == []
        assert payload.edges == []

    def test_string_result_returns_empty_payload(self):
        """If result is a plain string (e.g., error), return empty."""
        payload = neo4j_result_to_discovery("No results found")
        assert payload.nodes == []
        assert payload.edges == []

    def test_nodes_use_name_property_for_label_if_no_labels(self):
        """When neo4j labels are lost in .data(), use 'Node' as default label."""
        neo4j_data = [{"n": {"name": "web-api"}}]
        payload = neo4j_result_to_discovery(neo4j_data)
        assert len(payload.nodes[0].labels) >= 1

    def test_deduplicates_nodes(self):
        """Same node appearing in multiple rows should be deduplicated."""
        neo4j_data = [
            {"n": {"name": "web-api"}, "m": {"name": "postgres"}},
            {"n": {"name": "web-api"}, "m": {"name": "redis"}},
        ]
        payload = neo4j_result_to_discovery(neo4j_data)
        names = [n.properties.get("name") for n in payload.nodes]
        assert len(set(names)) == len(names)  # No duplicates
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_discovery.py::TestNeo4jResultParser -v`
Expected: FAIL with `ImportError: cannot import name 'neo4j_result_to_discovery'`

**Step 3: Implement neo4j_result_to_discovery in dcaf/core/discovery.py**

```python
import hashlib
import json


def neo4j_result_to_discovery(result: Any) -> DiscoveryPayload:
    """
    Convert a neo4j run_cypher_query result to a DiscoveryPayload.

    The result from Neo4jTools.run_cypher_query() is typically a list of dicts
    from neo4j's session.run(query).data(). Each dict represents a row, where
    values can be node dicts (properties only — id/labels lost by .data()).

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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_discovery.py::TestNeo4jResultParser -v`
Expected: PASS (all 6 tests)

**Step 5: Commit**

```bash
git add dcaf/core/discovery.py tests/core/test_discovery.py
git commit -m "feat(discovery): add neo4j result parser

Converts run_cypher_query output (list of dicts from neo4j .data())
into DiscoveryPayload with deterministic node IDs and deduplication.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 6: Agno Adapter — Neo4j Detection and Tool Hook

**Files:**
- Modify: `dcaf/core/adapters/outbound/agno/adapter.py:630-677` (`_create_agent_async`)
- Modify: `dcaf/core/adapters/outbound/agno/adapter.py:724-750` (`_prepare_tools_with_defaults`)
- Test: `tests/core/test_discovery.py`

The adapter needs to: (1) detect Neo4jTools in the tools list, (2) install a tool hook that captures neo4j results, and (3) pass `tool_hooks` to the AgnoAgent constructor.

**Step 1: Write failing tests**

```python
# Append to tests/core/test_discovery.py

class TestNeo4jToolDetection:
    def test_has_neo4j_tools_returns_true_for_neo4j_toolkit(self):
        """Adapter should detect Neo4jTools in the tools list."""
        from agno.tools.toolkit import Toolkit as AgnoToolkit

        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        class FakeNeo4jTools(AgnoToolkit):
            def __init__(self):
                super().__init__(name="neo4j_tools")

        adapter = AgnoAdapter(model_id="test", provider="bedrock")
        assert adapter._has_neo4j_tools([FakeNeo4jTools()]) is True

    def test_has_neo4j_tools_returns_false_for_other_toolkits(self):
        from agno.tools.toolkit import Toolkit as AgnoToolkit

        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        class FakeDuckDbTools(AgnoToolkit):
            def __init__(self):
                super().__init__(name="duckdb_tools")

        adapter = AgnoAdapter(model_id="test", provider="bedrock")
        assert adapter._has_neo4j_tools([FakeDuckDbTools()]) is False

    def test_has_neo4j_tools_returns_false_for_empty_list(self):
        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")
        assert adapter._has_neo4j_tools([]) is False


class TestDiscoveryToolHook:
    def setup_method(self):
        reset_discovery_queue()

    def test_discovery_hook_captures_neo4j_result(self):
        """The tool hook should capture run_cypher_query results into the discovery queue."""
        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")
        hook = adapter._build_discovery_tool_hook()

        # Simulate a neo4j tool call
        def fake_run_cypher_query(**kwargs):
            return [{"n": {"name": "web-api", "status": "running"}}]

        result = hook(
            function_name="run_cypher_query",
            func=fake_run_cypher_query,
            args={"query": "MATCH (n) RETURN n"},
        )

        # Hook should return the result unchanged
        assert result == [{"n": {"name": "web-api", "status": "running"}}]

        # Discovery queue should have a payload
        payloads = drain_discovery_queue()
        assert len(payloads) == 1
        assert payloads[0].nodes[0].properties["name"] == "web-api"

    def test_discovery_hook_ignores_non_neo4j_tools(self):
        """The hook should not capture results from non-neo4j tools."""
        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")
        hook = adapter._build_discovery_tool_hook()

        def fake_other_tool(**kwargs):
            return "some result"

        result = hook(function_name="list_files", func=fake_other_tool, args={})
        assert result == "some result"

        payloads = drain_discovery_queue()
        assert len(payloads) == 0

    def test_discovery_hook_handles_tool_error_gracefully(self):
        """If the neo4j tool raises, the hook should re-raise without queuing."""
        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")
        hook = adapter._build_discovery_tool_hook()

        def failing_tool(**kwargs):
            raise ConnectionError("neo4j down")

        with pytest.raises(ConnectionError):
            hook(function_name="run_cypher_query", func=failing_tool, args={})

        payloads = drain_discovery_queue()
        assert len(payloads) == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_discovery.py::TestNeo4jToolDetection -v`
Expected: FAIL with `AttributeError: 'AgnoAdapter' object has no attribute '_has_neo4j_tools'`

**Step 3: Implement detection and hook in adapter.py**

Add these methods to `AgnoAdapter` class in `dcaf/core/adapters/outbound/agno/adapter.py`:

```python
    # Neo4j tool function names that produce graph data
    _NEO4J_DISCOVERY_TOOLS = {"run_cypher_query"}

    def _has_neo4j_tools(self, tools: list[Any]) -> bool:
        """Check if any tool in the list is a Neo4j toolkit."""
        try:
            from agno.tools.neo4j import Neo4jTools
        except ImportError:
            return False
        return any(isinstance(t, Neo4jTools) for t in tools)

    def _build_discovery_tool_hook(self) -> Any:
        """
        Build an Agno tool_hook that captures Neo4j results for discovery.

        Returns a hook function compatible with Agno's tool_hooks parameter.
        The hook intercepts run_cypher_query results, converts them to
        DiscoveryPayload, and queues them for the streaming pipeline.
        """
        from ....discovery import emit_discovery, neo4j_result_to_discovery

        def discovery_hook(function_name: str, func: Any, args: dict) -> Any:
            result = func(**args)
            if function_name in self._NEO4J_DISCOVERY_TOOLS:
                try:
                    payload = neo4j_result_to_discovery(result)
                    if payload.nodes or payload.edges:
                        emit_discovery(
                            nodes=[n.model_dump() for n in payload.nodes],
                            edges=[e.model_dump() for e in payload.edges],
                        )
                except Exception as e:
                    logger.warning(f"Discovery parsing failed for {function_name}: {e}")
            return result

        return discovery_hook
```

Update `_create_agent_async` (around line 667) to pass `tool_hooks` when Neo4j is detected:

```python
        # Check if neo4j tools are present and build discovery hook
        tool_hooks = None
        if self._has_neo4j_tools(tools):
            tool_hooks = [self._build_discovery_tool_hook()]
            logger.info("Discovery: Neo4j tools detected, installing discovery tool hook")

        # Create the agent
        agent = AgnoAgent(
            model=model,
            instructions=modified_prompt,
            tools=agno_tools if agno_tools else None,
            stream=stream,
            tool_call_limit=self._tool_call_limit,
            skills=agno_skills,
            telemetry=False,
            tool_hooks=tool_hooks,
        )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_discovery.py::TestNeo4jToolDetection tests/core/test_discovery.py::TestDiscoveryToolHook -v`
Expected: PASS (all 6 tests)

**Step 5: Run full test suite**

Run: `pytest tests/core/ -v`
Expected: PASS

**Step 6: Commit**

```bash
git add dcaf/core/adapters/outbound/agno/adapter.py tests/core/test_discovery.py
git commit -m "feat(discovery): auto-detect Neo4jTools and install discovery hook

When Neo4jTools is detected in the tools list, DCAF installs an Agno
tool_hook that captures run_cypher_query results, converts them to
DiscoveryPayload, and queues them for SSE emission. Zero agent-developer
code required.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 7: Drain Discovery Queue in Streaming Pipeline

**Files:**
- Modify: `dcaf/core/adapters/outbound/agno/adapter.py:417-442` (`invoke_stream`)
- Test: `tests/core/test_discovery.py`

After each `TOOL_USE_END` event in the streaming loop, drain the discovery queue and yield `DiscoveryEvent`s.

**Step 1: Write failing test**

```python
# Append to tests/core/test_discovery.py

import asyncio


class TestStreamDiscoveryEmission:
    def test_invoke_stream_yields_discovery_after_tool_end(self):
        """After a TOOL_USE_END event, pending discovery payloads should be yielded."""
        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter
        from dcaf.core.application.dto.responses import StreamEvent as CoreStreamEvent
        from dcaf.core.application.dto.responses import StreamEventType

        reset_discovery_queue()

        # Pre-queue a discovery payload (simulating the tool hook having run)
        emit_discovery(
            nodes=[{"id": "n1", "labels": ["Service"], "properties": {"name": "web-api"}}],
            edges=[],
        )

        adapter = AgnoAdapter(model_id="test", provider="bedrock")

        # The _emit_pending_discovery method should yield DiscoveryEvents
        events = list(adapter._emit_pending_discovery())
        assert len(events) == 1
        assert events[0].type == "discovery"
        assert events[0].discovery.nodes[0].id == "n1"

    def test_emit_pending_discovery_returns_nothing_when_empty(self):
        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        reset_discovery_queue()

        adapter = AgnoAdapter(model_id="test", provider="bedrock")
        events = list(adapter._emit_pending_discovery())
        assert events == []
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_discovery.py::TestStreamDiscoveryEmission -v`
Expected: FAIL with `AttributeError: 'AgnoAdapter' object has no attribute '_emit_pending_discovery'`

**Step 3: Add _emit_pending_discovery and update invoke_stream**

Add method to `AgnoAdapter`:

```python
    def _emit_pending_discovery(self) -> list[Any]:
        """
        Drain the discovery queue and return DiscoveryEvents.

        Called after TOOL_USE_END events in the streaming pipeline.
        """
        from ....discovery import drain_discovery_queue
        from ....schemas.events import DiscoveryEvent

        payloads = drain_discovery_queue()
        events = []
        for payload in payloads:
            events.append(DiscoveryEvent(discovery=payload))
            logger.info(
                f"Discovery: Emitting {len(payload.nodes)} nodes, {len(payload.edges)} edges"
            )
        return events
```

In `invoke_stream()`, after `yield stream_event` (around line 429), add discovery emission:

```python
                if stream_event:
                    yield stream_event

                    # After tool completion, emit any pending discovery events
                    if stream_event.event_type == StreamEventType.TOOL_USE_END:
                        for discovery_event in self._emit_pending_discovery():
                            yield discovery_event
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_discovery.py::TestStreamDiscoveryEmission -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest tests/core/ -v`
Expected: PASS

**Step 6: Commit**

```bash
git add dcaf/core/adapters/outbound/agno/adapter.py tests/core/test_discovery.py
git commit -m "feat(discovery): drain discovery queue in streaming pipeline

After each TOOL_USE_END event, drain pending discovery payloads from
the context var queue and yield DiscoveryEvents in the SSE stream.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 8: Mentions Extraction and Context Injection

**Files:**
- Modify: `dcaf/core/adapters/inbound/server_adapter.py:242-289`
- Test: `tests/core/test_discovery.py`

**Step 1: Write failing tests for mentions handling**

```python
# Append to tests/core/test_discovery.py

class TestMentionsExtraction:
    def _make_adapter(self):
        """Create a ServerAdapter with a minimal mock agent."""
        from unittest.mock import AsyncMock, MagicMock

        from dcaf.core.adapters.inbound.server_adapter import ServerAdapter

        mock_agent = MagicMock()
        mock_agent.run_stream = AsyncMock(return_value=iter([]))
        mock_agent.tools = []
        return ServerAdapter(mock_agent)

    def test_extract_mentions_from_user_message(self):
        adapter = self._make_adapter()
        messages = [
            {
                "role": "user",
                "content": "tell me about @Service:web-api",
                "mentions": [
                    {
                        "nodeId": "n1",
                        "labels": ["Service"],
                        "properties": {"name": "web-api", "status": "running"},
                    }
                ],
            }
        ]
        mentions = adapter._extract_mentions(messages)
        assert len(mentions) == 1
        assert mentions[0]["nodeId"] == "n1"
        assert mentions[0]["labels"] == ["Service"]

    def test_extract_mentions_returns_empty_when_no_mentions(self):
        adapter = self._make_adapter()
        messages = [{"role": "user", "content": "hello"}]
        mentions = adapter._extract_mentions(messages)
        assert mentions == []

    def test_extract_mentions_from_latest_user_message(self):
        adapter = self._make_adapter()
        messages = [
            {
                "role": "user",
                "content": "old message",
                "mentions": [{"nodeId": "old", "labels": ["X"], "properties": {}}],
            },
            {"role": "assistant", "content": "response"},
            {
                "role": "user",
                "content": "new message",
                "mentions": [{"nodeId": "new", "labels": ["Y"], "properties": {}}],
            },
        ]
        mentions = adapter._extract_mentions(messages)
        assert len(mentions) == 1
        assert mentions[0]["nodeId"] == "new"

    def test_inject_mentions_appends_to_last_user_message(self):
        adapter = self._make_adapter()
        core_messages = [{"role": "user", "content": "tell me about @Service:web-api"}]
        mentions = [
            {
                "nodeId": "n1",
                "labels": ["Service"],
                "properties": {"name": "web-api", "status": "running", "replicas": 3},
            }
        ]
        adapter._inject_mentions(core_messages, mentions)
        content = core_messages[0]["content"]
        assert "Referenced nodes:" in content
        assert "Service" in content
        assert "web-api" in content

    def test_inject_mentions_noop_when_empty(self):
        adapter = self._make_adapter()
        core_messages = [{"role": "user", "content": "hello"}]
        adapter._inject_mentions(core_messages, [])
        assert core_messages[0]["content"] == "hello"

    def test_mentions_added_to_platform_context(self):
        adapter = self._make_adapter()
        messages = [
            {
                "role": "user",
                "content": "tell me about @Service:web-api",
                "platform_context": {"tenant_id": "t1"},
                "mentions": [
                    {
                        "nodeId": "n1",
                        "labels": ["Service"],
                        "properties": {"name": "web-api"},
                    }
                ],
            }
        ]
        context = adapter._extract_platform_context(messages)
        mentions = adapter._extract_mentions(messages)
        context["mentions"] = mentions
        assert context["tenant_id"] == "t1"
        assert len(context["mentions"]) == 1
        assert context["mentions"][0]["nodeId"] == "n1"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_discovery.py::TestMentionsExtraction -v`
Expected: FAIL with `AttributeError: 'ServerAdapter' object has no attribute '_extract_mentions'`

**Step 3: Add mentions methods to ServerAdapter**

Add to `ServerAdapter` class in `dcaf/core/adapters/inbound/server_adapter.py`:

```python
    def _extract_mentions(self, messages_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Extract mentions from the latest user message.

        Mentions are graph nodes that the user @mentioned in the chat input.
        The UI sends them as a top-level 'mentions' field on the user message.
        """
        for msg in reversed(messages_list):
            if msg.get("role") == "user":
                mentions = msg.get("mentions", [])
                if mentions and isinstance(mentions, list):
                    return mentions
        return []

    def _inject_mentions(
        self,
        core_messages: list[dict[str, Any]],
        mentions: list[dict[str, Any]],
    ) -> None:
        """
        Inject mention details into the conversation for LLM context.

        Appends structured node information to the last user message
        so the LLM can reason about the referenced nodes.
        """
        if not mentions:
            return

        parts = []
        for mention in mentions:
            labels = mention.get("labels", [])
            label = labels[0] if labels else "Node"
            props = mention.get("properties", {})
            name = props.get("name", mention.get("nodeId", "unknown"))
            # Format properties excluding name (already shown)
            other_props = {k: v for k, v in props.items() if k != "name"}
            prop_str = ", ".join(f"{k}={v}" for k, v in other_props.items())
            if prop_str:
                parts.append(f'- {label} "{name}": {prop_str}')
            else:
                parts.append(f'- {label} "{name}"')

        mention_text = "Referenced nodes:\n" + "\n".join(parts)

        if core_messages and core_messages[-1]["role"] == "user":
            core_messages[-1]["content"] += "\n\n" + mention_text
        else:
            core_messages.append({"role": "user", "content": mention_text})
```

Update `invoke_stream()` (around line 165-169) to extract mentions and inject them:

```python
        # Extract mentions from user message
        mentions = self._extract_mentions(messages_list)

        # Merge top-level request fields into context (platform_context takes precedence)
        request_fields: dict[str, Any] = messages.get("_request_fields", {})
        context = {**request_fields, **platform_context} if request_fields else platform_context

        # Add mentions to context for programmatic access in tools
        if mentions:
            context["mentions"] = mentions
```

After `self._inject_execution_results(...)` call (around line 190), add:

```python
        # Inject mention details for LLM context
        self._inject_mentions(core_messages, mentions)
```

Do the same in `invoke()` (the non-streaming path, around line 110):

```python
        # Extract and inject mentions
        mentions = self._extract_mentions(messages_list)
        if mentions:
            context["mentions"] = mentions
        self._inject_mentions(core_messages, mentions)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_discovery.py::TestMentionsExtraction -v`
Expected: PASS (all 7 tests)

**Step 5: Run full test suite**

Run: `pytest tests/core/ -v`
Expected: PASS

**Step 6: Commit**

```bash
git add dcaf/core/adapters/inbound/server_adapter.py tests/core/test_discovery.py
git commit -m "feat(discovery): handle @mentions from UI

Extract mentions from user messages, inject node details into LLM
context for natural reasoning, and pass mentions in platform_context
for programmatic access in tools.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 9: Lint, Type Check, and Final Verification

**Files:**
- All modified files

**Step 1: Run linter**

Run: `ruff check dcaf/core/discovery.py dcaf/core/schemas/events.py dcaf/core/agent.py dcaf/core/adapters/outbound/agno/adapter.py dcaf/core/adapters/inbound/server_adapter.py`

Fix any issues.

**Step 2: Run formatter**

Run: `ruff format dcaf/core/discovery.py dcaf/core/schemas/events.py dcaf/core/agent.py dcaf/core/adapters/outbound/agno/adapter.py dcaf/core/adapters/inbound/server_adapter.py`

**Step 3: Run type checker**

Run: `mypy dcaf/core/discovery.py dcaf/core/schemas/events.py`

Fix any type errors.

**Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: PASS (excluding known channel_routing failures)

**Step 5: Run import linter**

Run: `lint-imports`
Expected: PASS

**Step 6: Run code health check**

Run: `python scripts/check_code_health.py`
Expected: PASS

**Step 7: Commit any fixes**

```bash
git add -A
git commit -m "chore: fix lint, format, and type issues for discovery feature

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
