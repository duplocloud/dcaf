# Session Management

Sessions allow you to persist state across conversation turns, enabling multi-step workflows where tools can share data.

---

## Overview

A Session is a key-value store that:

- **Persists across turns** - Data survives between user messages
- **Travels with the protocol** - Automatically serialized in responses
- **Supports typed models** - Store Pydantic models and dataclasses with auto-serialization
- **Provides simple API** - Dict-like access with type hints
- **Available everywhere** - In tools, interceptors, custom agent functions, and `agent.run()`

---

## Basic Usage

### Creating and Using Sessions

```python
from dcaf.core import Session

session = Session()

# Set values
session.set("user_id", "12345")
session.set("preferences", {"theme": "dark", "language": "en"})

# Get values
user_id = session.get("user_id")  # "12345"
prefs = session.get("preferences")  # {"theme": "dark", ...}

# Get with default
count = session.get("count", 0)  # Returns 0 if not set

# Check existence
if session.has("user_id"):
    print("User is logged in")

# Delete values
session.delete("user_id")
```

### Dict-Like Access

Session supports familiar dictionary-style access:

```python
# Set/get with brackets
session["key"] = "value"
value = session["key"]

# Iteration
for key in session.keys():
    print(f"{key}: {session[key]}")

# Get all items
for key, value in session.items():
    print(f"{key}: {value}")
```

### Bulk Operations

```python
# Update multiple values at once
session.update({
    "cart": [],
    "user_id": "12345",
    "step": 1,
})

# Clear all data
session.clear()

# Convert to dict
data = session.to_dict()
```

---

## Typed Storage

Session supports automatic serialization and deserialization of Pydantic models and dataclasses. This gives you type safety, IDE autocomplete, and cleaner code.

### Pydantic Models

```python
from pydantic import BaseModel, Field
from dcaf.core import Session

class UserPreferences(BaseModel):
    theme: str = "light"
    language: str = "en"
    notifications: bool = True

session = Session()

# Store a Pydantic model (auto-serializes to dict)
prefs = UserPreferences(theme="dark", notifications=False)
session.set("prefs", prefs)

# What's actually stored:
# {"theme": "dark", "language": "en", "notifications": False}

# Retrieve as typed model (auto-deserializes)
loaded_prefs = session.get("prefs", as_type=UserPreferences)
print(loaded_prefs.theme)  # "dark"
print(type(loaded_prefs))  # <class 'UserPreferences'>

# Retrieve without type (returns raw dict)
raw = session.get("prefs")
print(raw)  # {"theme": "dark", "language": "en", "notifications": False}
```

### Dataclasses

```python
from dataclasses import dataclass
from dcaf.core import Session

@dataclass
class Config:
    debug: bool = False
    max_retries: int = 3
    timeout: float = 30.0

session = Session()

# Store a dataclass (auto-serializes via asdict())
session.set("config", Config(debug=True, max_retries=5))

# Retrieve as typed
config = session.get("config", as_type=Config)
print(config.debug)  # True
print(config.max_retries)  # 5
```

### Nested Models

Complex nested structures work seamlessly:

```python
from pydantic import BaseModel, Field
from typing import Optional

class CartItem(BaseModel):
    name: str
    quantity: int
    price: float

class ShoppingCart(BaseModel):
    items: list[CartItem] = Field(default_factory=list)
    discount_code: Optional[str] = None
    
    @property
    def total(self) -> float:
        return sum(item.price * item.quantity for item in self.items)

# Store complex model
cart = ShoppingCart()
cart.items.append(CartItem(name="Widget", quantity=2, price=9.99))
cart.items.append(CartItem(name="Gadget", quantity=1, price=24.99))
session.set("cart", cart)

# Retrieve with full type hierarchy intact
loaded_cart = session.get("cart", as_type=ShoppingCart)
print(loaded_cart.total)  # 44.97
print(loaded_cart.items[0].name)  # "Widget"
```

### Default Values with Types

```python
# Returns None if key doesn't exist
cart = session.get("cart", as_type=ShoppingCart)  # None if not found

# Provide a default instance
cart = session.get("cart", ShoppingCart(), as_type=ShoppingCart)  # Never None
```

---

## Using Session in Tools

