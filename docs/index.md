# DCAF - DuploCloud Agent Framework

**DCAF (DuploCloud Agent Framework)** is a Python framework for building LLM-powered AI agents with tool calling and human-in-the-loop approval.

---

## Quick Start

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool

# 1. Define tools
@tool(description="List Kubernetes pods")
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

@tool(requires_approval=True, description="Delete a pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")

# 2. Create an agent
agent = Agent(tools=[list_pods, delete_pod])

# 3. Serve it
serve(agent)  # Running at http://0.0.0.0:8000
```

Test it:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What pods are running?"}]}'
```

---

## Key Features

| Feature | Description |
|---------|-------------|
| 🛠️ **Tool Calling** | Easy decorator-based tool definitions with auto-generated, dict, or Pydantic schemas |
| ✅ **Human-in-the-Loop** | Built-in approval flow for dangerous operations |
| 🔌 **Interceptors** | Hook into request/response for validation, context, security |
| 🔄 **Framework Adapters** | Swap LLM frameworks (Agno, Strands, LangChain) with one parameter |
| 🔗 **HelpDesk Protocol** | Full compatibility with DuploCloud HelpDesk messaging |
| 🌐 **REST API** | One-line server with `serve(agent)` |
| 📡 **Streaming** | Real-time token-by-token responses |
| 🔀 **Custom Logic** | Build agents with any structure you need |

---

## Architecture

### How It Works

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
│   1. Receives HTTP request from HelpDesk                        │
│   2. Converts to simple message format                          │
│   3. Runs your agent logic                                      │
│   4. Handles tool approvals automatically                       │
│   5. Returns response in HelpDesk protocol                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LLM (AWS Bedrock)                             │
│                                                                  │
│   Claude 3.5 Sonnet / Claude 4 / etc.                           │
└─────────────────────────────────────────────────────────────────┘
```

### Request/Response Flow

```
  DuploCloud HelpDesk                      Your Agent
         │                                      │
         │  POST /api/chat                      │
         │  {"messages": [...]}                 │
         │ ───────────────────────────────────► │
         │                                      │
         │                              ┌───────┴───────┐
         │                              │ Agent.run()   │
         │                              │ calls LLM     │
         │                              │ with tools    │
         │                              └───────┬───────┘
         │                                      │
         │  Tool needs approval?                │
         │  ◄─────────────────────────────────  │
         │  {"tool_calls": [...]}               │
         │                                      │
    ┌────┴────┐                                 │
    │  User   │                                 │
    │ Approves│                                 │
    └────┬────┘                                 │
         │                                      │
         │  POST /api/chat                      │
         │  {tool_calls: [execute: true]}       │
         │ ───────────────────────────────────► │
         │                                      │
         │                              ┌───────┴───────┐
         │                              │ Execute tool  │
         │                              │ Return result │
         │                              └───────┬───────┘
         │                                      │
         │  {"content": "Done!", ...}           │
         │  ◄─────────────────────────────────  │
```

### Component Overview

| Component | What It Does |
|-----------|--------------|
| **Agent** | Your LLM-powered assistant with tools |
| **Tools** | Functions the agent can call (with optional approval) |
| **serve()** | Runs your agent as a REST API |
| **HelpDesk Protocol** | Message format for DuploCloud integration |

For internal architecture details, see [Engineering Handoff](./engineering-handoff.md).

---

## Two Ways to Build Agents

### Option 1: Simple (Agent Class)

For most use cases:

```python
from dcaf.core import Agent, serve

agent = Agent(
    tools=[list_pods, delete_pod],
    system="You are a Kubernetes assistant.",
)
serve(agent)
```

### Option 2: Custom Function

For complex logic (multiple LLM calls, branching, etc.):

```python
from dcaf.core import Agent, AgentResult, serve

def my_agent(messages: list, context: dict) -> AgentResult:
    # Classify intent
    classifier = Agent(system="Classify as: query or action")
    intent = classifier.run(messages)
    
    if "action" in intent.text:
        # Use tools for actions
        executor = Agent(tools=[...])
        result = executor.run(messages)
        return AgentResult(text=result.text, ...)
    
    return AgentResult(text=intent.text)

serve(my_agent)
```

See [Custom Agents Guide](./guides/custom-agents.md) for patterns.

---

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/chat` | POST | Synchronous chat |
| `/api/chat-stream` | POST | Streaming (NDJSON) |

---

## Tool Approval

Tools that modify state should require approval:

```python
@tool(requires_approval=True, description="Delete a pod")
def delete_pod(name: str) -> str:
    return kubectl(f"delete pod {name}")
```

The agent will pause and ask for approval before executing.

---

## Documentation

### Getting Started

- [Installation & Quick Start](./getting-started.md)

### Core Framework

- [Core Overview](./core/index.md) - The Agent class and API
- [Server](./core/server.md) - Running agents as REST APIs
- [HelpDesk Protocol](./core/helpdesk-protocol.md) - Full DuploCloud HelpDesk compatibility
- [Framework Adapters](./guides/framework-adapters.md) - Swap between Agno, Strands, LangChain
- [Interceptors Guide](./guides/interceptors.md) - Hook into request/response pipeline
- [Custom Agents Guide](./guides/custom-agents.md) - Building complex agents

### Reference

- [Tools](./api-reference/tools.md) - Creating tools with `@tool`
- [Schemas](./api-reference/schemas.md) - Message format reference
- [Streaming](./guides/streaming.md) - Streaming responses

### Architecture

- [Architecture Guide](./architecture.md) - How DCAF works internally
- [Engineering Handoff](./engineering-handoff.md) - Team handoff documentation
- [Architecture Decision Records](./adrs/) - Design decisions

### Legacy (v1)

The original API is still available for existing integrations:

- [BedrockLLM](./api-reference/llm.md) - Direct Bedrock access
- [Agents (v1)](./api-reference/agents.md) - Legacy agent classes
- [Agent Server](./api-reference/agent-server.md) - Legacy server setup

---

## Installation

```bash
# From GitHub
pip install git+https://github.com/duplocloud/service-desk-agents.git

# For development
git clone https://github.com/duplocloud/service-desk-agents.git
cd service-desk-agents
pip install -r requirements.txt
```

---

## Requirements

- Python 3.12+
- AWS credentials with Bedrock access
- Dependencies: `fastapi`, `pydantic`, `uvicorn`, `boto3`

---

## License

MIT License - See [LICENSE](../LICENSE) for details.

---

## Support

- GitHub Issues: [service-desk-agents](https://github.com/duplocloud/service-desk-agents/issues)
- DuploCloud Support: support@duplocloud.com
