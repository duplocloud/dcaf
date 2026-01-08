# DCAF Core

DCAF Core provides a simple, Pythonic API for building AI agents with tool calling and human-in-the-loop approval.

---

## Quick Start

```python
from dcaf.core import Agent, ChatMessage
from dcaf.tools import tool

# 1. Define a tool
@tool(description="List Kubernetes pods")
def list_pods(namespace: str = "default") -> str:
    """List pods in a namespace."""
    return kubectl(f"get pods -n {namespace}")

@tool(requires_approval=True, description="Delete a pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    """Delete a pod. Requires approval."""
    return kubectl(f"delete pod {name} -n {namespace}")

# 2. Create an agent
agent = Agent(tools=[list_pods, delete_pod])

# 3. Run it with messages
response = agent.run(messages=[
    ChatMessage.user("What pods are running? Delete any failing ones.")
])

# 4. Handle approvals
if response.needs_approval:
    for pending in response.pending_tools:
        print(f"Approve {pending.name}? {pending.input}")
    
    # Approve all and continue
    response = response.approve_all()

print(response.text)
```

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Simple API** | One class (`Agent`) for most use cases |
| **Tool Calling** | Easy decorator-based tool definitions |
| **Human-in-the-Loop** | Built-in approval flow for dangerous operations |
| **HelpDesk Compatible** | Full compatibility with DuploCloud HelpDesk protocol |
| **Event Hooks** | Subscribe to events for logging, notifications |
| **Framework Agnostic** | Swap LLM providers without code changes |

---

## The Agent Class

The `Agent` class is the main entry point:

```python
agent = Agent(
    tools=[...],                    # List of tools the agent can use
    model="anthropic.claude-3-sonnet",  # LLM model (optional)
    system_prompt="You are...",     # Static system prompt (optional)
    system_context="Dynamic context",   # Dynamic context (optional, for caching)
    model_config={...},             # Model configuration (optional, e.g., caching)
    high_risk_tools=["rm", "delete"],   # Extra approval requirements (optional)
    on_event=my_handler,            # Event handler(s) (optional)
)
```

### Prompt Caching (Bedrock Only)

Reduce costs by up to 90% and latency by up to 85% with prompt caching. Separate static instructions from dynamic context:

```python
agent = Agent(
    # Static part - cached (same for all requests)
    system_prompt="""
    You are a Kubernetes expert. Your role is to help users manage clusters.
    [Add detailed guidelines here - aim for 1024+ tokens for caching]
    """,
    
    # Dynamic part - NOT cached (changes per request)
    system_context=lambda ctx: f"""
    Tenant: {ctx.get('tenant_name')}
    Namespace: {ctx.get('k8s_namespace')}
    User: {ctx.get('user_email')}
    """,
    
    # Enable caching
    model_config={"cache_system_prompt": True},
    
    tools=[...],
)
```

See [Prompt Caching Guide](../guides/prompt-caching.md) for details.

### Running the Agent

```python
from dcaf.core import Agent, ChatMessage

agent = Agent(tools=[...])

# Simple - single message
response = agent.run(messages=[
    ChatMessage.user("What's the status?")
])
print(response.text)

# With conversation history
response = agent.run(messages=[
    ChatMessage.user("What pods are running?"),
    ChatMessage.assistant("There are 3 pods: nginx, redis, api"),
    ChatMessage.user("Tell me more about nginx"),  # ← Current message (last)
])
```

**Important**: The last message in the list is always treated as the current user message. All previous messages are conversation history.

### Using Plain Dicts (JSON Compatible)

You can also pass plain dictionaries, which is useful when receiving messages from JSON:

```python
# From JSON/API request
response = agent.run(messages=[
    {"role": "user", "content": "What pods are running?"},
    {"role": "assistant", "content": "There are 3 pods..."},
    {"role": "user", "content": "Tell me more"},
])

# Or directly from request data
response = agent.run(
    messages=request_data["messages"],
    context=request_data.get("context"),
)
```

### Handling Approvals

```python
response = agent.run("Delete the pod")

if response.needs_approval:
    # Option 1: Approve all
    response = response.approve_all()
    
    # Option 2: Reject all
    response = response.reject_all("Too risky")
    
    # Option 3: Handle individually
    for tool in response.pending_tools:
        if confirm(f"Run {tool.name}?"):
            tool.approve()
        else:
            tool.reject("User declined")
    response = agent.resume(response.conversation_id)
```

---

## Defining Tools

Use the `@tool` decorator with one of three schema approaches:

### Option 1: Auto-Generate (Simplest)

```python
from dcaf.tools import tool

@tool(description="Get current weather")
def get_weather(city: str, units: str = "celsius") -> str:
    """Get weather for a city."""
    return weather_api.get(city, units)
```

