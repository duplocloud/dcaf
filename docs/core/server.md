# Server

DCAF Core provides simple utilities to expose your agent as a REST API server with minimal configuration.

---

## Quick Start

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool

@tool(description="Get current time")
def get_time() -> str:
    from datetime import datetime
    return datetime.now().isoformat()

agent = Agent(tools=[get_time])
serve(agent)  # Server at http://0.0.0.0:8000
```

That's it. Your agent is now accessible via HTTP.

---

## Configuration

### Port and Host

```python
# Custom port
serve(agent, port=8080)

# Custom host and port
serve(agent, host="0.0.0.0", port=3000)

# Development mode with auto-reload
serve(agent, port=8000, reload=True)
```

### Production Configuration

For production deployments, configure worker processes and keep-alive timeouts:

```python
serve(
    agent,
    port=8000,
    workers=4,              # Multiple workers for parallelism
    timeout_keep_alive=30,  # Match your load balancer's idle timeout
    log_level="warning",
)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `workers` | `1` | Number of worker processes. For production, use `(2 × cpu_cores) + 1`. |
| `timeout_keep_alive` | `5` | Keep-alive timeout in seconds. Set this to match or exceed your load balancer's idle timeout (e.g., AWS ALB defaults to 60s). |

!!! warning "reload and workers are mutually exclusive"
    You cannot use `reload=True` with `workers > 1`. Use `workers=1` for development with hot reload.

### Programmatic Control

If you need more control over the FastAPI app:

```python
from dcaf.core import Agent, create_app
import uvicorn

agent = Agent(tools=[...])
app = create_app(agent)

# Add custom endpoints
@app.get("/custom")
def custom_endpoint():
    return {"message": "Hello from custom endpoint"}

# Run with custom configuration
uvicorn.run(app, host="0.0.0.0", port=8000, workers=4)
```

---

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (always responds immediately) |
| `/api/chat` | POST | Synchronous chat |
| `/api/chat-stream` | POST | Streaming chat (NDJSON) |

### Legacy Endpoints (Backwards Compatible)

| Endpoint | Method | Status |
|----------|--------|--------|
| `/api/sendMessage` | POST | Deprecated, use `/api/chat` |
| `/api/sendMessageStream` | POST | Deprecated, use `/api/chat-stream` |

---

## Request Format

All chat endpoints accept the same request body:

```json
{
  "messages": [
    {"role": "user", "content": "What time is it?"}
  ]
}
```

### With Conversation History

```json
{
  "messages": [
    {"role": "user", "content": "What time is it?"},
    {"role": "assistant", "content": "The current time is 2024-01-15T14:30:00"},
    {"role": "user", "content": "What about in Tokyo?"}
  ]
}
```

!!! note "Last Message is Current"
    The last message in the array is always treated as the current user message. All previous messages are conversation history.

### With Platform Context

```json
{
  "messages": [
    {
      "role": "user",
      "content": "List the pods",
      "platform_context": {
        "tenant_name": "acme-corp",
        "k8s_namespace": "production"
      }
    }
  ]
}
```

---

## Response Format

### Synchronous Response (`/api/chat`)

```json
{
  "role": "assistant",
  "content": "The current time is 2024-01-15T14:30:00",
  "data": {
    "tool_calls": [],
    "executed_tool_calls": []
  }
}
```

### Tool Approval Required

When a tool requires approval:

```json
{
  "role": "assistant",
  "content": "I need your approval to execute the following tools:",
  "data": {
    "tool_calls": [
      {
        "id": "tc_123",
        "name": "delete_pod",
        "input": {"name": "nginx-abc", "namespace": "production"},
        "execute": false,
        "tool_description": "Delete a Kubernetes pod",
        "input_description": {}
      }
    ]
  }
}
```

### Approving Tool Calls

To approve a tool call, send back the same tool call with `execute: true`:

```json
{
  "messages": [
    {"role": "user", "content": "Delete the failing pod"},
    {
      "role": "assistant",
      "content": "I need your approval...",
      "data": {
        "tool_calls": [
          {
            "id": "tc_123",
            "name": "delete_pod",
            "input": {"name": "nginx-abc"},
            "execute": true
          }
        ]
      }
    },
    {"role": "user", "content": "Yes, approved"}
  ]
}
```

---

## Streaming (`/api/chat-stream`)

The streaming endpoint returns NDJSON (newline-delimited JSON):

```bash
curl -X POST http://localhost:8000/api/chat-stream \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Tell me about Kubernetes"}]}'
```

