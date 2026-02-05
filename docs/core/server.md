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
| `/api/chat-ws` | WebSocket | Bidirectional streaming chat |

### Legacy Endpoints (V1 Code Path)

For backwards compatibility with existing v1 clients, the following endpoints are preserved:

| Legacy Endpoint | Preferred Endpoint | Code Path |
|-----------------|-------------------|-----------|
| `POST /api/sendMessage` | `POST /api/chat` | V1 (`dcaf.agent_server`) |
| `POST /api/sendMessageStream` | `POST /api/chat-stream` | V1 (`dcaf.agent_server`) |

!!! info "Strangler Fig Migration (ADR-006)"
    Legacy endpoints use the **V1 code path** from `dcaf.agent_server`, while new endpoints use the **V2 code path** from `dcaf.core`. This follows the [Strangler Fig migration pattern](../adrs/006-strangler-fig-migration.md).

    **Key differences:**

    | Feature | V2 (`/api/chat`) | V1 (`/api/sendMessage`) |
    |---------|------------------|-------------------------|
    | `_request_fields` forwarding | ✅ Yes | ❌ No |
    | `meta_data.request_context` echo | ✅ Yes | ❌ No |
    | WebSocket support | ✅ Yes | ❌ No |
    | Response format | V2 `AgentMessage` | V1 `AgentMessage` |

    **Existing integrations continue to work without any code changes.**

!!! note "When to Use Each Endpoint"
    - **New projects**: Use `/api/chat`, `/api/chat-stream`, and `/api/chat-ws` (V2)
    - **Existing v1 integrations**: Continue using `/api/sendMessage` and `/api/sendMessageStream`
    - **Unified server**: `dcaf.core.create_app()` exposes both V1 and V2 endpoints simultaneously

#### Why the Rename? (ADR-007)

The endpoint names were changed for three reasons:

1. **Future-proofing**: Lowercase URLs avoid case-sensitivity issues if security middleware is added later
2. **Semantic accuracy**: "chat" better describes bidirectional conversation than "sendMessage"
3. **REST conventions**: Lowercase, hyphenated paths follow RESTful best practices

See [ADR-007: Lowercase Chat Endpoints](../adrs/007-lowercase-chat-endpoints.md) for the full rationale.

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

## WebSocket (`/api/chat-ws`)

The WebSocket endpoint provides bidirectional streaming chat over a persistent connection. Unlike the HTTP endpoints, a single WebSocket connection stays open for multiple conversation turns.

### Connecting

```
ws://localhost:8000/api/chat-ws
```

### Message Format

Each client frame is a JSON object with the same shape as the HTTP endpoints:

```json
{"messages": [{"role": "user", "content": "Hello"}]}
```

The server streams back event frames (same types as `/api/chat-stream`), ending each turn with a `done` event. The connection remains open for the next turn.

### Python Client

```python
import asyncio
import json
import websockets

async def chat():
    async with websockets.connect("ws://localhost:8000/api/chat-ws") as ws:
        # Turn 1
        await ws.send(json.dumps({
            "messages": [{"role": "user", "content": "What is Kubernetes?"}]
        }))

        async for frame in ws:
            event = json.loads(frame)
            if event["type"] == "text_delta":
                print(event["text"], end="", flush=True)
            elif event["type"] == "done":
                print()
                break

        # Turn 2 — same connection
        await ws.send(json.dumps({
            "messages": [
                {"role": "user", "content": "What is Kubernetes?"},
                {"role": "assistant", "content": "Kubernetes is a container orchestration platform..."},
                {"role": "user", "content": "How do I list pods?"},
            ]
        }))

        async for frame in ws:
            event = json.loads(frame)
            if event["type"] == "text_delta":
                print(event["text"], end="", flush=True)
            elif event["type"] == "done":
                print()
                break

asyncio.run(chat())
```

### JavaScript Client

