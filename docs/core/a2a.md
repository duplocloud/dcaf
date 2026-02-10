# A2A (Agent-to-Agent) Protocol

DCAF supports the **A2A (Agent-to-Agent) protocol** developed by Google, enabling agents to discover and communicate with each other using standardized HTTP/JSON-RPC interfaces.

---

## Overview

A2A is an open protocol for agent-to-agent communication that enables:

- 🔍 **Agent Discovery**: Agents expose a card describing their capabilities
- 📡 **Task Execution**: Agents can send tasks to other agents
- ⚡ **Async Support**: Long-running tasks can execute asynchronously
- 🌐 **Standard Protocol**: Uses HTTP, JSON-RPC, and SSE (Server-Sent Events)

### Why A2A?

Traditional monolithic agents try to do everything. With A2A, you can:

- **Specialize**: Build focused agents that excel at specific domains (K8s, AWS, databases)
- **Compose**: Combine specialist agents into powerful multi-agent systems
- **Scale**: Distribute work across multiple agents
- **Interoperate**: Work with agents from other frameworks that support A2A

---

## Quick Start

### Server: Expose an Agent via A2A

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool

@tool(description="List Kubernetes pods")
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

# Create agent with A2A identity
agent = Agent(
    name="k8s-assistant",              # A2A name (required for A2A)
    description="Kubernetes helper",   # A2A description
    tools=[list_pods],
)

# Enable A2A alongside regular REST API
serve(agent, port=8000, a2a=True)
```

When A2A is enabled, these endpoints are added:

| Endpoint | Purpose |
|----------|---------|
| `GET /.well-known/agent.json` | Agent card (discovery) |
| `POST /a2a/tasks/send` | Receive tasks |
| `GET /a2a/tasks/{id}` | Task status |

### Client: Call a Remote Agent

```python
from dcaf.core.a2a import RemoteAgent

# Connect to remote agent
k8s = RemoteAgent(url="http://k8s-agent:8000")

# Send a task
result = k8s.send("What pods are failing in production?")
print(result.text)

# Check agent capabilities
print(f"Agent: {k8s.name}")           # "k8s-assistant"
print(f"Skills: {k8s.skills}")        # ["list_pods", ...]
```

---

## Agent Card (Discovery)

When you expose an agent via A2A, it automatically generates an **Agent Card** that describes its capabilities. You can also provide a custom card for full control over the A2A discovery metadata.

### Auto-Generated Card

By default, the card is generated from your `Agent` instance:

```json
{
  "name": "k8s-assistant",
  "description": "Manages Kubernetes clusters",
  "url": "http://k8s-agent:8000",
  "skills": ["list_pods", "delete_pod", "describe_pod"],
  "version": "1.0",
  "metadata": {
    "framework": "dcaf",
    "model": "anthropic.claude-3-sonnet-20240229-v1:0",
    "provider": "bedrock"
  }
}
```

### Custom Agent Card

For full control over the agent card — including fields from the [A2A spec](https://a2a.cx) that DCAF doesn't auto-generate — pass `a2a_agent_card` to `serve()` or `create_app()`.

#### Using an AgentCard instance

```python
from dcaf.core import Agent, serve
from dcaf.core.a2a.models import AgentCard

agent = Agent(name="my-agent", tools=[...])

custom_card = AgentCard(
    name="ci-cd-agent",
    description="Jenkins CI/CD assistant",
    url="",  # Set automatically from request URL
    skills=["fetch_logs", "trigger_build"],
    version="2.0",
    metadata={"org": "duplocloud", "team": "platform"},
)

serve(agent, a2a=True, a2a_agent_card=custom_card)
```

#### Using a dict (full A2A spec compliance)

Pass a dict to include arbitrary fields from the A2A spec without being limited to the `AgentCard` model:

```python
from dcaf.core import Agent, create_app

agent = Agent(name="my-agent", tools=[...])

app = create_app(agent, a2a=True, a2a_agent_card={
    "name": "ci-cd-agent",
    "description": "Jenkins CI/CD assistant",
    "skills": ["fetch_logs", "trigger_build"],
    "authentication": {"schemes": ["bearer"]},
    "capabilities": {"streaming": True, "pushNotifications": False},
    "provider": {"organization": "DuploCloud"},
})
```

!!! note
    The `url` field is always set dynamically from the incoming request's base URL, regardless of whether you provide a custom card or use auto-generation.

### Accessing Agent Cards

```python
from dcaf.core.a2a import RemoteAgent

