# Domain Layer

The domain layer contains the core business logic for DCAF. It's pure Python with no external dependencies.

---

## Overview

| Component | What it is | When you use it |
|-----------|------------|-----------------|
| **Conversation** | Container for messages and tool calls | Automatically managed by Agent |
| **Message** | A single message (user, assistant, system) | Rarely used directly |
| **ToolCall** | A request to execute a tool | Returned when approval is needed |
| **ApprovalPolicy** | Rules for what needs approval | Advanced: custom approval rules |
| **Domain Events** | Records of what happened | Advanced: audit trails, notifications |

---

## Conversation

The `Conversation` is the central container that holds:
- The ordered list of messages
- Pending tool calls awaiting approval
- Domain events that occurred

### Key Rule

> **You cannot add a new user message while tool calls are pending approval.**

This prevents the conversation from continuing before the user deals with pending actions.

### Simple Usage

```python
from dcaf.core import Conversation

# Create a new conversation
conversation = Conversation.create()

# Add messages (accepts strings directly)
conversation.add_user_message("Hello!")
conversation.add_assistant_message("Hi there!")
conversation.add_system_message("You are a helpful assistant.")

# Check state
print(f"Messages: {conversation.message_count}")
print(f"Blocked: {conversation.is_blocked}")
```

### With System Prompt

```python
conversation = Conversation.with_system_prompt(
    "You are a Kubernetes assistant. Be concise."
)
```

### Handling Approvals

```python
# When blocked by pending approvals
if conversation.has_pending_approvals:
    for tc in conversation.pending_tool_calls:
        print(f"Pending: {tc.tool_name}")
    
    # Approve or reject
    conversation.approve_tool_call("tc-123")
    # or
    conversation.reject_tool_call("tc-123", "Too risky")
```

---

## ToolCall

A `ToolCall` represents a request to execute a tool. It has a **state machine** that tracks its lifecycle.

### States

```
PENDING → APPROVED → EXECUTING → COMPLETED
    │                     │
    └→ REJECTED           └→ FAILED
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `id` | str | Unique identifier |
| `tool_name` | str | Name of the tool |
| `input` | dict | Parameters for the tool |
| `status` | enum | Current state |
| `requires_approval` | bool | Whether approval was needed |
| `result` | str | Output (if completed) |
| `rejection_reason` | str | Why rejected (if rejected) |
| `error` | str | Error message (if failed) |

### Status Checks

```python
tool_call.is_pending     # Waiting for approval
tool_call.is_approved    # Approved, ready to execute
tool_call.is_rejected    # User rejected it
tool_call.is_completed   # Successfully executed
tool_call.is_failed      # Execution failed
tool_call.is_terminal    # In a final state (completed/rejected/failed)
```

---

## Message

Messages are simple - they have a role and content.

### Roles

- `USER` - Messages from the human
- `ASSISTANT` - Messages from the LLM
- `SYSTEM` - System prompts/instructions

### Creating Messages

```python
from dcaf.core import Message

# Factory methods (for advanced use)
msg = Message.user("Hello")
msg = Message.assistant("Hi there!")
msg = Message.system("You are helpful.")

# Properties
msg.text           # The text content
msg.role           # USER, ASSISTANT, or SYSTEM
msg.is_user_message
msg.is_assistant_message
msg.is_system_message
```

---

## Approval Policy

The `ApprovalPolicy` determines which tools need human approval.

### How Approval Works

**Rule**: If EITHER the tool OR the policy says it's risky, require approval.

| Tool Setting | Policy Setting | Result |
|--------------|----------------|--------|
| `requires_approval=True` | (any) | **Requires approval** |
| `requires_approval=False` | Not in high-risk list | **Auto-executes** |
| `requires_approval=False` | In high-risk list | **Requires approval** |

### Simple Usage

Most users just set `requires_approval` on the tool:

```python
from dcaf.tools import tool

@tool(requires_approval=True)  # Always needs approval
def delete_pod(name: str) -> str:
    return kubectl(f"delete pod {name}")

@tool(requires_approval=False)  # Auto-executes
def list_pods() -> str:
    return kubectl("get pods")
```

---

## Domain Events

Events are immutable records of significant things that happened.

### Available Events

| Event | When it fires | Key data |
|-------|---------------|----------|
| `ConversationStarted` | New conversation created | `conversation_id` |
| `ApprovalRequested` | Tool calls need approval | `conversation_id`, `tool_calls` |
| `ToolCallApproved` | User approved a tool | `tool_call_id`, `approved_by` |
| `ToolCallRejected` | User rejected a tool | `tool_call_id`, `reason` |
| `ToolExecuted` | Tool ran successfully | `tool_call`, `result` |
| `ToolExecutionFailed` | Tool execution failed | `tool_call_id`, `error` |

### Subscribing to Events

```python
from dcaf.core import Agent

def log_event(event):
    print(f"[{event.event_type}] {event.timestamp}")

def send_slack_notification(event):
    if event.event_type == "ApprovalRequested":
        slack.post(f"Approval needed: {len(event.tool_calls)} tool(s)")

# Single handler
agent = Agent(tools=[...], on_event=log_event)

# Multiple handlers
agent = Agent(tools=[...], on_event=[log_event, send_slack_notification])
```

### Event Properties

All events have:
- `timestamp` - When the event occurred
- `event_type` - The event class name (e.g., "ApprovalRequested")

---

## Advanced: Direct Domain Access

For advanced use cases, you can work with domain objects directly:

```python
from dcaf.core.domain.entities import Conversation, ToolCall, Message
from dcaf.core.domain.value_objects import ToolCallId, ToolInput
from dcaf.core.domain.events import ApprovalRequested
from dcaf.core.domain.services import ApprovalPolicy
from dcaf.core.domain.exceptions import ConversationBlocked, ToolCallNotFound

# Create a tool call manually
tool_call = ToolCall(
    id=ToolCallId.generate(),
    tool_name="kubectl",
    input=ToolInput({"command": "get pods"}),
    requires_approval=True,
)

# State transitions
tool_call.approve()
tool_call.start_execution()
tool_call.complete("pod-1, pod-2, pod-3")
```

Most users won't need this level of control - the `Agent` class handles it automatically.