```javascript
const ws = new WebSocket("ws://localhost:8000/api/chat-ws");

ws.onopen = () => {
  ws.send(JSON.stringify({
    messages: [{ role: "user", content: "Hello" }]
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === "text_delta") {
    process.stdout.write(data.text);
  } else if (data.type === "done") {
    console.log("\n--- Turn complete ---");
  } else if (data.type === "error") {
    console.error("Error:", data.error);
  }
};
```

### Error Handling

Errors during a turn are sent as `error` events without closing the connection. The client can continue sending messages after an error:

```json
{"type": "error", "error": "agent exploded"}
```

Invalid JSON or missing `messages` fields also return error events while keeping the connection alive.

### Connection Stability

DCAF uses uvicorn's built-in WebSocket ping/pong mechanism to detect dead connections. By default, the server sends a ping frame every **20 seconds** and expects a pong reply within **20 seconds**. If no pong is received, the server closes the connection.

You can tune these values via `serve()`:

```python
serve(
    agent,
    ws_ping_interval=30.0,   # Ping every 30s
    ws_ping_timeout=30.0,    # Wait 30s for pong
)
```

Set to `None` to disable automatic pings:

```python
serve(agent, ws_ping_interval=None, ws_ping_timeout=None)
```

!!! tip "Load Balancer Considerations"
    Many load balancers (e.g., AWS ALB, nginx) enforce their own idle timeouts, typically 60–120 seconds. Ensure `ws_ping_interval` is shorter than your load balancer's idle timeout so that ping frames keep the connection active.

#### Client-Side Reconnection

WebSocket connections can drop due to network issues, server restarts, or load balancer timeouts. Clients should implement reconnection logic:

=== "Python"

    ```python
    import asyncio
    import json
    import websockets
    from websockets.exceptions import ConnectionClosed

    async def resilient_chat(url: str, message: str):
        backoff = 1
        while True:
            try:
                async with websockets.connect(url) as ws:
                    backoff = 1  # Reset on successful connect
                    await ws.send(json.dumps({
                        "messages": [{"role": "user", "content": message}]
                    }))

                    async for frame in ws:
                        event = json.loads(frame)
                        if event["type"] == "text_delta":
                            print(event["text"], end="", flush=True)
                        elif event["type"] == "done":
                            print()
                            return  # Success
                        elif event["type"] == "error":
                            print(f"\nError: {event['error']}")
                            return

            except (ConnectionClosed, OSError) as e:
                print(f"\nConnection lost: {e}. Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)  # Exponential backoff, max 30s
    ```

=== "JavaScript"

    ```javascript
    function createResilientWebSocket(url, onEvent) {
      let backoff = 1000;

      function connect() {
        const ws = new WebSocket(url);

        ws.onopen = () => { backoff = 1000; };

        ws.onmessage = (msg) => {
          const event = JSON.parse(msg.data);
          onEvent(event);
        };

        ws.onclose = (e) => {
          if (e.code !== 1000) {  // Abnormal close
            console.log(`Reconnecting in ${backoff}ms...`);
            setTimeout(connect, backoff);
            backoff = Math.min(backoff * 2, 30000);
          }
        };

        ws.onerror = () => ws.close();

        return ws;
      }

      return connect();
    }

    // Usage
    createResilientWebSocket("ws://localhost:8000/api/chat-ws", (event) => {
      if (event.type === "text_delta") process.stdout.write(event.text);
      else if (event.type === "done") console.log("\n--- Done ---");
    });
    ```

### When to Use WebSocket vs HTTP

