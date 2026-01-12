# Response Conversion Guide

**Converting Core Responses to Schema Messages**

---

## Overview

DCAF provides a bridge between the core's internal `AgentResponse` and the schema's `AgentMessage` (wire format). This allows you to convert internal responses to validated Pydantic models ready for JSON serialization.

---

## Two Conversion Methods

### Method 1: `to_helpdesk_message()` - Returns Dict

**Use when:** You need a plain dictionary for immediate serialization.

```python
from dcaf.core.application.dto import AgentResponse, DataDTO

response = AgentResponse(
    conversation_id="conv-123",
    text="Hello, how can I help?",
    data=DataDTO(),
)

# Convert to dict
message_dict = response.to_helpdesk_message()
# Returns: {"role": "assistant", "content": "Hello...", "data": {...}, "meta_data": {}}
```

**Pros:**
- Simple and direct
- No validation overhead
- Lightweight

**Cons:**
- No type safety
- No validation
- Manual JSON serialization

---

### Method 2: `to_agent_message()` - Returns Pydantic Model ✨ NEW

**Use when:** You want validated, type-safe schema models.

```python
from dcaf.core.application.dto import AgentResponse, DataDTO

response = AgentResponse(
    conversation_id="conv-123",
    text="Hello, how can I help?",
    data=DataDTO(),
)

# Convert to AgentMessage (Pydantic)
agent_message = response.to_agent_message(
    agent_name="my-agent",
    agent_id="agent-001",
)

# Now you have a validated Pydantic model
print(agent_message.role)  # "assistant"
print(agent_message.timestamp)  # datetime object

# Serialize to JSON
json_data = agent_message.model_dump()
```

**Pros:**
- ✅ Type-safe (Pydantic model)
- ✅ Validated (catches errors early)
- ✅ Rich metadata (timestamp, agent info)
- ✅ Can use Pydantic features (JSON schema, serialization options)

**Cons:**
- Slightly more overhead (validation)

---

## Factory Method on Schema

You can also create an `AgentMessage` directly from any response:

```python
from dcaf.schemas.messages import AgentMessage

# Works with any core response
agent_message = AgentMessage.from_agent_response(
    response=core_response,
    agent_name="k8s-agent",
    agent_id="agent-123",
    include_timestamp=True,  # Optional
)
```

---

## Complete Example

```python
from dcaf.core.application.dto import (
    AgentResponse, 
    DataDTO, 
    ToolCallDTO,
    ExecutedToolCall,
)
from dcaf.schemas.messages import AgentMessage

# 1. Create a core response (from AgentService)
tool_call = ToolCallDTO(
    id="tc_789",
    name="delete_pod",
    input={"name": "nginx"},
    tool_description="Delete a Kubernetes pod",
    execute=False,
    requires_approval=True,
)

executed_tc = ExecutedToolCall(
    id="tc_456",
    name="list_pods",
    input={"namespace": "default"},
    output="3 pods found: nginx, redis, api",
)

data = DataDTO(
    tool_calls=[tool_call],
    executed_tool_calls=[executed_tc],
)

response = AgentResponse(
    conversation_id="conv-789",
    text="I found 3 pods. Should I delete nginx?",
    data=data,
    has_pending_approvals=True,
    metadata={"model": "claude-3-sonnet"},
)

# 2. Convert to AgentMessage
agent_message = response.to_agent_message(
    agent_name="k8s-assistant",
    agent_id="agent-001",
)

# 3. Access Pydantic features
print(f"Role: {agent_message.role}")  # "assistant"
print(f"Timestamp: {agent_message.timestamp}")  # datetime
print(f"Agent: {agent_message.agent.name}")  # "k8s-assistant"
print(f"Tool calls: {len(agent_message.data.tool_calls)}")  # 1
print(f"Executed: {len(agent_message.data.executed_tool_calls)}")  # 1

# 4. Serialize to JSON
json_data = agent_message.model_dump()

# 5. Validate round-trip
validated = AgentMessage(**json_data)
assert validated.content == agent_message.content
```