**Response stream:**

```json
{"type": "text_delta", "text": "Kubernetes"}
{"type": "text_delta", "text": " is"}
{"type": "text_delta", "text": " a"}
{"type": "text_delta", "text": " container"}
{"type": "text_delta", "text": " orchestration"}
{"type": "text_delta", "text": " platform..."}
{"type": "done"}
```

### Event Types

| Event Type | Description |
|------------|-------------|
| `text_delta` | Text token(s) from the LLM |
| `tool_calls` | Tool calls requiring approval |
| `executed_tool_calls` | Results from executed tools |
| `done` | Stream completed successfully |
| `error` | An error occurred |

### Handling Streams in Python

```python
import httpx

with httpx.stream(
    "POST",
    "http://localhost:8000/api/chat-stream",
    json={"messages": [{"role": "user", "content": "Hello"}]},
) as response:
    for line in response.iter_lines():
        if line:
            event = json.loads(line)
            if event["type"] == "text_delta":
                print(event["text"], end="", flush=True)
            elif event["type"] == "done":
                print("\n--- Done ---")
```

### Handling Streams in JavaScript

```javascript
const response = await fetch("http://localhost:8000/api/chat-stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    messages: [{ role: "user", content: "Hello" }]
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  const lines = decoder.decode(value).split("\n");
  for (const line of lines) {
    if (line) {
      const event = JSON.parse(line);
      if (event.type === "text_delta") {
        process.stdout.write(event.text);
      }
    }
  }
}
```

---

## Async / Non-Blocking

All LLM calls run in a thread pool, so:

- **Health checks always respond immediately** (not blocked by long LLM calls)
- **Multiple concurrent requests** are handled properly
- **Kubernetes liveness probes** won't timeout during LLM calls

This is critical for production deployments where a 15-second LLM call could otherwise cause health check failures and container restarts.

---

## Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

With a production-ready entry point:

```python
# main.py
import os
from dcaf.core import Agent, serve
from my_tools import list_pods, delete_pod

agent = Agent(
    tools=[list_pods, delete_pod],
    system_prompt="You are a Kubernetes assistant."
)

if __name__ == "__main__":
    serve(
        agent,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        workers=int(os.getenv("WORKERS", 4)),
        timeout_keep_alive=int(os.getenv("KEEP_ALIVE", 30)),
        log_level=os.getenv("LOG_LEVEL", "warning"),
    )
```

!!! tip "Environment Variables"
    Use environment variables for configuration so you can tune without rebuilding:
    
    ```bash
    docker run -e WORKERS=8 -e KEEP_ALIVE=60 my-agent:latest
    ```

---

## Kubernetes Health Check

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
        - name: agent
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
            timeoutSeconds: 5  # Safe: health endpoint is non-blocking
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            periodSeconds: 5
```

---

## API Reference

### serve()

```python
def serve(
    agent: Agent | Callable,
    port: int = 8000,
    host: str = "0.0.0.0",
    reload: bool = False,
    log_level: str = "info",
    workers: int = 1,
    timeout_keep_alive: int = 5,
    additional_routers: Sequence[APIRouter] | None = None,
) -> None
```

Start a REST server for the agent.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent` | `Agent` or `Callable` | Required | Agent instance or callable `(messages, context) -> AgentResult` |
| `port` | `int` | `8000` | Port to listen on |
| `host` | `str` | `"0.0.0.0"` | Host to bind to |
| `reload` | `bool` | `False` | Enable auto-reload on code changes (development only) |
| `log_level` | `str` | `"info"` | Logging level (`debug`, `info`, `warning`, `error`) |
| `workers` | `int` | `1` | Number of worker processes for parallelism |
| `timeout_keep_alive` | `int` | `5` | Keep-alive timeout in seconds |
| `additional_routers` | `Sequence[APIRouter]` | `None` | Custom FastAPI routers to include |

**Raises:**

- `ValueError` - If `reload=True` and `workers > 1` (mutually exclusive)

### create_app()

```python
def create_app(
    agent: Agent | Callable,
    additional_routers: Sequence[APIRouter] | None = None,
) -> FastAPI
```

Create a FastAPI application without starting the server. Use this for programmatic control or custom uvicorn configuration.

---

## See Also

- [Core Overview](index.md) - Introduction to DCAF Core
- [ADR-007: Lowercase Chat Endpoints](../adrs/007-lowercase-chat-endpoints.md) - Why `/api/chat` instead of `/api/sendMessage`
