# A2A Integration - Engineer Handoff Documentation

## Overview

This document provides a working example of DCAF's A2A (Agent-to-Agent) protocol integration for engineer handoff.

**Status:** ✅ Fully functional and tested  
**Date:** January 9, 2026  
**Fix Applied:** httpx client configuration issue resolved

---

## What is A2A?

A2A (Agent-to-Agent) is Google's open protocol for agent communication that enables:

- **Agent Discovery**: Agents expose a card describing their capabilities
- **Task Execution**: Agents can send tasks to other agents
- **Orchestration**: Build multi-agent systems where specialist agents communicate

### Use Cases

- **Microservices Architecture**: Deploy specialized agents (K8s, AWS, Database) that communicate
- **Multi-Agent Systems**: Orchestrator agent routes requests to appropriate specialists
- **Distributed AI**: Agents running in different environments/regions working together

---

## Quick Start

### 1. Prerequisites

```bash
# Install dependencies
cd /Users/chuckconway/Projects/dcaf
source .venv/bin/activate
uv pip install -r requirements.txt

# Set AWS profile (for Bedrock)
export AWS_PROFILE=test10
```

### 2. Run the Tests

#### Option A: Unit Tests (No Server Required)

```bash
python -m pytest tests/test_a2a_integration.py -v
```

**Expected Output:**
```
✅ 7 passed - All A2A features working correctly
```

#### Option B: Full Integration Test (Live Agents)

**Terminal 1 - Start K8s Agent:**
```bash
export AWS_PROFILE=test10
python examples/a2a_example.py k8s
```

**Terminal 2 - Run Client:**
```bash
export AWS_PROFILE=test10
python examples/a2a_example.py client
```

---

## Code Examples

### Example 1: Creating an A2A-Enabled Agent

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool

@tool(description="List Kubernetes pods")
def list_pods(namespace: str = "default") -> str:
    """List all pods in a namespace."""
    return kubectl(f"get pods -n {namespace}")

# Create agent with A2A identity
agent = Agent(
    name="k8s-assistant",              # A2A name (required)
    description="Kubernetes helper",   # A2A description
    tools=[list_pods],
    aws_profile="test10",              # AWS credentials
    aws_region="us-west-2",
)

# Enable A2A alongside regular REST API
serve(agent, port=8001, a2a=True)
```

**A2A Endpoints Exposed:**
- `GET /.well-known/agent.json` - Agent discovery
- `POST /a2a/tasks/send` - Task execution
- `GET /a2a/tasks/{id}` - Task status

### Example 2: Calling a Remote Agent

```python
from dcaf.core.a2a import RemoteAgent

# Connect to remote agent
k8s = RemoteAgent(url="http://localhost:8001")

# Check agent info
print(f"Agent: {k8s.name}")           # "k8s-assistant"
print(f"Skills: {k8s.skills}")        # ["list_pods", ...]

# Send a task
result = k8s.send("List all failing pods in production")
print(result.text)
```

### Example 3: Multi-Agent Orchestration

```python
from dcaf.core import Agent
from dcaf.core.a2a import RemoteAgent

# Connect to specialist agents
k8s = RemoteAgent(url="http://k8s-agent:8001")
aws = RemoteAgent(url="http://aws-agent:8002")
db = RemoteAgent(url="http://db-agent:8003")

# Create orchestrator that routes to specialists
orchestrator = Agent(
    name="orchestrator",
    tools=[k8s.as_tool(), aws.as_tool(), db.as_tool()],
    system="You route requests to specialist agents based on the question."
)

# The LLM decides which specialist to call
response = orchestrator.run([
    {"role": "user", "content": "How many pods are running and what's my AWS bill?"}
])
# Orchestrator will call both k8s and aws agents automatically
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     A2A ARCHITECTURE                         │
└─────────────────────────────────────────────────────────────┘

  ┌──────────────┐                        ┌──────────────┐
  │ Orchestrator │                        │   K8s Agent  │
  │    Agent     │                        │  (Specialist)│
  └──────┬───────┘                        └──────▲───────┘
         │                                       │
         │  1. GET /.well-known/agent.json      │
         │──────────────────────────────────────>│
         │                                       │
         │  2. 200 OK + AgentCard               │
         │<──────────────────────────────────────│
         │     {name, description, skills}       │
         │                                       │
         │  3. POST /a2a/tasks/send              │
         │     {message: "List pods"}            │
         │──────────────────────────────────────>│
         │                                       │
         │  4. 200 OK + TaskResult               │
         │<──────────────────────────────────────│
         │     {status, text, artifacts}         │
         │                                       │
```

---

## File Structure

```
dcaf/core/a2a/
├── __init__.py          # Public API exports
├── models.py            # AgentCard, Task, TaskResult
├── protocols.py         # Abstract interfaces
├── client.py            # RemoteAgent (client)
├── server.py            # Server utilities
└── adapters/
    └── agno.py          # Agno implementation (httpx-based)