remote = RemoteAgent(url="http://k8s-agent:8000")

# Card is fetched automatically on first access
print(remote.card.name)         # "k8s-assistant"
print(remote.card.description)  # "Manages Kubernetes clusters"
print(remote.card.skills)       # ["list_pods", "delete_pod", ...]
```

---

## Multi-Agent Patterns

### Pattern 1: Peer-to-Peer

Agents directly communicate with each other.

```python
# === k8s_agent.py ===
from dcaf.core import Agent, serve

agent = Agent(
    name="k8s-assistant",
    tools=[list_pods, delete_pod],
)
serve(agent, port=8001, a2a=True)


# === aws_agent.py ===
from dcaf.core import Agent, serve

agent = Agent(
    name="aws-assistant",
    tools=[list_ec2, describe_vpc],
)
serve(agent, port=8002, a2a=True)


# === client.py ===
from dcaf.core.a2a import RemoteAgent

k8s = RemoteAgent(url="http://localhost:8001")
aws = RemoteAgent(url="http://localhost:8002")

# Call each agent directly
k8s_result = k8s.send("List pods")
aws_result = aws.send("List EC2 instances")
```

### Pattern 2: Orchestration

An orchestrator agent routes requests to specialist agents.

```python
from dcaf.core import Agent
from dcaf.core.a2a import RemoteAgent

# Connect to specialist agents
k8s = RemoteAgent(url="http://k8s-agent:8000")
aws = RemoteAgent(url="http://aws-agent:8000")
db = RemoteAgent(url="http://db-agent:8000")

# Orchestrator uses remote agents as tools
orchestrator = Agent(
    name="orchestrator",
    tools=[
        k8s.as_tool(),  # Wraps remote agent as a tool
        aws.as_tool(),
        db.as_tool(),
    ],
    system="""You are an orchestrator that routes requests to specialist agents.
    Use k8s_assistant for Kubernetes questions.
    Use aws_assistant for AWS questions.
    Use db_assistant for database questions."""
)

# The LLM decides which specialist to call
response = orchestrator.run([
    {"role": "user", "content": "How many pods are running and what's my AWS bill?"}
])
# The orchestrator will call both k8s and aws agents
```

---

## RemoteAgent API Reference

### Constructor

```python
RemoteAgent(
    url: str,
    name: str | None = None,
    adapter: A2AClientAdapter | None = None,
)
```

**Parameters:**

- `url`: Base URL of the remote agent (e.g., "http://k8s-agent:8000")
- `name`: Optional name override (uses card name if not provided)
- `adapter`: Optional custom A2A client adapter (default: Agno)

### Methods

#### send()

Send a message and wait for response (synchronous).

```python
def send(
    message: str,
    context: dict | None = None,
    timeout: float = 60.0,
) -> TaskResult
```

**Example:**

```python
result = remote.send(
    "List pods in production",
    context={"tenant_name": "prod"},
    timeout=120.0,
)
print(result.text)
print(result.status)  # "completed", "failed", "pending"
```

#### send_async()

Send a message asynchronously (returns immediately).

```python
def send_async(
    message: str,
    context: dict | None = None,
) -> str  # Returns task_id
```

**Example:**

```python
task_id = remote.send_async("Analyze all pod logs")

# Later, check status
result = remote.get_task_status(task_id)
if result.status == "completed":
    print(result.text)
```

#### as_tool()

Convert the remote agent to a tool for use by other agents.

```python
def as_tool() -> Tool
```

**Example:**

```python
k8s = RemoteAgent(url="http://k8s-agent:8000")

# Use as a tool
orchestrator = Agent(
    tools=[k8s.as_tool()],
    system="Use k8s_assistant for Kubernetes questions"
)
```

### Properties

```python
remote.card         # AgentCard: Agent metadata
remote.name         # str: Agent name
remote.description  # str: Agent description
remote.skills       # list[str]: List of tool names
```

---

## TaskResult

Response from a remote agent.

```python
@dataclass
class TaskResult:
    task_id: str              # ID of the task
    text: str                 # Response text
    status: str               # "completed", "failed", "pending"
    artifacts: list[dict]     # Structured outputs
    error: str | None         # Error message (if failed)
    metadata: dict            # Additional metadata
```

**Example:**

```python
result = remote.send("List pods")

print(result.task_id)    # "task_abc123"
print(result.text)       # "Here are the pods: nginx-abc, redis-xyz..."
print(result.status)     # "completed"
print(result.artifacts)  # []
```

---

## Server Configuration

### Basic Setup

```python
from dcaf.core import Agent, serve