### Option 2: Dict Schema (Full Control)

```python
@tool(
    description="Get current weather",
    schema={
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City name"},
            "units": {"type": "string", "enum": ["celsius", "fahrenheit"]}
        },
        "required": ["city"]
    }
)
def get_weather(city: str, units: str = "celsius") -> str:
    return weather_api.get(city, units)
```

### Option 3: Pydantic Model (Type-Safe)

```python
from pydantic import BaseModel, Field
from typing import Literal

class WeatherInput(BaseModel):
    city: str = Field(..., description="City name")
    units: Literal["celsius", "fahrenheit"] = Field(default="celsius")

@tool(description="Get current weather", schema=WeatherInput)
def get_weather(city: str, units: str = "celsius") -> str:
    return weather_api.get(city, units)
```

### Tool Options

| Option | Default | Description |
|--------|---------|-------------|
| `description` | Docstring | What the tool does (shown to LLM) |
| `requires_approval` | `False` | Whether to require human approval |
| `schema` | Auto-generated | Dict schema OR Pydantic model class |

---

## Approval Rules

**Simple rule**: If EITHER the tool OR the policy says it's risky, require approval.

| Tool `requires_approval` | In `high_risk_tools` | Result |
|--------------------------|----------------------|--------|
| `True` | (any) | Requires approval |
| `False` | No | Auto-executes |
| `False` | Yes | Requires approval |

---

## Event Handling

Subscribe to events for logging, notifications, or audit trails:

```python
def log_events(event):
    print(f"[{event.event_type}] at {event.timestamp}")

def notify_slack(event):
    if event.event_type == "ApprovalRequested":
        slack.post("Approval needed!")

# Single handler
agent = Agent(tools=[...], on_event=log_events)

# Multiple handlers
agent = Agent(tools=[...], on_event=[log_events, notify_slack])
```

### Event Types

- `ConversationStarted` - New conversation began
- `ApprovalRequested` - Tools need approval
- `ToolCallApproved` - User approved a tool
- `ToolCallRejected` - User rejected a tool
- `ToolExecuted` - Tool ran successfully
- `ToolExecutionFailed` - Tool execution failed

---

## Interceptors

Interceptors let you hook into the request/response pipeline. Use them to:

- Add context before sending to the LLM
- Validate or block suspicious input
- Clean up or redact responses

```python
from dcaf.core import Agent, LLMRequest, LLMResponse, InterceptorError

# Request interceptor - runs BEFORE the LLM call
def add_tenant_context(request: LLMRequest) -> LLMRequest:
    """Add tenant info to help the AI understand the environment."""
    tenant = request.context.get("tenant_name", "unknown")
    request.add_system_context(f"User's tenant: {tenant}")
    return request

# Security interceptor - block bad input
def block_prompt_injection(request: LLMRequest) -> LLMRequest:
    """Block suspicious prompts."""
    user_message = request.get_latest_user_message().lower()
    
    if "ignore previous instructions" in user_message:
        raise InterceptorError(
            user_message="I can't process this request.",
            code="BLOCKED",
        )
    
    return request

# Response interceptor - runs AFTER the LLM call
def redact_secrets(response: LLMResponse) -> LLMResponse:
    """Remove any leaked secrets."""
    response.text = response.text.replace("sk-secret123", "[REDACTED]")
    return response

# Use interceptors
agent = Agent(
    tools=[...],
    request_interceptors=[block_prompt_injection, add_tenant_context],
    response_interceptors=redact_secrets,
)
```

### Async Interceptors

Interceptors can be async (for database lookups, API calls, etc.):

```python
async def get_user_preferences(request: LLMRequest) -> LLMRequest:
    """Look up user preferences from the database."""
    user_id = request.context.get("user_id")
    if user_id:
        prefs = await database.get_preferences(user_id)
        request.context["preferences"] = prefs
    return request

agent = Agent(
    request_interceptors=get_user_preferences,
)
```

See the [Interceptors Guide](../guides/interceptors.md) for comprehensive documentation.

---

## Session Management

Sessions persist state across conversation turns for multi-step workflows. They support typed storage with Pydantic models and dataclasses:

```python
from pydantic import BaseModel, Field
from dcaf.core import Session
from dcaf.tools import tool

class CartItem(BaseModel):
    name: str
    quantity: int
    price: float

class ShoppingCart(BaseModel):
    items: list[CartItem] = Field(default_factory=list)

@tool(description="Add item to cart")
def add_to_cart(name: str, quantity: int, price: float, session: Session) -> str:
    # Get as typed model (auto-deserializes)
    cart = session.get("cart", as_type=ShoppingCart) or ShoppingCart()
    
    cart.items.append(CartItem(name=name, quantity=quantity, price=price))
    
    # Store typed model (auto-serializes)
    session.set("cart", cart)
    return f"Added {quantity}x {name}. {len(cart.items)} items in cart."

@tool(description="Checkout")
def checkout(session: Session) -> str:
    cart = session.get("cart", as_type=ShoppingCart)
    if not cart:
        return "Cart is empty"
    
    total = sum(item.price * item.quantity for item in cart.items)
    session.delete("cart")
    return f"Checked out ${total:.2f}!"
```

Session data travels with the protocol in `data.session`:

```json
{
  "role": "assistant",
  "content": "Added 2x Widget.",
  "data": {
    "session": {"cart": {"items": [{"name": "Widget", "quantity": 2, "price": 9.99}]}}
  }
}
```

See the [Session Management Guide](../guides/session-management.md) for comprehensive documentation.

---

## Streaming

For real-time token-by-token responses:

```python
from dcaf.core import Agent, ChatMessage, TextDeltaEvent, DoneEvent

agent = Agent(tools=[...])

for event in agent.run_stream(messages=[
    ChatMessage.user("Tell me about Kubernetes")
]):
    if isinstance(event, TextDeltaEvent):
        print(event.text, end="", flush=True)
    elif isinstance(event, DoneEvent):
        print("\n--- Done ---")
```

---

## Running as a Server

Expose your agent as a REST API with one line:

```python
from dcaf.core import Agent, serve

agent = Agent(tools=[...])
serve(agent, port=8000)  # Server at http://0.0.0.0:8000
```

Endpoints:
- `GET /health` - Health check
- `POST /api/chat` - Synchronous chat
- `POST /api/chat-stream` - Streaming (NDJSON)

See [Server Documentation](./server.md) for full details.

---

## A2A (Agent-to-Agent)

DCAF supports the **A2A protocol** for agent-to-agent communication, enabling agents to discover and call each other.

### Server: Expose an Agent

```python
from dcaf.core import Agent, serve

agent = Agent(
    name="k8s-assistant",              # A2A identity
    description="Kubernetes helper",   # A2A description
    tools=[list_pods, delete_pod],
)

# Enable A2A protocol
serve(agent, port=8000, a2a=True)
```

This adds A2A endpoints:
- `GET /.well-known/agent.json` - Agent card (discovery)
- `POST /a2a/tasks/send` - Receive tasks
- `GET /a2a/tasks/{id}` - Task status

### Client: Call Remote Agents

```python
from dcaf.core.a2a import RemoteAgent

# Connect to remote agent
k8s = RemoteAgent(url="http://k8s-agent:8000")

# Send a task
result = k8s.send("List failing pods in production")
print(result.text)
```

### Multi-Agent Orchestration

Remote agents can be used as tools for other agents:

```python
from dcaf.core import Agent
from dcaf.core.a2a import RemoteAgent

# Connect to specialist agents
k8s = RemoteAgent(url="http://k8s-agent:8000")
aws = RemoteAgent(url="http://aws-agent:8000")

# Orchestrator routes to specialists
orchestrator = Agent(
    name="orchestrator",
    tools=[k8s.as_tool(), aws.as_tool()],
    system="Route requests to the appropriate specialist agent"
)

# LLM decides which specialist to call
response = orchestrator.run([
    {"role": "user", "content": "What's the status of my infrastructure?"}
])
```

**Learn more:** See the complete [A2A Guide](./a2a.md) for patterns, examples, and best practices.

---

## Documentation

- [Server](./server.md) - Running agents as REST APIs
- [Domain Layer](./domain.md) - Core concepts: Conversation, ToolCall, Events
- [Application Layer](./application.md) - Services and Ports
- [Adapters](./adapters.md) - LLM framework adapters
- [Testing](./testing.md) - Test utilities and patterns

---

## Architecture

For those interested in the internals:

```
┌──────────────────────────────────────────────────────────────┐
│                         Agent                                 │
│                   (Simple Facade)                             │
├──────────────────────────────────────────────────────────────┤
│                     Application Layer                         │
│              AgentService    ApprovalService                  │
├──────────────────────────────────────────────────────────────┤
│                      Domain Layer                             │
│         Conversation   ToolCall   Message   Events            │
├──────────────────────────────────────────────────────────────┤
│                     Adapters Layer                            │
│              AgnoAdapter    InMemoryRepository                │
└──────────────────────────────────────────────────────────────┘
```

The `Agent` class is a simple facade over the Clean Architecture internals.
Most users only need the `Agent` class and the `@tool` decorator.
