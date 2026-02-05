# Agent Server API Reference (Legacy)

!!! warning "Legacy API"
    This documents the **v1 API**. For new projects, use `serve(agent)` from the [Core API](../core/index.md).
    
    See [Migration Guide](../guides/migration.md) to upgrade existing code.

The Agent Server module provides a FastAPI-based server for hosting DCAF agents with RESTful endpoints.

---

## Table of Contents

1. [Overview](#overview)
2. [create_chat_app()](#create_chat_app)
3. [API Endpoints](#api-endpoints)
4. [Request/Response Formats](#requestresponse-formats)
5. [Streaming](#streaming)
6. [Error Handling](#error-handling)
7. [Channel Routing](#channel-routing)
8. [Examples](#examples)

---

## Overview

The Agent Server wraps any `AgentProtocol`-compliant agent in a FastAPI application with standardized endpoints for chat interactions.

### Import

```python
from dcaf.agent_server import create_chat_app, AgentProtocol

# Or from the main module
from dcaf import create_chat_app, AgentProtocol
```

### Features

- **REST API**: Standard HTTP endpoints
- **WebSocket**: Bidirectional streaming via `/api/chat-ws`
- **Streaming**: NDJSON streaming support
- **Validation**: Pydantic schema validation
- **Logging**: Built-in request/response logging
- **Health Check**: Endpoint for monitoring
- **Channel Routing**: Optional Slack integration

### AgentProtocol Interface

Any agent passed to `create_chat_app()` must satisfy the `AgentProtocol`:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class AgentProtocol(Protocol):
    def invoke(self, messages: dict[str, list[dict[str, Any]]]) -> AgentMessage: ...
```

**Required:**

- `invoke(messages) -> AgentMessage`: Process messages and return a response. Can be sync or async.

**Optional:**

- `invoke_stream(messages) -> Iterator[StreamEvent]`: Stream responses. If not implemented, streaming endpoints fall back to `invoke()` and wrap the response in stream events.

!!! note "Backwards Compatibility"
    The protocol only requires `invoke()`. V1 agents that don't implement `invoke_stream()` will still work with all endpoints—streaming endpoints automatically fall back to wrapping the `invoke()` response in stream events.

---

## create_chat_app()

Create a FastAPI application from an agent.

```python
def create_chat_app(
    agent: AgentProtocol, 
    router: ChannelResponseRouter = None
) -> FastAPI
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent` | `AgentProtocol` | Yes | Agent implementation |
| `router` | `ChannelResponseRouter` | No | Channel-specific routing |

### Returns

`FastAPI` - A configured FastAPI application instance.

### Raises

- `TypeError` - If agent doesn't satisfy `AgentProtocol`

### Example

```python
from dcaf.agent_server import create_chat_app
from dcaf.agents import ToolCallingAgent
from dcaf.llm import BedrockLLM
import uvicorn

# Create agent
llm = BedrockLLM()
agent = ToolCallingAgent(llm=llm, tools=[...], system_prompt="...")

# Create app
app = create_chat_app(agent)

# Run server
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### With Channel Router

```python
from dcaf.agent_server import create_chat_app
from dcaf.channel_routing import SlackResponseRouter
from dcaf.llm import BedrockLLM

llm = BedrockLLM()

# Create router for Slack
router = SlackResponseRouter(
    llm_client=llm,
    agent_name="MyBot",
    agent_description="A helpful assistant"
)

# Create app with router
app = create_chat_app(agent, router=router)
```

---

## API Endpoints

!!! note "Endpoint Naming"
    The legacy endpoints (`/api/sendMessage`, `/api/sendMessageStream`) are still fully functional but deprecated. New integrations should use the preferred endpoints (`/api/chat`, `/api/chat-stream`).

    | Legacy (Deprecated) | Preferred | Description |
    |---------------------|-----------|-------------|
    | `POST /api/sendMessage` | `POST /api/chat` | Synchronous chat |
    | `POST /api/sendMessageStream` | `POST /api/chat-stream` | Streaming chat |
    | — | `WS /api/chat-ws` | WebSocket chat (new) |

### GET /health

Health check endpoint for monitoring.

```
GET /health
```

#### Response

```json
{
    "status": "ok"
}
```

#### Example

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

### POST /api/sendMessage

!!! warning "Deprecated"
    This endpoint is deprecated. Use `POST /api/chat` instead for new integrations.

    The endpoint remains fully functional for backwards compatibility.

Send a message to the agent and receive a response.

```
POST /api/sendMessage
Content-Type: application/json
```

#### Request Body

```json
{
    "messages": [
        {
            "role": "user",
            "content": "Hello!",
            "data": {},
            "platform_context": {
                "tenant_name": "production",
                "user_id": "user123"
            }
        }
    ],
    "source": "help-desk"
}
```

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `messages` | `array` | Yes | Array of message objects |
| `source` | `string` | No | Message source (e.g., "slack", "help-desk") |

#### Response

```json
{
    "role": "assistant",
    "content": "Hello! How can I help you today?",
    "data": {
        "cmds": [],
        "executed_cmds": [],
        "tool_calls": [],
        "executed_tool_calls": [],
        "url_configs": []
    },
    "meta_data": {},
    "timestamp": null,
    "user": null,
    "agent": null
}
```

#### Example

```bash
curl -X POST http://localhost:8000/api/sendMessage \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is the weather in NYC?"}
    ]
  }'
```

#### Error Responses

| Code | Description |
|------|-------------|
| `400` | Missing `messages` field |
| `422` | Validation error in messages |
| `500` | Agent error or invalid response |

---

### POST /api/sendMessageStream

!!! warning "Deprecated"
    This endpoint is deprecated. Use `POST /api/chat-stream` instead for new integrations.

    The endpoint remains fully functional for backwards compatibility.

Stream a response from the agent.

```
POST /api/sendMessageStream
Content-Type: application/json
```

#### Request Body

Same as `/api/sendMessage`.

#### Response

NDJSON (Newline-delimited JSON) stream:

```
{"type":"text_delta","text":"Hello"}
{"type":"text_delta","text":" there!"}
{"type":"tool_calls","tool_calls":[...]}
{"type":"done","stop_reason":"end_turn"}
```

#### Example

```bash
curl -X POST http://localhost:8000/api/sendMessageStream \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Tell me a story"}]}'
```

---

### WS /api/chat-ws

Bidirectional streaming chat over WebSocket. The connection stays open for multiple conversation turns.

```
WS /api/chat-ws
```

#### Client Frame

Each text frame from the client is a JSON object with the same shape as the HTTP endpoints:

```json
{"messages": [{"role": "user", "content": "Hello"}]}
```

#### Server Frames

The server streams back the same event types as `/api/sendMessageStream` (text_delta, tool_calls, done, error, etc.), one JSON object per text frame. Each turn ends with a `done` event, after which the client can send the next turn.

#### Error Behavior

Errors (invalid JSON, missing fields, agent exceptions) are sent as `error` events **without** closing the connection. The client can continue sending messages after receiving an error.

#### Example

```python
import asyncio
import json
import websockets

async def chat():
    async with websockets.connect("ws://localhost:8000/api/chat-ws") as ws:
        await ws.send(json.dumps({
            "messages": [{"role": "user", "content": "Hello"}]
        }))

        async for frame in ws:
            event = json.loads(frame)
            if event["type"] == "text_delta":
                print(event["text"], end="", flush=True)
            elif event["type"] == "done":
                print("\n--- Done ---")
                break
            elif event["type"] == "error":
                print(f"\nError: {event['error']}")
                break

asyncio.run(chat())
```

---

## Request/Response Formats

### Message Object

```python
{
    "role": "user" | "assistant",
    "content": "Message text",
    "data": {
        "cmds": [...],              # Suggested commands
        "executed_cmds": [...],     # Executed commands
        "tool_calls": [...],        # Tools needing approval
        "executed_tool_calls": [...] # Executed tools
    },
    "platform_context": {           # Only for user messages
        "tenant_name": "string",
        "user_id": "string",
        "k8s_namespace": "string",
        "duplo_base_url": "string",
        "duplo_token": "string",
        "kubeconfig": "base64-string",
        "aws_credentials": {...}
    },
    "timestamp": "ISO-8601",
    "user": {"name": "string", "id": "string"},
    "agent": {"name": "string", "id": "string"}
}
```

### AgentMessage Response

```python
class AgentMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str = ""
    data: Data = Data()
    meta_data: Dict[str, Any] = {}
    timestamp: Optional[datetime] = None
    user: Optional[User] = None
    agent: Optional[Agent] = None
```

### Data Object

```python
class Data(BaseModel):
    cmds: List[Command] = []           # Suggested terminal commands
    executed_cmds: List[ExecutedCommand] = []
    tool_calls: List[ToolCall] = []    # Tools needing approval
    executed_tool_calls: List[ExecutedToolCall] = []
    url_configs: List[URLConfig] = []
```

---

## Streaming

### Stream Event Types

DCAF supports 7 event types for streaming:

#### 1. text_delta

Streaming text tokens from the LLM.

```json
{"type": "text_delta", "text": "Hello"}
```

#### 2. tool_calls

Tool calls requiring user approval.

```json
{
    "type": "tool_calls",
    "tool_calls": [
        {
            "id": "tool-123",
            "name": "delete_file",
            "input": {"path": "/tmp/file.txt"},
            "execute": false,
            "tool_description": "Delete a file",
            "input_description": {...}
        }
    ]
}
```

#### 3. executed_tool_calls

Tools that were executed.

```json
{
    "type": "executed_tool_calls",
    "executed_tool_calls": [
        {
            "id": "tool-456",
            "name": "get_weather",
            "input": {"location": "NYC"},
            "output": "72°F, sunny"
        }
    ]
}
```

#### 4. commands

Terminal commands for approval.

```json
{
    "type": "commands",
    "commands": [
        {
            "command": "kubectl get pods",
            "execute": false,
            "files": []
        }
    ]
}
```

#### 5. executed_commands

Commands that were executed.

```json
{
    "type": "executed_commands",
    "executed_cmds": [
        {
            "command": "ls -la",
            "output": "total 0\ndrwxr-xr-x ..."
        }
    ]
}
```

#### 6. done

Stream completed successfully.

```json
{"type": "done", "stop_reason": "end_turn"}
```

#### 7. error

Error during streaming.

```json
{"type": "error", "error": "Connection timeout"}
```

### Consuming Streams

#### Python

```python
import requests

response = requests.post(
    "http://localhost:8000/api/sendMessageStream",
    json={"messages": [{"role": "user", "content": "Hello"}]},
    stream=True
)

for line in response.iter_lines():
    if line:
        import json
        event = json.loads(line)
        
        if event["type"] == "text_delta":
            print(event["text"], end="", flush=True)
        elif event["type"] == "done":
            print("\n[Done]")
            break
        elif event["type"] == "error":
            print(f"\n[Error: {event['error']}]")
            break
```

#### JavaScript

```javascript
const response = await fetch('/api/sendMessageStream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        messages: [{ role: 'user', content: 'Hello' }]
    })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    
    const lines = decoder.decode(value).split('\n');
    for (const line of lines) {
        if (line.trim()) {
            const event = JSON.parse(line);
            console.log(event);
        }
    }
}
```

---

## Error Handling

### Error Responses

```python
# 400 Bad Request - Missing messages
{
    "detail": "'messages' field missing from request body"
}

# 422 Unprocessable Entity - Validation error
{
    "detail": [
        {
            "loc": ["body", "messages", 0, "role"],
            "msg": "value is not a valid enumeration member",
            "type": "type_error.enum"
        }
    ]
}

# 500 Internal Server Error - Agent error
{
    "detail": "Agent returned invalid Message: ..."
}
```

### Handling Errors in Client

```python
import requests

try:
    response = requests.post(
        "http://localhost:8000/api/sendMessage",
        json={"messages": [{"role": "user", "content": "Hi"}]},
        timeout=30
    )
    response.raise_for_status()
    data = response.json()
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 400:
        print("Bad request:", e.response.json())
    elif e.response.status_code == 422:
        print("Validation error:", e.response.json())
    elif e.response.status_code == 500:
        print("Server error:", e.response.json())
except requests.exceptions.Timeout:
    print("Request timed out")
except requests.exceptions.ConnectionError:
    print("Connection error")
```

---

## Channel Routing

The Agent Server supports channel-specific routing, particularly for Slack.

### Slack Integration

```python
from dcaf.agent_server import create_chat_app
from dcaf.channel_routing import SlackResponseRouter
from dcaf.llm import BedrockLLM

llm = BedrockLLM()

# Create Slack router
router = SlackResponseRouter(
    llm_client=llm,
    agent_name="DuploBot",
    agent_description="A helpful DuploCloud assistant",
    model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0"  # Fast model for routing
)

# Create app with router
app = create_chat_app(agent, router=router)
```

### How Routing Works

1. Request includes `"source": "slack"`
2. Router's `should_agent_respond()` is called
3. If `False`, returns empty response (agent stays silent)
4. If `True`, proceeds with agent invocation

### Request with Source

```json
{
    "messages": [...],
    "source": "slack"
}
```

---

## Examples

### Example 1: Basic Server

```python
from dcaf.agent_server import create_chat_app, AgentProtocol
from dcaf.schemas.messages import AgentMessage
import uvicorn

class SimpleAgent(AgentProtocol):
    def invoke(self, messages):
        return AgentMessage(content="Hello from SimpleAgent!")

agent = SimpleAgent()
app = create_chat_app(agent)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Example 2: Production Server

```python
from dcaf.agent_server import create_chat_app
from dcaf.agents import ToolCallingAgent
from dcaf.llm import BedrockLLM
from dcaf.tools import tool
import uvicorn
import dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment
dotenv.load_dotenv()

# Define tools
@tool(schema={...}, requires_approval=False)
def my_tool(param: str) -> str:
    return f"Result: {param}"

# Create components
llm = BedrockLLM(region_name="us-east-1")
agent = ToolCallingAgent(
    llm=llm,
    tools=[my_tool],
    system_prompt="You are a helpful assistant."
)

# Create app
app = create_chat_app(agent)

# Add middleware (optional)
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        workers=1  # Use 1 worker for stateful agents
    )
```

### Example 3: Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```python
# main.py
from dcaf.agent_server import create_chat_app
from dcaf.agents import ToolCallingAgent
from dcaf.llm import BedrockLLM
import dotenv

dotenv.load_dotenv()

llm = BedrockLLM()
agent = ToolCallingAgent(llm=llm, tools=[], system_prompt="...")
app = create_chat_app(agent)
```

### Example 4: Testing the Server

```python
# test_server.py
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_send_message():
    response = client.post(
        "/api/sendMessage",
        json={
            "messages": [
                {"role": "user", "content": "Hello!"}
            ]
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert data["role"] == "assistant"

def test_missing_messages():
    response = client.post(
        "/api/sendMessage",
        json={}
    )
    assert response.status_code == 400

def test_invalid_role():
    response = client.post(
        "/api/sendMessage",
        json={
            "messages": [
                {"role": "invalid", "content": "Hello!"}
            ]
        }
    )
    assert response.status_code == 422
```

---

## See Also

- [Agents API Reference](./agents.md)
- [Schemas API Reference](./schemas.md)
- [Channel Routing API Reference](./channel-routing.md)
- [Streaming Guide](../guides/streaming.md)

