# Tracing and Observability

DCAF provides built-in support for distributed tracing and observability, allowing you to track requests through the entire agent execution pipeline from your application to the LLM provider.

---

## Overview

Tracing in DCAF is built around four key identifiers that flow through the system:

| Field | Purpose | Example |
|-------|---------|---------|
| `user_id` | Identifies the user making requests | `"user-123"` |
| `session_id` | Groups related runs into a session | `"session-abc"` |
| `run_id` | Unique identifier for a single execution | `"run-xyz"` |
| `request_id` | HTTP request correlation ID | `"req-456"` |

These identifiers are:
- Passed to the LLM provider (Agno SDK) for end-to-end tracing
- Included in response metadata for correlation
- Available in logs throughout the execution pipeline
- Compatible with OpenTelemetry and other observability platforms

---

## Quick Start

### Option 1: Via AgentRequest

The simplest way to add tracing is through the `AgentRequest`:

```python
from dcaf.core.application.dto import AgentRequest

request = AgentRequest(
    content="What pods are running?",
    tools=[kubectl_tool],
    # Tracing fields
    user_id="user-123",
    session_id="session-abc",
    run_id="run-xyz",
    request_id="req-456",
)

response = await agent_service.execute(request)

# Tracing IDs are returned in response metadata
print(response.metadata)
# {'run_id': 'run-xyz', 'session_id': 'session-abc', 'user_id': 'user-123', 'request_id': 'req-456'}
```

### Option 2: Via PlatformContext

For more control, use the `PlatformContext` value object:

```python
from dcaf.core.domain.value_objects import PlatformContext

# Create context with tracing
context = PlatformContext(
    tenant_id="tenant-1",
    tenant_name="acme-corp",
    user_id="user-123",
    session_id="session-abc",
    run_id="run-xyz",
    request_id="req-456",
)

# Or add tracing to an existing context
context = PlatformContext.from_dict({"tenant_id": "tenant-1"})
context = context.with_tracing(
    user_id="user-123",
    session_id="session-abc",
    run_id="run-xyz",
)

# Pass as dict in request
request = AgentRequest(
    content="Deploy my app",
    context=context.to_dict(),
    tools=[deploy_tool],
)
```

---

## Tracing Fields

### user_id

Identifies the user making the request. Use this for:
- User-level analytics and quotas
- Audit trails showing who performed actions
- Personalization and context

```python
request = AgentRequest(
    content="Delete the old pods",
    user_id="alice@company.com",  # Or user ID from your auth system
    tools=[kubectl_tool],
)
```

### session_id

Groups related runs into a logical session. Use this for:
- Conversation continuity tracking
- Session-level analytics
- Grouping related agent interactions

```python
# Generate session ID at the start of a conversation
import uuid
session_id = f"session-{uuid.uuid4()}"

# Use it for all requests in the conversation
request1 = AgentRequest(content="What's running?", session_id=session_id, ...)
request2 = AgentRequest(content="Delete pod-1", session_id=session_id, ...)
```

### run_id

Unique identifier for a single agent execution. Use this for:
- Correlating logs across services
- Debugging specific executions
- Linking to external tracing systems

```python
import uuid

request = AgentRequest(
    content="Scale deployment to 5 replicas",
    run_id=f"run-{uuid.uuid4()}",
    tools=[scale_tool],
)
```

### request_id

HTTP request correlation ID. Use this for:
- End-to-end request tracing
- Correlating with API gateway logs
- Debugging request flows

```python
# Typically passed from your HTTP framework
from fastapi import Request

@app.post("/chat")
async def chat(request: Request, body: ChatRequest):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    agent_request = AgentRequest(
        content=body.message,
        request_id=request_id,
        tools=[...],
    )
```

---

## How Tracing Flows Through the System