agent = Agent(
    name="my-agent",              # Required for A2A
    description="Does X, Y, Z",   # Recommended for A2A
    tools=[...],
)

# Enable A2A
serve(agent, port=8000, a2a=True)
```

### Advanced Setup

For more control over the FastAPI app:

```python
from dcaf.core import Agent, create_app
import uvicorn

agent = Agent(name="my-agent", tools=[...])

# Create app with A2A enabled
app = create_app(agent, a2a=True)

# Add custom middleware, etc.
@app.middleware("http")
async def log_requests(request, call_next):
    print(f"Request: {request.url}")
    return await call_next(request)

# Run with custom configuration
uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Custom A2A Routes

You can also manually add A2A routes:

```python
from dcaf.core import Agent, create_app
from dcaf.core.a2a import create_a2a_routes

agent = Agent(name="my-agent", tools=[...])

# Create base app without A2A
app = create_app(agent, a2a=False)

# Add A2A routes manually
for router in create_a2a_routes(agent):
    app.include_router(router)
```

---

## Complete Example: Multi-Agent System

This example shows a complete multi-agent system with three specialist agents and an orchestrator.

### Specialist Agent 1: Kubernetes

```python
# k8s_agent.py
from dcaf.core import Agent, serve
from dcaf.tools import tool
import subprocess

def kubectl(cmd: str) -> str:
    result = subprocess.run(
        f"kubectl {cmd}",
        shell=True,
        capture_output=True,
        text=True
    )
    return result.stdout or result.stderr

@tool(description="List pods in a namespace")
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

@tool(requires_approval=True, description="Delete a pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")

agent = Agent(
    name="k8s-assistant",
    description="Manages Kubernetes clusters",
    tools=[list_pods, delete_pod],
)

if __name__ == "__main__":
    serve(agent, port=8001, a2a=True)
```

### Specialist Agent 2: AWS

```python
# aws_agent.py
from dcaf.core import Agent, serve
from dcaf.tools import tool
import boto3

@tool(description="List EC2 instances")
def list_ec2() -> str:
    ec2 = boto3.client('ec2')
    response = ec2.describe_instances()
    instances = []
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instances.append(f"{instance['InstanceId']} - {instance['State']['Name']}")
    return "\n".join(instances)

agent = Agent(
    name="aws-assistant",
    description="Manages AWS resources",
    tools=[list_ec2],
)

if __name__ == "__main__":
    serve(agent, port=8002, a2a=True)
```

### Orchestrator Agent

```python
# orchestrator.py
from dcaf.core import Agent, serve
from dcaf.core.a2a import RemoteAgent

# Connect to specialist agents
k8s = RemoteAgent(url="http://localhost:8001")
aws = RemoteAgent(url="http://localhost:8002")

# Orchestrator routes to specialists
orchestrator = Agent(
    name="orchestrator",
    description="Routes requests to specialist agents",
    tools=[k8s.as_tool(), aws.as_tool()],
    system="""You are an intelligent orchestrator for infrastructure management.
    
    You have access to two specialist agents:
    - k8s_assistant: For Kubernetes questions (pods, deployments, services)
    - aws_assistant: For AWS questions (EC2, VPC, billing)
    
    Route each question to the appropriate specialist. You can call both if needed.
    """,
)

if __name__ == "__main__":
    serve(orchestrator, port=8000, a2a=True)
```

### Usage

```python
# client.py
from dcaf.core.a2a import RemoteAgent

# Connect to orchestrator
orchestrator = RemoteAgent(url="http://localhost:8000")

# Ask a question - orchestrator will route to k8s agent
result = orchestrator.send("How many pods are running in production?")
print(result.text)

# Ask another - orchestrator will route to aws agent
result = orchestrator.send("List my EC2 instances")
print(result.text)

# Ask complex - orchestrator will call both
result = orchestrator.send("Give me a status of my infrastructure")
print(result.text)
```

---

## Testing

### Testing A2A Server

```python
import pytest
from dcaf.core import Agent
from dcaf.core.a2a import RemoteAgent, generate_agent_card

def test_agent_card_generation():
    agent = Agent(
        name="test-agent",
        description="Test agent",
        tools=[my_tool],
    )
    
    card = generate_agent_card(agent, "http://localhost:8000")
    
    assert card.name == "test-agent"
    assert card.description == "Test agent"
    assert "my_tool" in card.skills

def test_a2a_task_execution():
    # Start agent with A2A in a fixture
    # ...
    
    remote = RemoteAgent(url="http://localhost:8000")
    result = remote.send("Test message")
    
    assert result.status == "completed"
    assert len(result.text) > 0
```

