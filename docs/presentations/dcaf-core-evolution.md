# DCAF Core: The Evolution

A presentation comparing the original DCAF v1 API to the new Core API.

---

## Slide 1: Title

# DCAF Core: The Evolution
### From Complexity to Simplicity

**DCAF** = DuploCloud Agent Framework

A Python framework for building LLM-powered AI agents with:
- Tool calling
- Human-in-the-loop approval
- Production-ready REST API

---

## Slide 2: The Problem We Solved

### Original v1 API Required Too Much Boilerplate

Developers had to:

1. ❌ Manually instantiate the LLM client
2. ❌ Configure tool schemas by hand (verbose JSON)
3. ❌ Wire up the agent, app, and server separately
4. ❌ Manage uvicorn configuration directly
5. ❌ Handle message format conversions

**Result:** 30+ lines of boilerplate before writing any business logic.

---

## Slide 3: Before & After - At a Glance

### v1 (Before): 30+ Lines

```python
from dcaf.llm import BedrockLLM
from dcaf.agents import ToolCallingAgent
from dcaf.tools import tool
from dcaf.agent_server import create_chat_app
import uvicorn
import dotenv

dotenv.load_dotenv()

@tool(
    schema={
        "name": "list_pods",
        "description": "List Kubernetes pods",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": "default"}
            }
        }
    },
    requires_approval=False
)
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

llm = BedrockLLM(region_name="us-east-1")
agent = ToolCallingAgent(
    llm=llm,
    tools=[list_pods],
    system_prompt="You are a Kubernetes assistant.",
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0"
)

app = create_chat_app(agent)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## Slide 4: Before & After - At a Glance (continued)

### Core (After): 10 Lines

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool

@tool(description="List Kubernetes pods")
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

agent = Agent(tools=[list_pods], system="You are a Kubernetes assistant.")

serve(agent)
```

**70% less code. Same capabilities.**

---

## Slide 5: Key Change #1 - Tool Definitions

### v1: Verbose JSON Schema Required

```python
@tool(
    schema={
        "name": "delete_pod",
        "description": "Delete a Kubernetes pod",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Pod name"},
                "namespace": {"type": "string", "default": "default"}
            },
            "required": ["name"]
        }
    },
    requires_approval=True
)
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")
```

### Core: Auto-Generated from Type Hints

```python
@tool(requires_approval=True, description="Delete a Kubernetes pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")
```

**Schemas are inferred from function signatures automatically.**

---

## Slide 6: Key Change #2 - Agent Creation

### v1: Manual LLM + Agent Wiring

```python
# Step 1: Create LLM client
llm = BedrockLLM(region_name="us-east-1")

# Step 2: Create agent with explicit config
agent = ToolCallingAgent(
    llm=llm,
    tools=[list_pods, delete_pod],
    system_prompt="You are a Kubernetes assistant.",
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_iterations=10
)
```

### Core: One-Step Creation

```python
agent = Agent(
    tools=[list_pods, delete_pod],
    system="You are a Kubernetes assistant.",
)
```

**LLM configuration is handled internally with sensible defaults.**

---

## Slide 7: Key Change #3 - Server Setup

### v1: Three-Step Process

```python
# Step 1: Create the FastAPI app
app = create_chat_app(agent)

# Step 2: Configure uvicorn
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        workers=4,
        timeout_keep_alive=30,
    )
```

### Core: One Function

```python
serve(
    agent,
    port=8000,
    workers=4,
    timeout_keep_alive=30,
)
```

**All server configuration in one place.**

---

## Slide 8: Key Change #4 - Custom Agent Logic

### v1: Class Inheritance

```python
from dcaf.agents import ToolCallingAgent

class MyAgent(ToolCallingAgent):
    def invoke(self, messages):
        # Pre-processing
        tenant = self.extract_tenant(messages)
        
        # Call parent
        response = super().invoke(messages)
        
        # Post-processing
        self.log_response(tenant, response)
        return response
```

### Core: Simple Functions

```python
from dcaf.core import Agent, AgentResult, serve

def my_agent(messages: list, context: dict) -> AgentResult:
    tenant = context.get("tenant_name")  # Context extracted for you
    
    agent = Agent(tools=[...])
    response = agent.run(messages)
    
    log_response(tenant, response)
    return AgentResult(text=response.text)

serve(my_agent)
```

**No inheritance required. Just functions.**

---

## Slide 9: Key Change #5 - Production Configuration (NEW!)

### v1: Direct uvicorn.run()

```python
import uvicorn

app = create_chat_app(agent)

uvicorn.run(
    app,
    host="0.0.0.0",
    port=8000,
    workers=4,                   # Had to know uvicorn API
    timeout_keep_alive=30,       # Easy to forget
)
```

### Core: Built-in Production Parameters

```python
serve(
    agent,
    port=8000,
    workers=4,                   # Multiple workers for parallelism
    timeout_keep_alive=30,       # Match load balancer timeout
    log_level="warning",
)
```

**Production configuration is first-class, not an afterthought.**

---

## Slide 10: API Mapping Reference

| v1 Concept | Core Equivalent |
|------------|-----------------|
| `BedrockLLM()` | Built into `Agent` |
| `ToolCallingAgent(llm=..., tools=...)` | `Agent(tools=...)` |
| `system_prompt` | `system` |
| `model_id` | `model` (or env var) |
| `create_chat_app(agent)` | `create_app(agent)` |
| `uvicorn.run(app, ...)` | `serve(agent, ...)` |
| `response.content` | `response.text` |
| `response.data.tool_calls` | `response.pending_tools` |
| `/api/sendMessage` | `/api/chat` |
| `/api/sendMessageStream` | `/api/chat-stream` |

