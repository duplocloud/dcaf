# Getting Started with DCAF

This guide walks you through building AI agents with DCAF (DuploCloud Agent Framework). You'll learn to create agents, define tools, serve them as APIs, and implement human-in-the-loop approval for dangerous operations.

---

## What is DCAF?

DCAF is a framework for building AI agents that can:

- **Execute tools safely** - Dangerous operations require human approval before execution
- **Persist state** - Session management across conversation turns
- **Switch LLM providers** - Swap between Bedrock, OpenAI, Anthropic without code changes
- **Stream responses** - Real-time token-by-token output

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool

@tool(requires_approval=True, description="Delete a Kubernetes pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")

agent = Agent(tools=[delete_pod])
serve(agent, port=8000)
```

---

## Prerequisites

### Required

- **Python 3.11+** - DCAF supports Python 3.11, 3.12, and 3.13
- **AWS Account** - With access to AWS Bedrock
- **AWS Credentials** - With permissions to invoke Bedrock models

### Optional

- **DuploCloud Account** - For credential management CLI
- **Docker** - For containerized deployments

---

## Installation

### From GitHub

```bash
pip install git+https://github.com/duplocloud/service-desk-agents.git
```

### For Development

```bash
git clone https://github.com/duplocloud/service-desk-agents.git
cd service-desk-agents
pip install -r requirements.txt
```

### Verify Installation

```python
from dcaf.core import Agent, serve
print("DCAF installed successfully!")
```

---

## Environment Setup

### Option 1: AWS Profiles (Recommended)

Use AWS profiles from `~/.aws/credentials`:

```python
from dcaf.core import Agent

agent = Agent(
    aws_profile="my-profile",    # Use this AWS profile
    aws_region="us-east-1",      # Optional region override
)
```

Configure profiles in `~/.aws/credentials`:

```ini
[default]
aws_access_key_id = AKIA...
aws_secret_access_key = ...

[production]
aws_access_key_id = AKIA...
aws_secret_access_key = ...
region = us-west-2
```

### Option 2: Environment Variables

Create a `.env` file:

```bash
# AWS Credentials
AWS_ACCESS_KEY_ID=your_access_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
AWS_SESSION_TOKEN=your_session_token  # Optional
AWS_REGION=us-east-1

# Optional: Bedrock Configuration
BEDROCK_MODEL_ID=us.anthropic.claude-3-5-sonnet-20240620-v1:0

# For other providers
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

### Option 3: DuploCloud (Optional)

```bash
# Update AWS credentials via DuploCloud
dcaf env-update-aws-creds --tenant=your-tenant --host=https://your-duplo-host.duplocloud.net
```

---

## 1. The Agent

The `Agent` class is the core of DCAF. It orchestrates conversations, manages tool execution, and handles the approval workflow.

### Creating an Agent

```python
from dcaf.core import Agent

agent = Agent(
    tools=[...],                         # Tools the agent can use
    system="You are a helpful assistant", # System prompt
    model="anthropic.claude-3-sonnet",   # LLM model (optional)
)
```

### Running the Agent

```python
from dcaf.core import Agent, ChatMessage

agent = Agent(tools=[...])

# Simple - pass messages
response = agent.run(messages=[
    ChatMessage.user("What pods are running?")
])
print(response.text)

# With conversation history
response = agent.run(messages=[
    ChatMessage.user("What pods are running?"),
    ChatMessage.assistant("There are 3 pods: nginx, redis, api"),
    ChatMessage.user("Tell me more about nginx"),  # ← Current message
])
```

### Using Plain Dicts (JSON Compatible)

You can pass plain dictionaries, useful when receiving messages from JSON APIs:

```python
# From JSON/API request
response = agent.run(messages=[
    {"role": "user", "content": "What pods are running?"},
    {"role": "assistant", "content": "There are 3 pods..."},
    {"role": "user", "content": "Tell me more"},
])
```

### Choosing a Provider

DCAF supports multiple LLM providers:

| Provider | Description | Model Examples |
|----------|-------------|----------------|
| `bedrock` | AWS Bedrock (default) | `anthropic.claude-3-sonnet-20240229-v1:0` |
| `anthropic` | Direct Anthropic API | `claude-3-sonnet-20240229` |
| `openai` | OpenAI API | `gpt-4`, `gpt-4-turbo`, `gpt-3.5-turbo` |
| `azure` | Azure OpenAI | Deployment names |
| `google` | Google AI | `gemini-pro` |
| `ollama` | Local Ollama | `llama2`, `mistral`, `codellama` |

