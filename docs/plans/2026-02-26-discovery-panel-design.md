# Discovery Panel — Design Document

**Date**: 2026-02-26
**Branch**: feature/discovery

## Overview

The Discovery feature enables DCAF agents to emit graph data (nodes and edges) to the UI's
Discovery panel via SSE streaming. It supports two modes:

1. **Automatic**: DCAF detects registered `Neo4jTools` and automatically converts `run_cypher_query`
   results into discovery events — zero agent-developer code required.
2. **Explicit**: Agent developers call `emit_discovery()` from any tool or interceptor to push
   custom graph data.

The UI can also send `@mentions` of graph nodes back to the agent. DCAF handles these by injecting
mention details into the LLM context and making them available as structured data.

## Discovery Event Schema

A new `DiscoveryEvent` stream event emitted over SSE/NDJSON:

```json
{
  "type": "discovery",
  "discovery": {
    "nodes": [
      {
        "id": "string",
        "labels": ["string"],
        "properties": {"name": "string", "...": "any"}
      }
    ],
    "edges": [
      {
        "id": "string",
        "type": "string",
        "startNode": "string",
        "endNode": "string",
        "properties": {}
      }
    ]
  }
}
```

### Pydantic Models

```python
class DiscoveryNode(BaseModel):
    id: str
    labels: list[str]
    properties: dict[str, Any]

class DiscoveryEdge(BaseModel):
    id: str
    type: str
    startNode: str
    endNode: str
    properties: dict[str, Any] = Field(default_factory=dict)

class DiscoveryPayload(BaseModel):
    nodes: list[DiscoveryNode]
    edges: list[DiscoveryEdge]

class DiscoveryEvent(StreamEvent):
    type: Literal["discovery"] = "discovery"
    discovery: DiscoveryPayload
```

### Behavior

- The Discovery panel auto-opens on the first `discovery` event.
- Each subsequent event replaces the entire graph (not append).
- Orphan nodes (no matching edges) are rendered.
- Edges referencing non-existent node IDs are silently filtered by the UI.

## Automatic Neo4j Interception

### Detection

During `_convert_tools_to_agno()`, DCAF checks if any tool is a `Neo4jTools` instance using a
conditional import:

```python
try:
    from agno.tools.neo4j import Neo4jTools
except ImportError:
    Neo4jTools = None
```

If detected, DCAF installs an Agno `tool_hook` on the agent.

### Hook Flow

```
LLM calls run_cypher_query
  -> Agno tool_hook fires
    -> calls run_cypher_query(**args)
    -> captures result (list of dicts from neo4j .data())
    -> neo4j_result_to_discovery(result) -> DiscoveryPayload
    -> stores payload in contextvars queue
  -> returns result to Agno (unchanged)
-> Agno emits ToolCallCompletedEvent
-> DCAF yields TOOL_USE_END stream event
-> DCAF drains discovery queue -> yields DiscoveryEvent
-> UI auto-opens Discovery panel
```

### Neo4j Result Parsing

The `run_cypher_query` tool returns `session.run(query).data()` — a list of dicts where neo4j
Node/Relationship objects are flattened to their properties. The parser (`neo4j_result_to_discovery`)
extracts graph structure from these results, generating deterministic IDs and inferring labels
from the data. Implementation will investigate the actual metadata available in the Agno event
and neo4j driver result to maximize fidelity.

## Explicit `emit_discovery()` API

### Usage

```python
from dcaf.core.discovery import emit_discovery

@tool
def analyze_topology(platform_context: dict) -> str:
    nodes = [
        {"id": "svc-1", "labels": ["Service"], "properties": {"name": "web-api"}},
        {"id": "db-1", "labels": ["Database"], "properties": {"name": "postgres"}},
    ]
    edges = [
        {"id": "e1", "type": "CONNECTS_TO", "startNode": "svc-1", "endNode": "db-1",
         "properties": {"port": 5432}},
    ]
    emit_discovery(nodes=nodes, edges=edges)
    return "Topology analysis complete"
```

### Mechanism

`emit_discovery()` pushes a `DiscoveryPayload` onto a `contextvars.ContextVar` queue scoped to
the current streaming request. The streaming pipeline in `invoke_stream()` drains this queue after
each tool completion and yields `DiscoveryEvent`s.

Using `contextvars`:
- No special context object passed into tools.
- Thread/async-safe — each request gets its own queue.
- Works from anywhere in the call stack (tools, interceptors, nested functions).

### Module

`dcaf/core/discovery.py` — contains `emit_discovery()`, discovery models, the context var, and the
`neo4j_result_to_discovery()` parser.

## Mentions Handling (UI -> Agent)

### Request Format

The UI sends `mentions` on the user message when nodes are @mentioned:

```json
{
  "content": "tell me more about @Service:web-api",
  "mentions": [
    {
      "nodeId": "n1",
      "labels": ["Service"],
      "properties": {"name": "web-api", "status": "running", "replicas": 3}
    }
  ]
}
```

### Context Injection (Automatic)

In `ServerAdapter`, DCAF detects the `mentions` array and augments the user message content with
structured mention details for the LLM:

```
Referenced nodes:
- Service "web-api": status=running, replicas=3, image=nginx:1.25
```

This follows the same pattern as existing executed tool call injection in
`_inject_execution_results()`.

### Structured Data (Programmatic Access)

The `mentions` array is preserved in `platform_context` so tools and interceptors can access
the raw mention objects:

```python
@tool
def explore_connections(platform_context: dict) -> str:
    mentions = platform_context.get("mentions", [])
    for mention in mentions:
        node_id = mention["nodeId"]
        # Query neo4j for connected nodes...
```

## Files Changed

| File | Change |
|------|--------|
| `dcaf/core/discovery.py` | **New** — `emit_discovery()`, models, context var, neo4j parser |
| `dcaf/core/schemas/events.py` | Add `DiscoveryEvent` wrapping `DiscoveryPayload` |
| `dcaf/core/adapters/outbound/agno/adapter.py` | Detect `Neo4jTools`, install tool hook, drain discovery queue in `invoke_stream()` |
| `dcaf/core/adapters/inbound/server_adapter.py` | Extract mentions, inject into message content, pass in platform_context |
| Tests | Discovery models, neo4j parser, tool hook wiring, mentions extraction, `emit_discovery()` |

## Files Unchanged

- `dcaf/core/server.py` — already serializes any `StreamEvent` subclass via `model_dump_json()`
- `dcaf/core/agent.py` — discovery is handled at the adapter layer
- `dcaf/core/events.py` — internal event system doesn't need new types

## Dependencies

- No new external dependencies.
- `Neo4jTools` detection uses conditional import (no hard dependency on `agno[neo4j]`).
- `contextvars` is Python stdlib.
