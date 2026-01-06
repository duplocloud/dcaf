# DCAF Core: A New Approach

A presentation introducing the DCAF Core API.

---

## Slide 1: Title

# DCAF Core
### Building AI Agents with Simplicity

**DCAF** = DuploCloud Agent Framework

A Python framework for building LLM-powered AI agents with:
- Tool calling
- Human-in-the-loop approval
- Production-ready REST API

---

## Slide 2: What is DCAF Core?

### A Simple API for Complex Agent Workflows

DCAF Core provides a streamlined interface for building AI agents that can:

- 🛠️ **Call tools** - Execute functions on behalf of users
- ✅ **Request approval** - Pause for human authorization on sensitive operations
- 📡 **Stream responses** - Real-time token-by-token output
- 🌐 **Serve via REST** - One-line HTTP server deployment

**Philosophy:** Hide complexity, expose simplicity.

---

## Slide 3: The Core API in 10 Lines

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool

@tool(description="List Kubernetes pods")
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

agent = Agent(tools=[list_pods], system="You are a Kubernetes assistant.")

serve(agent)
```

**That's it.** Your agent is now running at `http://localhost:8000`.

---

## Slide 4: Tool Definitions

### Auto-Generated Schemas from Type Hints

```python
@tool(description="Delete a Kubernetes pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")
```

The framework automatically infers:
- Parameter names and types from the function signature
- Required vs optional from default values
- Description from the decorator

### Adding Approval Requirements

```python
@tool(requires_approval=True, description="Delete a Kubernetes pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")
```

The agent will pause and request user approval before executing.

---

## Slide 5: The Agent Class

### Minimal Configuration, Maximum Capability

```python
from dcaf.core import Agent

agent = Agent(
    tools=[list_pods, delete_pod, restart_deployment],
    system="You are a Kubernetes assistant for the production cluster.",
)
```

### Running the Agent Programmatically

```python
response = agent.run([
    {"role": "user", "content": "What pods are running in the default namespace?"}
])

print(response.text)
# "Here are the pods currently running in the default namespace: ..."
```

---

## Slide 6: The serve() Function

### One-Line REST API Server

```python
from dcaf.core import serve

serve(agent)  # Running at http://0.0.0.0:8000
```

### Configuration Options

```python
serve(
    agent,
    port=8000,              # Port to listen on
    host="0.0.0.0",         # Host to bind to
    reload=True,            # Auto-reload for development
    log_level="info",       # Logging verbosity
)
```

---

## Slide 7: Production Configuration

### Built-in Support for Production Deployments

```python
serve(
    agent,
    port=8000,
    workers=4,              # Multiple worker processes
    timeout_keep_alive=30,  # Match load balancer timeout
    log_level="warning",
)
```

### Parameters

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `workers` | `1` | Number of worker processes for parallelism |
| `timeout_keep_alive` | `5` | Keep-alive timeout in seconds |

### Best Practices

- **Workers**: Use `(2 × cpu_cores) + 1` for production
- **Keep-Alive**: Set to match your load balancer (AWS ALB default is 60s)

---

## Slide 8: REST API Endpoints

### Automatically Created Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (always responds immediately) |
| `/api/chat` | POST | Synchronous chat |
| `/api/chat-stream` | POST | Streaming chat (NDJSON) |

### Example Request

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "List the pods"}]}'
```

### Example Response

```json
{
  "role": "assistant",
  "content": "Here are the pods in the default namespace: nginx-abc, redis-xyz...",
  "data": {"tool_calls": [], "executed_tool_calls": [...]}
}
```

---

## Slide 9: Human-in-the-Loop Approval

### How It Works

1. User asks agent to perform an action
2. Agent identifies a tool that requires approval
3. Agent pauses and returns pending tool calls
4. User reviews and approves (or rejects)
5. Agent executes the approved tool

### Response with Pending Approval

```json
{
  "role": "assistant",
  "content": "I'll delete the pod. This requires your approval.",
  "data": {
    "tool_calls": [{
      "id": "tc_123",
      "name": "delete_pod",
      "input": {"name": "nginx-abc", "namespace": "production"},
      "execute": false
    }]
  }
}
```

---

## Slide 10: Custom Agent Logic

### Using Functions for Complex Workflows

```python
from dcaf.core import Agent, AgentResult, serve

def my_agent(messages: list, context: dict) -> AgentResult:
    # Access platform context
    tenant = context.get("tenant_name")
    
    # Classify intent first
    classifier = Agent(system="Classify as: query, action, or unknown")
    intent = classifier.run(messages)
    
    if "action" in intent.text.lower():
        # Use tools for actions
        executor = Agent(
            tools=[list_pods, delete_pod],
            system=f"You are helping tenant: {tenant}"
        )
        result = executor.run(messages)
        return AgentResult(text=result.text)
    
    # Just answer the question
    return AgentResult(text=intent.text)

serve(my_agent)
```

**Any structure you need.** Multiple LLM calls, branching, orchestration.

---

## Slide 11: Platform Context

### Automatic Context Extraction

The framework automatically extracts platform context from incoming requests:

```python
def my_agent(messages: list, context: dict) -> AgentResult:
    # Context is extracted for you
    tenant = context.get("tenant_name")
    namespace = context.get("k8s_namespace")
    user_id = context.get("user_id")
    
    # Use it in your logic
    agent = Agent(
        tools=[...],
        system=f"Assisting tenant {tenant} in namespace {namespace}"
    )
    ...