```python
# AWS Bedrock (default)
agent = Agent(provider="bedrock", model="anthropic.claude-3-sonnet-20240229-v1:0")

# OpenAI
agent = Agent(provider="openai", model="gpt-4", api_key="sk-...")

# Local Ollama (free, runs locally)
agent = Agent(provider="ollama", model="llama2")
```

### Custom Agent Functions

For complex logic beyond simple tool calling, define a custom function:

```python
from dcaf.core import Agent, AgentResult, serve

def my_custom_agent(messages: list, context: dict) -> AgentResult:
    """Custom agent with multi-step logic."""
    # Step 1: Classify intent
    classifier = Agent(system="Classify the user's intent")
    intent = classifier.run(messages).text
    
    # Step 2: Route to appropriate handler
    if "kubernetes" in intent.lower():
        k8s_agent = Agent(tools=[list_pods, delete_pod])
        response = k8s_agent.run(messages)
    else:
        general_agent = Agent(system="You are a helpful assistant")
        response = general_agent.run(messages)
    
    return AgentResult(text=response.text)

# Serve the custom function
serve(my_custom_agent, port=8000)
```

---

## 2. Tools

Tools are capabilities your agent can use. DCAF provides three ways to define tool schemas.

### Option 1: Auto-Generate (Simplest)

Let DCAF generate the schema from your function signature:

```python
from dcaf.tools import tool

@tool(description="Get current weather for a city")
def get_weather(city: str, units: str = "celsius") -> str:
    """Fetch weather data."""
    return weather_api.get(city, units)
```

DCAF automatically creates a JSON schema from the type hints:

```json
{
  "type": "object",
  "properties": {
    "city": {"type": "string"},
    "units": {"type": "string", "default": "celsius"}
  },
  "required": ["city"]
}
```

### Option 2: Dict Schema (Full Control)

Define the exact JSON schema yourself:

```python
@tool(
    description="Get current weather for a city",
    schema={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name (e.g., 'London', 'New York')"
            },
            "units": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "description": "Temperature units"
            }
        },
        "required": ["city"]
    }
)
def get_weather(city: str, units: str = "celsius") -> str:
    return weather_api.get(city, units)
```

### Option 3: Pydantic Model (Type-Safe)

Use Pydantic for IDE autocomplete, validation, and reusable schemas:

```python
from pydantic import BaseModel, Field
from typing import Literal

class WeatherInput(BaseModel):
    """Schema for weather requests."""
    city: str = Field(..., description="City name")
    units: Literal["celsius", "fahrenheit"] = Field(
        default="celsius",
        description="Temperature units"
    )

@tool(description="Get current weather", schema=WeatherInput)
def get_weather(city: str, units: str = "celsius") -> str:
    return weather_api.get(city, units)
```

**Just pass the Pydantic class** - DCAF automatically converts it to JSON schema.

### Tool Options

| Option | Default | Description |
|--------|---------|-------------|
| `description` | Docstring | What the tool does (shown to LLM) |
| `requires_approval` | `False` | Whether to require human approval |
| `schema` | Auto-generated | Dict schema OR Pydantic model class |

### Complete Tools Example

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool
from pydantic import BaseModel, Field

# Auto-generated schema (safe operation)
@tool(description="List Kubernetes pods")
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

# Pydantic schema (dangerous operation)
class DeletePodInput(BaseModel):
    name: str = Field(..., description="Pod name to delete")
    namespace: str = Field(default="default")
    force: bool = Field(default=False, description="Force immediate deletion")

@tool(
    description="Delete a Kubernetes pod",
    requires_approval=True,
    schema=DeletePodInput
)
def delete_pod(name: str, namespace: str = "default", force: bool = False) -> str:
    cmd = f"kubectl delete pod {name} -n {namespace}"
    if force:
        cmd += " --force --grace-period=0"
    return kubectl(cmd)

# Create and serve the agent
agent = Agent(
    tools=[list_pods, delete_pod],
    system="You are a Kubernetes assistant."
)
serve(agent, port=8000)
```

---

## 3. Serving Your Agent

Expose your agent as a REST API with one line:

```python
from dcaf.core import Agent, serve