Tools can declare a `Session` parameter that DCAF automatically injects. The parameter name must be exactly `session` with type `Session`.

### Basic Example

```python
from dcaf.core import Session
from dcaf.tools import tool

@tool(description="Remember a value")
def remember(key: str, value: str, session: Session) -> str:
    """Store a value in session."""
    session.set(key, value)
    return f"Remembered {key}={value}"

@tool(description="Recall a value")
def recall(key: str, session: Session) -> str:
    """Retrieve a value from session."""
    value = session.get(key)
    if value is None:
        return f"I don't remember '{key}'"
    return f"{key} is '{value}'"
```

### Shopping Cart Example

```python
from dcaf.core import Session
from dcaf.tools import tool

@tool(description="Add item to shopping cart")
def add_to_cart(item: str, quantity: int, session: Session) -> str:
    """Add an item to the user's cart."""
    cart = session.get("cart", [])
    cart.append({"item": item, "quantity": quantity})
    session.set("cart", cart)
    
    total_items = sum(i["quantity"] for i in cart)
    return f"Added {quantity}x {item}. Cart now has {total_items} items."

@tool(description="View shopping cart contents")
def view_cart(session: Session) -> str:
    """Show what's in the cart."""
    cart = session.get("cart", [])
    
    if not cart:
        return "Your cart is empty."
    
    lines = ["Your cart contains:"]
    for item in cart:
        lines.append(f"  - {item['quantity']}x {item['item']}")
    
    total = sum(i["quantity"] for i in cart)
    lines.append(f"Total: {total} items")
    return "\n".join(lines)

@tool(description="Clear the shopping cart")
def clear_cart(session: Session) -> str:
    """Remove all items from the cart."""
    session.delete("cart")
    return "Cart cleared."

@tool(description="Checkout and complete purchase")
def checkout(session: Session) -> str:
    """Complete the purchase."""
    cart = session.get("cart", [])
    
    if not cart:
        return "Cannot checkout - cart is empty."
    
    total_items = sum(i["quantity"] for i in cart)
    session.delete("cart")  # Clear after checkout
    
    return f"✅ Order placed! {total_items} items will be shipped."
```

### Multi-Step Workflow Example

```python
from dcaf.core import Session
from dcaf.tools import tool
from typing import Literal

@tool(description="Start a deployment workflow")
def start_deployment(
    environment: Literal["staging", "production"],
    session: Session
) -> str:
    """Initialize a deployment workflow."""
    session.set("deployment", {
        "environment": environment,
        "step": "started",
        "services": [],
    })
    return f"Deployment workflow started for {environment}. Add services to deploy."

@tool(description="Add a service to the deployment")
def add_service(service_name: str, version: str, session: Session) -> str:
    """Add a service to the pending deployment."""
    deployment = session.get("deployment")
    
    if not deployment:
        return "No deployment in progress. Run start_deployment first."
    
    deployment["services"].append({
        "name": service_name,
        "version": version,
    })
    deployment["step"] = "services_added"
    session.set("deployment", deployment)
    
    return f"Added {service_name}:{version} to deployment. {len(deployment['services'])} services total."

@tool(requires_approval=True, description="Execute the deployment")
def execute_deployment(session: Session) -> str:
    """Execute the pending deployment (requires approval)."""
    deployment = session.get("deployment")
    
    if not deployment:
        return "No deployment in progress."
    
    if not deployment.get("services"):
        return "No services to deploy. Add services first."
    
    env = deployment["environment"]
    services = deployment["services"]
    
    # Simulate deployment
    results = []
    for svc in services:
        results.append(f"✅ Deployed {svc['name']}:{svc['version']} to {env}")
    
    # Clear deployment state
    session.delete("deployment")
    
    return "\n".join(results)
```

---

## Using Session with Agent.run()

You can pass session data directly to `agent.run()` and `agent.chat()`:

```python
from dcaf.core import Agent, Session

agent = Agent(tools=[...])

# Pass session as a dict
response = agent.run(
    messages=[{"role": "user", "content": "Continue the wizard"}],
    session={"wizard_step": 2, "user_name": "Alice"},
)

# Access updated session from response
print(response.session)  # {"wizard_step": 3, "user_name": "Alice", ...}

# Pass session to next request
next_response = agent.run(
    messages=[{"role": "user", "content": "Next step"}],
    session=response.session,
)
```