```

### Available Context Fields

- `tenant_name` - DuploCloud tenant
- `k8s_namespace` - Kubernetes namespace
- `user_id` - Requesting user
- `duplo_token` - Authentication token
- Custom fields from your integration

---

## Slide 12: Streaming Responses

### Real-Time Token-by-Token Output

```bash
curl -X POST http://localhost:8000/api/chat-stream \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Explain Kubernetes"}]}'
```

### NDJSON Response Stream

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

| Type | Description |
|------|-------------|
| `text_delta` | Incremental text from the LLM |
| `tool_calls` | Tools requiring approval |
| `executed_tool_calls` | Results from executed tools |
| `done` | Stream completed |
| `error` | An error occurred |

---

## Slide 13: Adding Custom Endpoints

### Extend Your Agent Server

```python
from dcaf.core import Agent, serve
from fastapi import APIRouter

agent = Agent(tools=[...])

# Create custom router
custom_router = APIRouter()

@custom_router.get("/api/custom/schema")
async def get_schema():
    return {"tools": ["list_pods", "delete_pod"]}

@custom_router.get("/api/custom/health")
async def detailed_health():
    return {"status": "healthy", "tools_loaded": 2}

# Include custom routes
serve(agent, additional_routers=[custom_router])
```

---

## Slide 14: Programmatic App Control

### Using create_app() for Full Control

```python
from dcaf.core import Agent, create_app
import uvicorn

agent = Agent(tools=[...])
app = create_app(agent)

# Add middleware, custom configuration, etc.
@app.middleware("http")
async def log_requests(request, call_next):
    print(f"Request: {request.url}")
    return await call_next(request)

# Run with full uvicorn control
uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## Slide 15: Docker Deployment

### Production-Ready Container

```python
# main.py
import os
from dcaf.core import Agent, serve
from my_tools import list_pods, delete_pod

agent = Agent(
    tools=[list_pods, delete_pod],
    system="You are a Kubernetes assistant."
)

if __name__ == "__main__":
    serve(
        agent,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        workers=int(os.getenv("WORKERS", 4)),
        timeout_keep_alive=int(os.getenv("KEEP_ALIVE", 30)),
    )
```

### Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

### Run with Configuration

```bash
docker run -e WORKERS=8 -e KEEP_ALIVE=60 -p 8000:8000 my-agent:latest
```

---

## Slide 16: Kubernetes Deployment

### Health Check Configuration

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
            timeoutSeconds: 5
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            periodSeconds: 5
```

**Note:** The `/health` endpoint is non-blocking, so health checks won't timeout during long LLM calls.

---

## Slide 17: Complete Example - Kubernetes Agent

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool
import subprocess

def kubectl(cmd: str) -> str:
    result = subprocess.run(f"kubectl {cmd}", shell=True, capture_output=True, text=True)
    return result.stdout or result.stderr

@tool(description="List Kubernetes pods in a namespace")
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

@tool(description="Get details about a specific pod")
def describe_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"describe pod {name} -n {namespace}")

@tool(requires_approval=True, description="Delete a Kubernetes pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")

@tool(requires_approval=True, description="Restart a deployment")
def restart_deployment(name: str, namespace: str = "default") -> str:
    return kubectl(f"rollout restart deployment {name} -n {namespace}")

agent = Agent(
    tools=[list_pods, describe_pod, delete_pod, restart_deployment],
    system="You are a Kubernetes assistant. Help users manage their cluster.",
)

if __name__ == "__main__":
    serve(agent, port=8000, workers=4)
```

---

## Slide 18: Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Your Code                                │
│                                                                  │
│   agent = Agent(tools=[...])    OR    def my_agent(messages, ctx)│
│   serve(agent)                        serve(my_agent)            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        DCAF Core                                 │
│                                                                  │
│   • Receives HTTP request                                       │
│   • Converts to simple message format                           │
│   • Runs your agent logic                                       │
│   • Handles tool approvals automatically                        │
│   • Returns response in HelpDesk protocol                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LLM (AWS Bedrock)                             │
│                                                                  │
│   Claude 3.5 Sonnet / Claude 4 / etc.                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Slide 19: Key Concepts

| Concept | Description |
|---------|-------------|
| **Agent** | Your LLM-powered assistant with tools |
| **Tool** | A function the agent can call |
| **Approval** | Human authorization for sensitive tools |
| **serve()** | One-line REST API server |
| **create_app()** | Programmatic FastAPI control |
| **Platform Context** | Runtime environment (tenant, namespace, etc.) |
| **AgentResult** | Return type for custom agent functions |

---

## Slide 20: Getting Started

### Installation

```bash
pip install git+https://github.com/duplocloud/dcaf.git
```

### Minimal Example

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool

@tool(description="Say hello")
def greet(name: str) -> str:
    return f"Hello, {name}!"

agent = Agent(tools=[greet])
serve(agent)
```

### Documentation

- **Core Overview**: `docs/core/index.md`
- **Server Guide**: `docs/core/server.md`
- **Custom Agents**: `docs/guides/custom-agents.md`
- **Streaming**: `docs/guides/streaming.md`

---

## Slide 21: Q&A

# Questions?

### Key Takeaways

1. **Simple API** - `Agent` + `serve()` is all you need
2. **Tool calling** - Decorator-based with auto-generated schemas
3. **Human-in-the-loop** - Built-in approval for sensitive operations
4. **Production-ready** - Workers, keep-alive, health checks included
5. **Flexible** - Use classes or functions, your choice

---

*Presentation created January 2026*
*DCAF Core - vnext branch*
