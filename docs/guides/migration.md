# Migrating from v1 to Core

This guide helps you migrate from the legacy v1 API to the new Core API.

---

## Why Migrate?

The Core API offers:

- **Simpler code** - Fewer imports, less boilerplate
- **One-line server** - `serve(agent)` instead of `create_chat_app()` + `uvicorn.run()`
- **Better defaults** - Sensible configuration out of the box
- **Custom logic support** - Write functions, not just classes
- **Same capabilities** - Tool calling, approvals, streaming all work

---

## Quick Comparison

### Before (v1)

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

### After (Core)

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool

@tool(description="List Kubernetes pods")
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

agent = Agent(
    tools=[list_pods],
    system="You are a Kubernetes assistant.",
)

if __name__ == "__main__":
    serve(agent)
```

**What changed:**
- No `BedrockLLM` instantiation needed
- No `ToolCallingAgent` - just `Agent`
- No `create_chat_app()` + `uvicorn.run()` - just `serve()`
- Simpler `@tool` decorator (schema auto-generated)
- `system_prompt` → `system`

---

## Step-by-Step Migration

### Step 1: Update Imports

```python
# Before
from dcaf.llm import BedrockLLM
from dcaf.agents import ToolCallingAgent
from dcaf.agent_server import create_chat_app

# After
from dcaf.core import Agent, serve
```

### Step 2: Simplify Tools

The `@tool` decorator now auto-generates schemas from type hints:

```python
# Before - explicit schema
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

# After - auto-generated schema
@tool(requires_approval=True, description="Delete a Kubernetes pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    """Delete a pod from the cluster."""
    return kubectl(f"delete pod {name} -n {namespace}")
```

!!! note
    You can still use explicit schemas if needed. The Core API supports both approaches.

### Step 3: Replace Agent Class

```python
# Before
llm = BedrockLLM(region_name="us-east-1")
agent = ToolCallingAgent(
    llm=llm,
    tools=[my_tool],
    system_prompt="You are helpful.",
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_iterations=10
)

# After
agent = Agent(
    tools=[my_tool],
    system="You are helpful.",
    # model is configured via environment or defaults
)
```

### Step 4: Replace Server Setup

```python
# Before
app = create_chat_app(agent)
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

# After
if __name__ == "__main__":
    serve(agent, port=8000)
```

### Step 5: Update Endpoints (Clients)

If you have clients calling your agent:

| Old Endpoint | New Endpoint | Status |
|--------------|--------------|--------|
| `/api/sendMessage` | `/api/chat` | Both work (legacy supported) |
| `/api/sendMessageStream` | `/api/chat-stream` | Both work (legacy supported) |

The legacy endpoints still work, but we recommend updating clients to use the new endpoints.

---

## Common Patterns

### Custom Agent Logic (v1 → Core)

**Before (extending ToolCallingAgent):**

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

**After (custom function):**

```python
from dcaf.core import Agent, AgentResult, serve

def my_agent(messages: list, context: dict) -> AgentResult:
    # Pre-processing
    tenant = context.get("tenant_name")
    
    # Use Agent
    agent = Agent(tools=[...], system="...")
    response = agent.run(messages)
    
    # Post-processing
    log_response(tenant, response)
    
    return AgentResult(text=response.text)

serve(my_agent)
```

### Platform Context

**Before:**

```python
class MyAgent(ToolCallingAgent):
    def invoke(self, messages):
        messages_list = messages.get("messages", [])
        last_user = next(
            (m for m in reversed(messages_list) if m.get("role") == "user"),
            {}
        )
        platform_context = last_user.get("platform_context", {})
        tenant = platform_context.get("tenant_name")
        # ...
```

**After:**

```python
def my_agent(messages: list, context: dict) -> AgentResult:
    # Context is extracted for you
    tenant = context.get("tenant_name")
    # ...
```

### Handling Approvals

**Before (checking response):**

```python
response = agent.invoke(messages)
if response.data.tool_calls:
    # Has pending approvals
    pass
```

**After:**

```python
response = agent.run(messages)
if response.needs_approval:
    # Has pending approvals
    for tool in response.pending_tools:
        print(f"Pending: {tool.name}")
```

---

## Feature Mapping

| v1 Feature | Core Equivalent |
|------------|-----------------|
| `ToolCallingAgent` | `Agent` |
| `BedrockLLM` | Built into `Agent` |
| `create_chat_app(agent)` | `create_app(agent)` |
| `uvicorn.run(app, ...)` | `serve(agent, ...)` |
| `system_prompt` param | `system` param |
| `model_id` param | `model` param (or env var) |
| `max_iterations` param | Built-in with sensible default |
| `AgentMessage` response | `AgentResponse` response |
| `response.content` | `response.text` |
| `response.data.tool_calls` | `response.pending_tools` |
| `/api/sendMessage` | `/api/chat` (legacy still works) |
| `/api/sendMessageStream` | `/api/chat-stream` (legacy still works) |

---

## Keeping Legacy Code

You don't have to migrate everything at once. The legacy API still works:

```python
# This still works fine
from dcaf.llm import BedrockLLM
from dcaf.agents import ToolCallingAgent
from dcaf.agent_server import create_chat_app

llm = BedrockLLM()
agent = ToolCallingAgent(llm=llm, tools=[...])
app = create_chat_app(agent)
```

You can have some agents on v1 and some on Core. They use the same underlying server.

---

## Gradual Migration Strategy

1. **New agents** - Use Core API
2. **Existing agents** - Migrate when you need to modify them
3. **Clients** - Update to new endpoints when convenient (legacy works indefinitely)

---

## Need Help?

- [Core Documentation](../core/index.md)
- [Custom Agents Guide](./custom-agents.md)
- [Legacy API Reference](../api-reference/agents.md)
- GitHub Issues: [service-desk-agents](https://github.com/duplocloud/service-desk-agents/issues)