| Use Case | Recommended Endpoint |
|----------|---------------------|
| Single request/response | `/api/chat` |
| Streaming a single response | `/api/chat-stream` |
| Multi-turn conversation with streaming | `/api/chat-ws` |
| Real-time interactive UI | `/api/chat-ws` |
| Simple integration / cURL testing | `/api/chat` or `/api/chat-stream` |

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
    channel_router: ChannelResponseRouter | None = None,
    a2a: bool = False,
    a2a_adapter: str = "agno",
    a2a_agent_card: AgentCard | dict | None = None,
    mcp: bool = False,
    mcp_port: int = 8001,
    mcp_transport: str = "sse",
    ws_ping_interval: float | None = 20.0,
    ws_ping_timeout: float | None = 20.0,
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
| `channel_router` | `ChannelResponseRouter` | `None` | Channel response router for multi-agent environments. See [Channel Routing](#channel-routing). |
| `a2a` | `bool` | `False` | Enable A2A (Agent-to-Agent) protocol support |
| `a2a_adapter` | `str` | `"agno"` | A2A adapter to use |
| `a2a_agent_card` | `AgentCard` or `dict` | `None` | Custom agent card for A2A discovery. See [A2A Agent Card](./a2a.md#custom-agent-card). |
| `mcp` | `bool` | `False` | Enable MCP server alongside the HTTP server |
| `mcp_port` | `int` | `8001` | Port for the MCP server |
| `mcp_transport` | `str` | `"sse"` | MCP transport (`"sse"` or `"stdio"`) |
| `ws_ping_interval` | `float` or `None` | `20.0` | Seconds between WebSocket ping frames. Set to `None` to disable. |
| `ws_ping_timeout` | `float` or `None` | `20.0` | Seconds to wait for a pong reply before closing the connection. |

**Raises:**

- `ValueError` - If `reload=True` and `workers > 1` (mutually exclusive)

### create_app()

```python
def create_app(
    agent: Agent | Callable,
    additional_routers: Sequence[APIRouter] | None = None,
    channel_router: ChannelResponseRouter | None = None,
    a2a: bool = False,
    a2a_adapter: str = "agno",
    a2a_agent_card: AgentCard | dict | None = None,
) -> FastAPI
```

Create a FastAPI application without starting the server. Use this for programmatic control or custom uvicorn configuration.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent` | `Agent` or `Callable` | Required | Agent instance or callable `(messages, context) -> AgentResult` |
| `additional_routers` | `Sequence[APIRouter]` | `None` | Custom FastAPI routers to include |
| `channel_router` | `ChannelResponseRouter` | `None` | Channel response router for multi-agent environments. See [Channel Routing](#channel-routing). |
| `a2a` | `bool` | `False` | Enable A2A (Agent-to-Agent) protocol support |
| `a2a_adapter` | `str` | `"agno"` | A2A adapter to use |
| `a2a_agent_card` | `AgentCard` or `dict` | `None` | Custom agent card for A2A discovery. See [A2A Agent Card](./a2a.md#custom-agent-card). |

---

## Channel Routing

Channel routing enables intelligent message filtering in multi-agent environments. When a `channel_router` is provided and the incoming request includes `"source": "slack"`, the router determines whether the agent should respond before processing the message.

This is useful when multiple agents share a Slack channel — each agent uses its own router to decide if a message is relevant to its domain.

### Setup

```python
from dcaf.core import Agent, serve, SlackResponseRouter
from dcaf.llm import BedrockLLM

agent = Agent(
    tools=[...],
    system_prompt="You are a Kubernetes assistant.",
)

llm = BedrockLLM()

slack_router = SlackResponseRouter(
    llm_client=llm,
    agent_name="k8s-agent",
    agent_description="""
    Specialized Kubernetes and Helm expert. Responds to:
    - Kubernetes resource management, kubectl commands
    - Helm chart operations
    - DuploCloud service management
    Does NOT respond to: general cloud infra, CI/CD, database queries.
    """,
)

serve(agent, channel_router=slack_router, port=8000)
```

### With create_app()

```python
from dcaf.core import Agent, create_app, SlackResponseRouter
from dcaf.llm import BedrockLLM
import uvicorn

agent = Agent(tools=[...])
llm = BedrockLLM()

router = SlackResponseRouter(
    llm_client=llm,
    agent_name="aws-agent",
    agent_description="AWS cloud infrastructure specialist",
)

app = create_app(agent, channel_router=router)
uvicorn.run(app, host="0.0.0.0", port=8000)
```

### How It Works

When a request arrives with `"source": "slack"` in the body:

1. The `SlackResponseRouter.should_agent_respond()` method is called with the message thread.
2. The router uses a fast LLM call (Claude 3.5 Haiku) to analyze the conversation and decide if the agent should respond.
3. If the router decides **not** to respond, the endpoint returns an empty response immediately (or a `done` event for streaming).
4. If the router decides **to respond**, the request proceeds to the agent normally.

Requests without `"source": "slack"` bypass routing entirely.

### Slack Request Format

```json
{
    "messages": [
        {
            "role": "user",
            "content": "My pods keep crashing with OOMKilled",
            "user": {"name": "alice", "id": "U123"}
        },
        {
            "role": "assistant",
            "content": "Try increasing memory limits in your deployment.",
            "agent": {"name": "k8s-agent", "id": "B456"}
        },
        {
            "role": "user",
            "content": "Actually, I think this is an AWS node issue",
            "user": {"name": "alice", "id": "U123"}
        }
    ],
    "source": "slack"
}
```

### Multi-Agent Example

Run multiple agents on different ports, each with its own router:

```python
# k8s_server.py
from dcaf.core import Agent, serve, SlackResponseRouter
from dcaf.llm import BedrockLLM

llm = BedrockLLM()
agent = Agent(tools=[...], system_prompt="You are a Kubernetes expert.")

serve(
    agent,
    channel_router=SlackResponseRouter(
        llm_client=llm,
        agent_name="k8s-agent",
        agent_description="Kubernetes and container orchestration specialist",
    ),
    port=8000,
)
```

```python
# aws_server.py
from dcaf.core import Agent, serve, SlackResponseRouter
from dcaf.llm import BedrockLLM

llm = BedrockLLM()
agent = Agent(tools=[...], system_prompt="You are an AWS infrastructure expert.")

serve(
    agent,
    channel_router=SlackResponseRouter(
        llm_client=llm,
        agent_name="aws-agent",
        agent_description="AWS cloud infrastructure and services specialist",
    ),
    port=8001,
)
```

When a Slack message arrives, each agent's router independently decides whether to respond based on the message content and the agent's description.

### Custom Routers

You can implement your own router by extending `ChannelResponseRouter`:

```python
from dcaf.core import ChannelResponseRouter

class KeywordRouter(ChannelResponseRouter):
    def __init__(self, keywords: list[str]):
        self.keywords = keywords

    def should_agent_respond(self, messages: list) -> dict:
        last_msg = next(
            (m for m in reversed(messages) if m.get("role") == "user"),
            None,
        )
        if not last_msg:
            return {"should_respond": False, "reasoning": "No user message"}

        content = last_msg.get("content", "").lower()
        for kw in self.keywords:
            if kw.lower() in content:
                return {"should_respond": True, "reasoning": f"Matched: {kw}"}

        return {"should_respond": False, "reasoning": "No matching keywords"}

serve(agent, channel_router=KeywordRouter(keywords=["kubernetes", "k8s", "pod"]))
```

!!! info "See Also"
    For full API details on `SlackResponseRouter` (constructor parameters, decision criteria, testing patterns), see the [Channel Routing API Reference](../api-reference/channel-routing.md).

---

## See Also

- [Core Overview](index.md) - Introduction to DCAF Core
- [Channel Routing API Reference](../api-reference/channel-routing.md) - Full `SlackResponseRouter` and `ChannelResponseRouter` API details
- [ADR-007: Lowercase Chat Endpoints](../adrs/007-lowercase-chat-endpoints.md) - Why `/api/chat` instead of `/api/sendMessage`