### Integration Testing

```python
import pytest
from dcaf.core import Agent, create_app
from fastapi.testclient import TestClient

@pytest.fixture
def a2a_agent():
    agent = Agent(
        name="test",
        description="Test agent",
        tools=[my_tool],
    )
    return create_app(agent, a2a=True)

def test_agent_card_endpoint(a2a_agent):
    client = TestClient(a2a_agent)
    response = client.get("/.well-known/agent.json")
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test"
    assert "my_tool" in data["skills"]

def test_task_send_endpoint(a2a_agent):
    client = TestClient(a2a_agent)
    response = client.post(
        "/a2a/tasks/send",
        json={
            "id": "task_123",
            "message": "Test message",
            "context": {},
            "status": "pending",
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["completed", "pending", "failed"]
```

---

## Troubleshooting

### Common Issues

**Issue: "No A2A adapter available"**

```
RuntimeError: No A2A adapter available. Install agno with: pip install agno
```

**Solution:** Install required dependencies:

```bash
pip install httpx  # For A2A client
pip install agno   # For Agno adapter (optional)
```

**Issue: "Cannot reach agent at http://..."**

```
ConnectionError: Cannot reach agent at http://k8s-agent:8000
```

**Solution:** 
- Check that the agent is running: `curl http://k8s-agent:8000/.well-known/agent.json`
- Check network connectivity
- Verify the URL is correct

**Issue: Agent card missing tools**

```python
# Agent card shows: "skills": []
```

**Solution:** Make sure tools are provided when creating the agent:

```python
agent = Agent(
    name="my-agent",
    tools=[tool1, tool2],  # Must provide tools
)
```

---

## Client Configuration

### Environment Variables

The A2A client (used by `RemoteAgent`) supports timeout configuration via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `BOTO3_READ_TIMEOUT` | `20` | Read timeout in seconds for HTTP operations |
| `BOTO3_CONNECT_TIMEOUT` | `10` | Connection timeout in seconds |

These are the same variables used by the [Bedrock LLM](../api-reference/llm.md#environment-variables), allowing unified timeout configuration across your application.

**Example:**

```bash
# Set longer timeouts for slow networks
export BOTO3_READ_TIMEOUT=60
export BOTO3_CONNECT_TIMEOUT=30
```

```python
from dcaf.core.a2a import RemoteAgent

# Client will use environment-configured timeouts
remote = RemoteAgent(url="http://k8s-agent:8000")
result = remote.send("List pods")
```

---

## Best Practices

### 1. Name Your Agents

Always provide a meaningful name for A2A agents:

```python
# Good
agent = Agent(
    name="k8s-prod-assistant",
    description="Manages production Kubernetes cluster",
    ...
)

# Bad
agent = Agent(...)  # Default name: "dcaf-agent"
```

### 2. Provide Clear Descriptions

Help other agents understand what your agent does:

```python
agent = Agent(
    name="k8s-assistant",
    description="Manages Kubernetes clusters. Can list, describe, delete pods and deployments.",
    ...
)
```

### 3. Handle Errors Gracefully

```python
from dcaf.core.a2a import RemoteAgent

remote = RemoteAgent(url="http://k8s-agent:8000")

try:
    result = remote.send("List pods", timeout=30.0)
    if result.status == "failed":
        print(f"Task failed: {result.error}")
    else:
        print(result.text)
except ConnectionError:
    print("Agent is not available")
except TimeoutError:
    print("Task timed out")
```

### 4. Use Async for Long-Running Tasks

```python
# For tasks that take > 30 seconds
task_id = remote.send_async("Analyze all logs")

# Poll for completion
import time
while True:
    result = remote.get_task_status(task_id)
    if result.status in ["completed", "failed"]:
        break
    time.sleep(5)
```

### 5. Secure Your A2A Endpoints

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def verify_token(credentials = Depends(security)):
    if credentials.credentials != "your-secret-token":
        raise HTTPException(status_code=401)

# Add to routes
app = create_app(agent, a2a=True)

@app.middleware("http")
async def auth_middleware(request, call_next):
    # Implement your auth logic
    return await call_next(request)
```

---

## See Also

- [Core Overview](./index.md)
- [Server Guide](./server.md)
- [Custom Agents Guide](../guides/custom-agents.md)
- [Building Tools](../guides/building-tools.md)
- [A2A Protocol Specification](https://a2a.cx)