agent = Agent(tools=[...])
serve(agent, port=8000)
```

### Available Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/chat` | POST | Synchronous chat |
| `/api/chat-stream` | POST | Streaming (NDJSON) |

### Testing Your Agent

**With curl:**

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "List all pods"}]}'
```

**With Python:**

```python
import requests

response = requests.post(
    "http://localhost:8000/api/chat",
    json={"messages": [{"role": "user", "content": "List all pods"}]}
)
print(response.json())
```

### Streaming Responses

For real-time token-by-token output:

```bash
curl -X POST http://localhost:8000/api/chat-stream \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Explain Kubernetes"}]}'
```

Response (NDJSON):

```json
{"type": "text_delta", "text": "Kubernetes"}
{"type": "text_delta", "text": " is"}
{"type": "text_delta", "text": " a container orchestration platform..."}
{"type": "done"}
```

### Adding Custom Routes

```python
from fastapi import APIRouter

custom_router = APIRouter()

@custom_router.get("/custom/status")
def get_status():
    return {"status": "operational"}

serve(agent, port=8000, additional_routers=[custom_router])
```

---

## 4. Human-in-the-Loop Approval

A core feature of DCAF is requiring human approval for dangerous operations before execution.

### Why Approval Matters

Autonomous agents executing infrastructure operations is risky:

- **Destructive actions**: `kubectl delete pod` or `aws ec2 terminate-instances`
- **Irreversible changes**: Data deletion, resource destruction
- **Compliance**: Some environments require human sign-off
- **Cost**: Expensive operations should be reviewed

### Marking Tools for Approval

```python
@tool(requires_approval=True, description="Delete a pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")
```

### The Approval Flow

```
User: "Delete the failing pod"
           │
           ▼
    ┌──────────────┐
    │  Agent calls │
    │  delete_pod  │
    └──────────────┘
           │
           ▼
    ┌──────────────────────────┐
    │  requires_approval=True  │
    │  → Pause execution       │
    └──────────────────────────┘
           │
           ▼
    ┌──────────────────────────┐
    │  Return pending tool     │
    │  call to user            │
    └──────────────────────────┘
           │
           ▼
    ┌──────────────────────────┐
    │  User reviews:           │
    │  [Approve] or [Reject]   │
    └──────────────────────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
  Approved    Rejected
     │           │
     ▼           ▼
  Execute    Skip tool,
  the tool   continue
```

### Response Format: Pending Approval

When a tool requires approval, the response includes the pending tool call:

```json
{
  "role": "assistant",
  "content": "I'll delete the pod. This requires your approval.",
  "data": {
    "tool_calls": [
      {
        "id": "tc_abc123",
        "name": "delete_pod",
        "input": {"name": "my-pod", "namespace": "default"},
        "execute": false
      }
    ]
  }
}
```

### Approving a Tool Call

Send back the tool call with `execute: true`:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "",
      "data": {
        "tool_calls": [
          {
            "id": "tc_abc123",
            "name": "delete_pod",
            "input": {"name": "my-pod", "namespace": "default"},
            "execute": true
          }
        ]
      }
    }
  ]
}
```

### Rejecting a Tool Call

To reject, simply don't include it or set `execute: false`:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "No, don't delete that pod."
    }
  ]
}
```

### Programmatic Handling

When using the Agent directly (not via HTTP):

```python
response = agent.run(messages)

if response.needs_approval:
    print("Tools pending approval:")
    for tool in response.pending_tools:
        print(f"  - {tool.name}: {tool.input}")
    
    # Option 1: Approve all
    response = response.approve_all()
    
    # Option 2: Reject all
    response = response.reject_all("User declined")
    
    # Option 3: Handle individually
    for tool in response.pending_tools:
        if should_approve(tool):
            tool.approve()
        else:
            tool.reject("Not allowed")
    response = agent.resume(response.conversation_id)