---

## Slide 11: Architecture - What Changed Under the Hood

### v1 Architecture
```
┌─────────────────────────────────────────────────┐
│  Your Code                                      │
│  (Manual wiring of LLM + Agent + Server)        │
└──────────────────────┬──────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   ┌─────────┐   ┌───────────┐   ┌─────────┐
   │BedrockLLM│   │ToolCalling│   │ FastAPI │
   │         │   │   Agent   │   │  Server │
   └─────────┘   └───────────┘   └─────────┘
```

### Core Architecture
```
┌─────────────────────────────────────────────────┐
│  Your Code                                      │
│  agent = Agent(tools=[...])                     │
│  serve(agent)                                   │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│              DCAF Core (Facade)                 │
│  Manages: LLM, Tools, Server, Approvals         │
└─────────────────────────────────────────────────┘
```

**Complexity hidden behind a simple facade.**

---

## Slide 12: Backward Compatibility

### You Don't Have to Migrate Everything at Once

The v1 API still works:

```python
# This still works fine
from dcaf.llm import BedrockLLM
from dcaf.agents import ToolCallingAgent
from dcaf.agent_server import create_chat_app

llm = BedrockLLM()
agent = ToolCallingAgent(llm=llm, tools=[...])
app = create_chat_app(agent)
```

### Legacy Endpoints Still Supported

| Old Endpoint | New Endpoint | Status |
|--------------|--------------|--------|
| `/api/sendMessage` | `/api/chat` | Both work |
| `/api/sendMessageStream` | `/api/chat-stream` | Both work |

---

## Slide 13: Migration Strategy

### Recommended Approach

1. **New agents** → Use Core API
2. **Existing agents** → Migrate when you need to modify them
3. **Clients** → Update to new endpoints when convenient

### Migration Steps

1. Update imports: `from dcaf.core import Agent, serve`
2. Simplify tool definitions (remove verbose schemas)
3. Replace `ToolCallingAgent` with `Agent`
4. Replace `create_chat_app()` + `uvicorn.run()` with `serve()`
5. (Optional) Update client endpoints to `/api/chat`

---

## Slide 14: Real-World Example - Kubernetes Agent

### v1 Version (45 lines)

```python
from dcaf.llm import BedrockLLM
from dcaf.agents import ToolCallingAgent
from dcaf.tools import tool
from dcaf.agent_server import create_chat_app
import uvicorn
import dotenv

dotenv.load_dotenv()

@tool(schema={"name": "list_pods", "description": "List pods", 
      "input_schema": {"type": "object", "properties": {"namespace": {"type": "string"}}}})
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

@tool(schema={"name": "delete_pod", "description": "Delete a pod",
      "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, 
      "namespace": {"type": "string"}}, "required": ["name"]}}, requires_approval=True)
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")

llm = BedrockLLM(region_name="us-east-1")
agent = ToolCallingAgent(
    llm=llm,
    tools=[list_pods, delete_pod],
    system_prompt="You are a Kubernetes assistant.",
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0"
)

app = create_chat_app(agent)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=4)
```

---

## Slide 15: Real-World Example - Kubernetes Agent (continued)

### Core Version (18 lines)

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool

@tool(description="List Kubernetes pods")
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

@tool(requires_approval=True, description="Delete a Kubernetes pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")

agent = Agent(
    tools=[list_pods, delete_pod],
    system="You are a Kubernetes assistant.",
)

serve(agent, workers=4)
```

**60% reduction in code. 100% of functionality.**

---

## Slide 16: New Production Features

### `serve()` Now Includes Production Configuration

```python
serve(
    agent,
    port=8000,
    workers=4,              # Utilize multiple CPU cores
    timeout_keep_alive=30,  # Match AWS ALB timeout
    log_level="warning",
)
```

### Parameters

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `workers` | `1` | Worker processes for parallelism |
| `timeout_keep_alive` | `5` | Keep-alive timeout (seconds) |

### Best Practices

- **Production**: `workers = (2 × cpu_cores) + 1`
- **AWS ALB**: Set `timeout_keep_alive ≥ 30` (ALB default is 60s)
- **Development**: Use `reload=True` with `workers=1`

---

## Slide 17: Summary - Why Core is Better

| Aspect | v1 | Core |
|--------|----|----|
| Lines of code | 30-45 | 10-18 |
| Tool schemas | Manual JSON | Auto-generated |
| LLM setup | Explicit | Built-in |
| Server setup | 3 steps | 1 function |
| Custom logic | Inheritance | Functions |
| Production config | DIY | First-class |
| Learning curve | Steep | Gentle |

---

## Slide 18: Getting Started

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

### Test It

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Greet Alice"}]}'
```

---

## Slide 19: Resources

### Documentation

- **Core Overview**: `docs/core/index.md`
- **Server Guide**: `docs/core/server.md`
- **Migration Guide**: `docs/guides/migration.md`
- **Custom Agents**: `docs/guides/custom-agents.md`

### Architecture

- **Engineering Handoff**: `docs/engineering-handoff.md`
- **ADRs**: `docs/adrs/`

### Support

- GitHub: `github.com/duplocloud/dcaf`
- Issues: `github.com/duplocloud/dcaf/issues`

---

## Slide 20: Q&A

# Questions?

### Key Takeaways

1. **70% less boilerplate** - Focus on business logic
2. **Same capabilities** - Tool calling, approvals, streaming
3. **Production-ready** - Built-in workers and keep-alive config
4. **Backward compatible** - Migrate at your own pace
5. **Simple API** - `Agent` + `serve()` is all you need

---

*Presentation created January 2026*
*DCAF Core - vnext branch*