You can also pass a `Session` instance:

```python
from dcaf.core import Agent, Session

session = Session()
session.set("user_id", "12345")

response = agent.run(messages=[...], session=session)

# Session changes are in response
print(response.session)
```

---

## Using Session in Custom Agent Functions

Custom agent functions receive session as an optional third parameter:

```python
from dcaf.core import serve, Session
from dcaf.core.primitives import AgentResult

def my_agent(messages: list, context: dict, session: Session) -> AgentResult:
    """Custom agent with session access."""
    # Read from session
    call_count = session.get("call_count", 0)
    
    # Modify session
    session.set("call_count", call_count + 1)
    session.set("last_message", messages[-1]["content"])
    
    # Return result with session data
    return AgentResult(
        text=f"This is call #{call_count + 1}",
        session=session.to_dict(),  # Include updated session in response
    )

serve(my_agent)
```

**Backward Compatibility**: Functions without a session parameter still work:

```python
# Old style (still supported)
def my_agent(messages: list, context: dict) -> AgentResult:
    return AgentResult(text="Hello!")

# New style with session
def my_agent(messages: list, context: dict, session: Session) -> AgentResult:
    return AgentResult(text="Hello!", session=session.to_dict())
```

---

## Using Session in Interceptors

Request and response interceptors have access to session:

### Request Interceptor

```python
from dcaf.core import Agent, LLMRequest

def add_user_context(request: LLMRequest) -> LLMRequest:
    """Add user-specific context from session."""
    # Access session data
    user_prefs = request.session.get("user_preferences", {})
    user_name = request.session.get("user_name", "User")
    
    # Add context to system prompt
    request.add_system_context(f"User: {user_name}")
    if user_prefs.get("verbose"):
        request.add_system_context("User prefers detailed explanations.")
    
    # Track request count
    count = request.session.get("request_count", 0)
    request.session.set("request_count", count + 1)
    
    return request

agent = Agent(
    tools=[...],
    request_interceptors=add_user_context,
)
```

### Response Interceptor

```python
from dcaf.core import Agent, LLMResponse

def track_response_metrics(response: LLMResponse) -> LLMResponse:
    """Track response metrics in session."""
    # Update session with response info
    response.session.set("last_response_length", len(response.text))
    response.session.set("had_tool_calls", response.has_tool_calls())
    
    # Accumulate total tokens if available
    if response.usage:
        total = response.session.get("total_tokens", 0)
        total += response.usage.get("output_tokens", 0)
        response.session.set("total_tokens", total)
    
    return response

agent = Agent(
    tools=[...],
    response_interceptors=track_response_metrics,
)
```

---

## Protocol Integration

Session data is automatically included in the HelpDesk protocol's `data.session` field.

### Response Format

When your agent responds, session data is included:

```json
{
  "role": "assistant",
  "content": "Added 2x Widget to cart.",
  "data": {
    "session": {
      "cart": [
        {"item": "Widget", "quantity": 2}
      ],
      "user_preference": "dark_mode"
    },
    "tool_calls": [],
    "executed_tool_calls": [...]
  }
}
```

### Request Format

The HelpDesk sends session data back on subsequent requests:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Add another widget",
      "data": {
        "session": {
          "cart": [
            {"item": "Widget", "quantity": 2}
          ],
          "user_preference": "dark_mode"
        }
      }
    }
  ]
}
```

### Session Lifecycle

```
Turn 1:
  User: "Add 2 widgets to cart"
  Tool: add_to_cart("Widget", 2, session)
  Session After: {"cart": [{"item": "Widget", "quantity": 2}]}
  Response: "Added 2x Widget. Cart has 2 items."

Turn 2:
  Session Before: {"cart": [{"item": "Widget", "quantity": 2}]}
  User: "Add 3 gadgets"
  Tool: add_to_cart("Gadget", 3, session)
  Session After: {"cart": [..., {"item": "Gadget", "quantity": 3}]}
  Response: "Added 3x Gadget. Cart has 5 items."

Turn 3:
  Session Before: {"cart": [{...}, {...}]}
  User: "Checkout"
  Tool: checkout(session)
  Session After: {}  ← Cleared
  Response: "Order placed! 5 items shipped."