---

## When to Use Which Method

| Scenario | Use | Reason |
|----------|-----|--------|
| **HTTP API responses** | `to_agent_message()` | Pydantic validation, JSON schema |
| **WebSocket streaming** | `to_helpdesk_message()` | Lower overhead |
| **Logging/debugging** | `to_agent_message()` | Rich metadata |
| **Testing** | `to_agent_message()` | Type safety |
| **Simple dict needed** | `to_helpdesk_message()` | Direct and fast |
| **Multi-agent systems** | `to_agent_message()` | Agent identity tracking |

---

## Conversion Path

```
┌─────────────────────────────────────────────────────────────┐
│                    Internal Core Layer                       │
│                                                              │
│  AgentResponse (dto/responses.py)                           │
│  - conversation_id: str                                      │
│  - text: str                                                 │
│  - data: DataDTO                                             │
│  - has_pending_approvals: bool                              │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │ .to_agent_message(agent_name, agent_id)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    Schema Layer (Wire Format)                │
│                                                              │
│  AgentMessage (schemas/messages.py)                         │
│  - role: "assistant"                                        │
│  - content: str                                              │
│  - data: Data (Pydantic)                                     │
│  - timestamp: datetime                                       │
│  - agent: Agent (name, id)                                   │
│  - meta_data: dict                                           │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │ .model_dump()
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    JSON (HelpDesk Protocol)                  │
│                                                              │
│  {                                                           │
│    "role": "assistant",                                     │
│    "content": "...",                                        │
│    "data": {                                                │
│      "tool_calls": [...],                                   │
│      "executed_tool_calls": [...]                           │
│    },                                                        │
│    "timestamp": "2026-01-08T...",                           │
│    "agent": {"name": "k8s-agent", "id": "agent-001"}        │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Benefits of the New Conversion

### Before (dict-based)
```python
# Had to manually build dict
msg = {
    "role": "assistant",
    "content": response.text,
    "data": response.data.to_dict(),
    "meta_data": response.metadata,
    # Missing: timestamp, agent info, validation
}
```

### After (Pydantic-based)
```python
# Rich, validated model
msg = response.to_agent_message(agent_name="my-agent")
# Includes: timestamp, agent info, full validation
json_data = msg.model_dump()  # Type-safe JSON
```

---

## Advanced: Custom Agent Identity

```python
# Track which agent generated the response
agent_message = response.to_agent_message(
    agent_name="k8s-specialist",
    agent_id="agent-k8s-001",
)

# Later, identify the agent
if agent_message.agent:
    print(f"Response from: {agent_message.agent.name}")
    print(f"Agent ID: {agent_message.agent.id}")
```

---

## Testing

```python
def test_response_conversion():
    """Test that conversion preserves data."""
    # Create response
    response = AgentResponse(
        conversation_id="test",
        text="Hello",
        data=DataDTO(),
    )
    
    # Convert
    msg = response.to_agent_message()
    
    # Validate
    assert msg.role == "assistant"
    assert msg.content == "Hello"
    assert msg.timestamp is not None
    
    # Round-trip
    json_data = msg.model_dump()
    msg2 = AgentMessage(**json_data)
    assert msg2.content == msg.content
```

---

## Summary

✅ **Two conversion methods available:**
1. `to_helpdesk_message()` - Returns dict (lightweight)
2. `to_agent_message()` - Returns Pydantic model (rich, validated)

✅ **Factory method on schema:**
- `AgentMessage.from_agent_response()` - Create from any response

✅ **Benefits:**
- Type safety with Pydantic
- Automatic timestamp tracking
- Agent identity tracking
- Full validation
- JSON schema generation

✅ **When to use:**
- Use `to_agent_message()` for HTTP APIs, logging, testing
- Use `to_helpdesk_message()` for simple, fast dict conversion