print(response.text)
```

### Approval Rules

**Simple rule**: If EITHER the tool OR the policy says it's risky, require approval.

| Tool `requires_approval` | In `high_risk_tools` | Result |
|--------------------------|----------------------|--------|
| `True` | (any) | Requires approval |
| `False` | No | Auto-executes |
| `False` | Yes | Requires approval |

```python
agent = Agent(
    tools=[list_pods, delete_pod, restart_service],
    high_risk_tools=["restart_service"],  # Additional approval requirement
)
```

---

## 5. Session Management

Sessions allow you to persist state across conversation turns - perfect for multi-step workflows.

### What is a Session?

A Session is a key-value store that:

- **Persists across turns** - Data survives between user messages
- **Travels with the protocol** - Automatically serialized in responses
- **Supports typed models** - Store Pydantic models and dataclasses with auto-serialization
- **Provides simple API** - Dict-like access with type hints

### Using Session in Tools

```python
from dcaf.core import Session
from dcaf.tools import tool

@tool(description="Add item to shopping cart")
def add_to_cart(item: str, quantity: int, session: Session) -> str:
    """Session is automatically injected by DCAF."""
    cart = session.get("cart", [])
    cart.append({"item": item, "quantity": quantity})
    session.set("cart", cart)
    return f"Added {quantity}x {item}. Cart now has {len(cart)} items."

@tool(description="View shopping cart")
def view_cart(session: Session) -> str:
    cart = session.get("cart", [])
    if not cart:
        return "Cart is empty"
    return "\n".join(f"- {i['quantity']}x {i['item']}" for i in cart)

@tool(description="Checkout")
def checkout(session: Session) -> str:
    cart = session.get("cart", [])
    total_items = sum(i["quantity"] for i in cart)
    session.delete("cart")  # Clear after checkout
    return f"Checked out {total_items} items!"
```

### Typed Session Storage

Store Pydantic models or dataclasses with automatic serialization/deserialization:

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
    discount_code: str | None = None

@tool(description="Add item to cart")
def add_to_cart(name: str, quantity: int, price: float, session: Session) -> str:
    # Get as typed model (auto-deserializes from stored JSON)
    cart = session.get("cart", as_type=ShoppingCart) or ShoppingCart()
    
    # Work with the typed model
    cart.items.append(CartItem(name=name, quantity=quantity, price=price))
    
    # Store it back (auto-serializes to JSON)
    session.set("cart", cart)
    
    total = sum(item.price * item.quantity for item in cart.items)
    return f"Added {quantity}x {name}. Cart total: ${total:.2f}"

@tool(description="Apply discount code")
def apply_discount(code: str, session: Session) -> str:
    cart = session.get("cart", as_type=ShoppingCart)
    if not cart:
        return "Cart is empty"
    
    cart.discount_code = code
    session.set("cart", cart)
    return f"Applied discount code: {code}"
```

**Dataclasses work too:**

```python
from dataclasses import dataclass

@dataclass
class UserPrefs:
    theme: str = "light"
    language: str = "en"
    notifications: bool = True

# Store dataclass (auto-serializes)
session.set("prefs", UserPrefs(theme="dark"))

# Retrieve as typed (auto-deserializes)
prefs = session.get("prefs", as_type=UserPrefs)
print(prefs.theme)  # "dark"
```

### Session API

```python
from dcaf.core import Session

session = Session()

# Basic operations
session.set("user_id", "12345")
user_id = session.get("user_id")
session.delete("user_id")

# With defaults
count = session.get("count", 0)  # Returns 0 if not set

# Typed retrieval
cart = session.get("cart", as_type=ShoppingCart)  # Returns ShoppingCart or None
cart = session.get("cart", ShoppingCart(), as_type=ShoppingCart)  # With default

# Check existence
if session.has("user_id"):
    ...

# Dict-like access
session["key"] = "value"
value = session["key"]

# Iteration
for key in session.keys():
    print(key, session[key])

# Bulk operations
session.update({"a": 1, "b": 2})
session.clear()
```

### Session in the Protocol

Session data is included in the `data.session` field of messages:

**Response with session:**

```json
{
  "role": "assistant",
  "content": "Added 2x Widget to cart.",
  "data": {
    "session": {
      "cart": [{"item": "Widget", "quantity": 2}],
      "user_preference": "dark_mode"
    }
  }
}
```

**Subsequent request (session travels back):**

```json
{
  "messages": [
    {
      "role": "user",
      "content": "What's in my cart?",
      "data": {
        "session": {
          "cart": [{"item": "Widget", "quantity": 2}],
          "user_preference": "dark_mode"
        }
      }
    }
  ]
}
```

### Multi-Turn Workflow Example