Turn 4:
  Session Before: {}
  User: "What's in my cart?"
  Tool: view_cart(session)
  Response: "Your cart is empty."
```

---

## Session API Reference

### `Session` Class

```python
from dcaf.core import Session
```

#### Methods

| Method | Description |
|--------|-------------|
| `get(key, default=None, *, as_type=None)` | Get a value, optionally deserializing to `as_type` |
| `set(key, value)` | Set a value (auto-serializes Pydantic/dataclass) |
| `delete(key)` | Delete a value |
| `has(key)` | Check if key exists |
| `keys()` | Get all keys |
| `items()` | Get all key-value pairs (raw data) |
| `update(dict)` | Update multiple values (auto-serializes) |
| `clear()` | Remove all values |
| `to_dict()` | Convert to plain dict |

#### The `as_type` Parameter

The `get()` method's `as_type` parameter enables typed retrieval:

```python
from pydantic import BaseModel

class UserPrefs(BaseModel):
    theme: str = "light"

# Store a model
session.set("prefs", UserPrefs(theme="dark"))

# Retrieve as typed model
prefs = session.get("prefs", as_type=UserPrefs)  # UserPrefs instance
print(prefs.theme)  # "dark"

# Retrieve without type (raw dict)
raw = session.get("prefs")  # {"theme": "dark"}

# With default value
prefs = session.get("prefs", UserPrefs(), as_type=UserPrefs)  # Never None
```

**Supported Types:**
- Pydantic models (v2) - via `model_validate()`
- Dataclasses - via constructor
- Primitives - returned as-is

#### Class Methods

| Method | Description |
|--------|-------------|
| `Session.from_dict(data)` | Create session from dict |

#### Properties

| Property | Description |
|----------|-------------|
| `is_modified` | True if session was changed since creation |
| `is_empty` | True if session has no data |

---

## Best Practices

### 1. Use Meaningful Keys

```python
# Good - clear, namespaced
session.set("deployment_state", {...})
session.set("user_preferences", {...})

# Bad - ambiguous
session.set("state", {...})
session.set("data", {...})
```

### 2. Clean Up When Done

```python
@tool(description="Complete the workflow")
def finish_workflow(session: Session) -> str:
    # Process the workflow...
    result = process(session.get("workflow_data"))
    
    # Clean up session state
    session.delete("workflow_data")
    session.delete("workflow_step")
    
    return result
```

### 3. Use Defaults for Safety

```python
# Always provide defaults for optional data
cart = session.get("cart", [])  # Empty list if not set
count = session.get("attempt_count", 0)  # Zero if not set

# With typed models, provide a default instance
prefs = session.get("prefs", UserPrefs(), as_type=UserPrefs)
```

### 4. Use Typed Models for Complex Data

```python
# Good - typed model with validation
class DeploymentState(BaseModel):
    environment: str
    services: list[str] = []
    step: int = 0

state = session.get("deployment", as_type=DeploymentState)
if state:
    # IDE autocomplete, type checking, validation
    print(state.environment)
    print(state.step)

# Less ideal - raw dicts require manual key access
state = session.get("deployment")
if state:
    # No autocomplete, prone to typos
    print(state.get("enviroment"))  # Typo goes unnoticed!
```

### 4. Keep Session Data Serializable

Session data must be JSON-serializable:

```python
# Good - JSON-serializable types
session.set("items", ["a", "b", "c"])
session.set("config", {"key": "value"})
session.set("count", 42)

# Bad - non-serializable types
session.set("connection", db_connection)  # Will fail
session.set("callback", lambda x: x)  # Will fail
```

### 5. Don't Store Sensitive Data

Session data is included in protocol messages. Avoid storing:

- Passwords or tokens
- API keys
- Personal identifiable information (PII)

```python
# Bad - sensitive data in session
session.set("api_key", "sk-secret-key")

# Good - store only references
session.set("user_id", "12345")  # Look up details server-side
```

---

## Related Documentation

- [Getting Started](../getting-started.md#5-session-management) - Session quick start
- [HelpDesk Protocol](../core/helpdesk-protocol.md) - Protocol format details
- [Building Tools](./building-tools.md) - Complete tool guide