```

---

## Configuration

### Environment Variables

```bash
# AWS Configuration
export AWS_PROFILE=test10
export AWS_REGION=us-west-2

# Alternative: Direct credentials (not recommended)
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
```

### Agent Configuration

```python
agent = Agent(
    # A2A Identity
    name="my-agent",                    # Required for A2A
    description="Agent description",    # Recommended
    
    # AWS/Bedrock Configuration
    provider="bedrock",
    model="anthropic.claude-3-sonnet-20240229-v1:0",
    aws_profile="test10",               # Profile from ~/.aws/credentials
    aws_region="us-west-2",
    
    # Tools
    tools=[tool1, tool2],
)
```

---

## Testing Checklist

- [ ] Unit tests pass: `pytest tests/test_a2a_integration.py`
- [ ] Agent card endpoint works: `curl http://localhost:8001/.well-known/agent.json`
- [ ] Task execution works: `POST /a2a/tasks/send`
- [ ] RemoteAgent client connects successfully
- [ ] Tool conversion works: `remote.as_tool()`
- [ ] AWS credentials configured properly
- [ ] No 404 errors (httpx fix applied)

---

## Known Issues & Solutions

### Issue 1: AWS Credential Errors

**Symptom:**
```
ERROR: Partial credentials found in shared-credentials-file
```

**Solution:**
```bash
# Ensure AWS profile is complete in ~/.aws/credentials
export AWS_PROFILE=test10

# Verify credentials
aws sts get-caller-identity --profile test10
```

### Issue 2: Connection Refused

**Symptom:**
```
ConnectionError: Cannot reach agent at http://localhost:8001
```

**Solution:**
- Ensure agent server is running
- Check port is not in use: `lsof -i :8001`
- Verify firewall settings

### Issue 3: 404 Not Found (Fixed)

**Symptom:**
```
404 Not Found on /.well-known/agent.json
```

**Solution:**
Already fixed! The httpx client now uses `trust_env=False` to prevent URL encoding issues.

---

## API Reference

### RemoteAgent Class

```python
class RemoteAgent:
    """Client for communicating with remote A2A agents."""
    
    def __init__(url: str, name: str = None):
        """Connect to remote agent."""
        
    @property
    def card(self) -> AgentCard:
        """Fetch agent card (cached)."""
        
    def send(message: str, context: dict = None, timeout: float = 60.0) -> TaskResult:
        """Send task and wait for response."""
        
    def send_async(message: str, context: dict = None) -> str:
        """Send task asynchronously, returns task_id."""
        
    def as_tool(self) -> Tool:
        """Convert to tool for use by other agents."""
```

### AgentCard

```python
@dataclass
class AgentCard:
    name: str              # Agent identifier
    description: str       # What the agent does
    url: str              # Base URL
    skills: list[str]     # Available tool names
    version: str          # A2A protocol version
    metadata: dict        # Framework info, model, etc.
```

### TaskResult

```python
@dataclass
class TaskResult:
    task_id: str          # Unique task identifier
    text: str             # Response text
    status: str           # "completed", "failed", "pending"
    artifacts: list       # Structured outputs
    error: str | None     # Error message if failed
    metadata: dict        # Additional info
```

---

## Production Deployment

### Docker Example

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Start K8s agent
CMD ["python", "-m", "examples.a2a_example", "k8s"]
```

### Docker Compose

```yaml
version: '3.8'
services:
  k8s-agent:
    build: .
    environment:
      - AWS_PROFILE=test10
      - AWS_REGION=us-west-2
    ports:
      - "8001:8001"
    volumes:
      - ~/.aws:/root/.aws:ro
      
  aws-agent:
    build: .
    environment:
      - AWS_PROFILE=test10
    ports:
      - "8002:8002"
      
  orchestrator:
    build: .
    environment:
      - AWS_PROFILE=test10
    ports:
      - "8000:8000"
    depends_on:
      - k8s-agent
      - aws-agent
```

---

## Support & Documentation

- **Full Docs**: `docs/core/a2a.md`
- **Examples**: `examples/a2a_example.py`
- **Tests**: `tests/test_a2a_integration.py`
- **Fix Details**: `A2A_FIX_SUMMARY.md`
- **Investigation**: `A2A_INVESTIGATION_REPORT.md`

---

## Handoff Checklist

- [x] A2A integration fixed and tested
- [x] Unit tests created (7 tests, all passing)
- [x] Integration example working
- [x] Documentation complete
- [x] AWS profile support verified
- [x] httpx client issue resolved
- [ ] Engineer reviews this document
- [ ] Engineer runs tests successfully
- [ ] Engineer understands architecture
- [ ] Ready for production deployment

---

## Questions?

Contact the team or refer to:
- A2A Protocol Spec: https://a2a.cx
- DCAF Documentation: `docs/core/a2a.md`
- This handoff document location: `A2A_HANDOFF_EXAMPLE.md`