```
Turn 1:
  User: "Add 2 widgets to cart"
  Agent: "Added 2x Widget" 
  Session: {"cart": [{"item": "Widget", "qty": 2}]}

Turn 2:
  User: "Add 3 gadgets"
  Agent: "Added 3x Gadget. Cart has 2 items."
  Session: {"cart": [..., {"item": "Gadget", "qty": 3}]}

Turn 3:
  User: "Checkout"
  Agent: "Checked out 5 items!"
  Session: {}  ← Cart cleared
```

---

## 6. Advanced Topics

### Interceptors

Interceptors let you hook into the request/response pipeline:

```python
from dcaf.core import Agent, LLMRequest, LLMResponse, InterceptorError

def add_context(request: LLMRequest) -> LLMRequest:
    """Add tenant info before sending to LLM."""
    tenant = request.context.get("tenant_name", "unknown")
    request.add_system_context(f"User's tenant: {tenant}")
    return request

def redact_secrets(response: LLMResponse) -> LLMResponse:
    """Remove leaked secrets from response."""
    response.text = response.text.replace("sk-secret", "[REDACTED]")
    return response

agent = Agent(
    tools=[...],
    request_interceptors=[add_context],
    response_interceptors=[redact_secrets],
)
```

See the [Interceptors Guide](./guides/interceptors.md) for more details.

### Event Handling

Subscribe to events for logging, notifications, or audit trails:

```python
def log_events(event):
    print(f"[{event.event_type}] at {event.timestamp}")

def notify_slack(event):
    if event.event_type == "ApprovalRequested":
        slack.post("Approval needed!")

agent = Agent(tools=[...], on_event=[log_events, notify_slack])
```

**Event Types:**

- `ConversationStarted` - New conversation began
- `ApprovalRequested` - Tools need approval
- `ToolCallApproved` - User approved a tool
- `ToolCallRejected` - User rejected a tool
- `ToolExecuted` - Tool ran successfully
- `ToolExecutionFailed` - Tool execution failed

---

## Troubleshooting

### AWS Credentials Expired

```
ExpiredTokenException: The security token included in the request is expired
```

**Solution:**

```bash
# Using DuploCloud
dcaf env-update-aws-creds --tenant=your-tenant --host=your-duplo-host

# Or manually update .env with fresh credentials
```

### Model Not Found

```
ResourceNotFoundException: Could not find model with id...
```

**Solution:**

- Verify the model ID is correct
- Check Bedrock is enabled in your AWS account
- Ensure your region has access to the model

### Expected toolResult Blocks

```
ValidationException: Expected toolResult blocks...
```

**Solution:**

This occurs when Bedrock receives tool-related messages in an invalid state. DCAF automatically handles this by:

1. Filtering tool messages from conversation history
2. Limiting parallel tool calls to 1
3. Adding a system prompt instruction for single tool calls

### Message Alternation Error

```
ValidationException: Messages must alternate between user and assistant
```

**Solution:**

DCAF automatically enforces message alternation. If you see this:

1. Check for manual message manipulation
2. Ensure you're not passing raw Bedrock-style messages

### Connection Timeout

```
ReadTimeoutError: Read timed out
```

**Solution:**

```bash
export BOTO3_READ_TIMEOUT=60
export BOTO3_CONNECT_TIMEOUT=30
```

### Import Errors

```
ModuleNotFoundError: No module named 'dcaf'
```

**Solution:**

```bash
pip install git+https://github.com/duplocloud/service-desk-agents.git
```

### Provider Package Missing

```
ImportError: OpenAI provider requires the 'openai' package...
```

**Solution:**

```bash
# For OpenAI/Azure
pip install openai

# For Google AI
pip install google-generativeai

# For Ollama
pip install ollama
```

---

## Next Steps

- **[Core Overview](./core/index.md)** - Full Agent API documentation
- **[Building Tools](./guides/building-tools.md)** - Advanced tool creation
- **[Custom Agents](./guides/custom-agents.md)** - Complex multi-step agents
- **[Server](./core/server.md)** - Deployment and configuration
- **[Interceptors](./guides/interceptors.md)** - Request/response hooks
- **[Examples](./examples/examples.md)** - More code examples

---

## Getting Help

- Check [GitHub Issues](https://github.com/duplocloud/service-desk-agents/issues)
- Enable debug logging: `export LOG_LEVEL=DEBUG`
- Contact DuploCloud: support@duplocloud.com