```
┌─────────────────────┐
│   HTTP Request      │  X-Request-ID, user from JWT, etc.
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   AgentRequest      │  user_id, session_id, run_id, request_id
│   + PlatformContext │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   AgentService      │  Logs tracing context
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   AgnoAdapter       │  Passes to Agno SDK:
│                     │  - run_id → agno_agent.arun(run_id=...)
│                     │  - session_id → agno_agent.arun(session_id=...)
│                     │  - user_id → agno_agent.arun(user_id=...)
│                     │  - metadata → agno_agent.arun(metadata={...})
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Agno SDK          │  Native tracing support
│   (LLM Provider)    │  Integrates with observability platforms
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   AgentResponse     │  metadata contains tracing IDs
└─────────────────────┘
```

---

## Accessing Tracing Context

### In Response Metadata

After execution, tracing IDs are available in the response:

```python
response = await agent_service.execute(request)

# Access tracing metadata
run_id = response.metadata.get("run_id")
session_id = response.metadata.get("session_id")
user_id = response.metadata.get("user_id")
request_id = response.metadata.get("request_id")
tenant_id = response.metadata.get("tenant_id")
```

### In PlatformContext

The `PlatformContext` provides a helper method to extract only tracing fields:

```python
context = PlatformContext.from_dict(request.context or {})

# Get only tracing fields (safe to log, no sensitive data)
tracing = context.get_tracing_dict()
# {'user_id': 'user-123', 'session_id': 'session-abc', ...}

logger.info(f"Processing request", extra=tracing)
```

---

## Integration with Agno Debug Mode

DCAF automatically syncs Agno's debug logging with Python's logging level:

```bash
# Enable Agno debug mode (verbose tracing)
LOG_LEVEL=DEBUG python your_agent.py

# Or set AGNO_DEBUG directly
AGNO_DEBUG=true python your_agent.py
```

When debug mode is enabled, you'll see:
- Detailed message flow logging
- Tool call parameters and results
- Agno SDK internal operations

---

## Integration with OpenTelemetry

Agno supports OpenTelemetry for distributed tracing. To enable:

```bash
pip install openinference-instrumentation-agno opentelemetry-sdk
```

```python
import openlit
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

# Configure OpenTelemetry
provider = TracerProvider()
exporter = OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")
# ... configure processor and provider

# Initialize instrumentation
openlit.init()

# Your DCAF code will now emit traces
response = await agent_service.execute(request)
```

With OpenTelemetry enabled, each agent execution creates spans that include:
- The tracing IDs you provided (run_id, session_id, etc.)
- Tool call durations and parameters
- LLM request/response timing
- Token usage metrics

---

## Logging Best Practices

### Structured Logging with Tracing

```python
import logging
import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger()

# Include tracing in all log entries
async def handle_chat(user_id: str, session_id: str, message: str):
    run_id = f"run-{uuid.uuid4()}"

    # Bind tracing context to logger
    log = logger.bind(
        user_id=user_id,
        session_id=session_id,
        run_id=run_id,
    )

    log.info("Starting agent execution")

    request = AgentRequest(
        content=message,
        user_id=user_id,
        session_id=session_id,
        run_id=run_id,
        tools=[...],
    )

    response = await agent_service.execute(request)

    log.info("Agent execution complete",
             has_pending=response.has_pending_approvals)

    return response
```

### Log Output Example

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "info",
  "event": "Starting agent execution",
  "user_id": "user-123",
  "session_id": "session-abc",
  "run_id": "run-xyz"
}
{
  "timestamp": "2024-01-15T10:30:02Z",
  "level": "info",
  "event": "Agno: Tracing context",
  "run_id": "run-xyz",
  "session_id": "session-abc",
  "user_id": "user-123"
}
{
  "timestamp": "2024-01-15T10:30:05Z",
  "level": "info",
  "event": "Agent execution complete",
  "user_id": "user-123",
  "session_id": "session-abc",
  "run_id": "run-xyz",
  "has_pending": false
}
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Python log level. Set to `DEBUG` for Agno verbose mode |
| `AGNO_DEBUG` | `false` | Enable Agno debug mode directly |
| `AGNO_MONITOR` | `false` | Enable Agno monitoring dashboard |

---

## See Also

- [Adapters](../core/adapters.md) - AgnoAdapter configuration
- [Environment Configuration](environment-configuration.md) - Environment variables
- [Working with Bedrock](working-with-bedrock.md) - AWS Bedrock setup
