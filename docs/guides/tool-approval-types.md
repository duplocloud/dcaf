# Tool Approval Types

DCAF supports two distinct approval experiences for tools that require human confirmation
before execution. The `approval_type` field controls which UI experience is presented
to the user.

## Overview

When a tool has `requires_approval=True`, the agent pauses and emits approval events before
executing. The `approval_type` field tells the UI *how* to render the approval dialog:

| Type | UI Experience | When to Use |
|------|--------------|-------------|
| `"tool_call"` | Structured approval dialog showing tool name, inputs, and description | Default — the LLM is calling a structured function |
| `"command"` | Terminal-style command-line approval showing the command string | The agent is about to run a shell or system command |

## How It Works

### The Approval Event Pipeline

```
Tool definition (approval_type="command")
         ↓
AgnoAdapter builds _tool_approval_types registry
         ↓
LLM calls tool → Agno pauses → RunPausedEvent
         ↓
AgnoResponseConverter looks up tool name in registry
    → ToolCallDTO(approval_type="command")
         ↓
agent.py converts to ToolCall schema
    → ToolCall(approval_type="command")
         ↓
ToolCallsEvent emitted
         ↓
ServerAdapter translates (_translate_tool_calls_event):
    → ApprovalsEvent([{type:"command"}, ...])   ← unified (future clients)
    → CommandsEvent([...])                       ← legacy command clients
    → ToolCallsEvent([...])                      ← legacy tool_call clients
```

### Event Emission

For every batch of pending approvals, the server emits events in this order:

1. **`ApprovalsEvent`** — Contains ALL pending approvals. Each approval has a `type` field
   set to `"command"` or `"tool_call"`. This is the recommended event for new clients.

2. **`ToolCallsEvent`** *(legacy)* — Contains only the `"tool_call"` approvals.
   For clients using `data.tool_calls`.

3. **`CommandsEvent`** *(legacy)* — Contains only the `"command"` approvals.
   For clients using `data.cmds`.

!!! warning "Mutual exclusivity"
    Handle EITHER `approvals` OR the legacy events (`tool_calls` / `commands`), never both.
    Handling both will show duplicate approval dialogs to the user.

## Setting `approval_type` on `@tool`

```python
from dcaf.core import tool

# Default: structured tool approval dialog
@tool(description="Fetch user from database", requires_approval=True)
def get_user(user_id: str) -> str:
    return fetch_user(user_id)

# Command-line approval: shows terminal-style UI
@tool(
    description="Run kubectl command",
    requires_approval=True,
    approval_type="command",
)
def run_kubectl(args: str) -> str:
    import subprocess
    return subprocess.check_output(["kubectl"] + args.split()).decode()
```

The `approval_type` parameter accepts `"tool_call"` (default) or `"command"`.
Setting it on the decorator is the recommended approach for user-defined tools.

## Built-in Toolkit Approval Types

When the default toolkit is enabled (`DEFAULT_TOOLKIT=true` environment variable),
DCAF automatically maps native Agno toolkit tools to their approval types:

| Tool | Toolkit | `approval_type` |
|------|---------|----------------|
| `run_shell_command` | `ShellTools` | `"command"` |
| All other tools | `FileTools`, `PythonTools`, etc. | `"tool_call"` |

This mapping is defined in `TOOLKIT_TOOL_APPROVAL_TYPES` in
`dcaf/core/adapters/outbound/agno/adapter.py`. You can reference it directly if needed:

```python
from dcaf.core.adapters.outbound.agno.adapter import TOOLKIT_TOOL_APPROVAL_TYPES
# {"run_shell_command": "command"}
```

## MCP Tools

For MCP servers, set `approval_type` at the `MCPTool` level. All tools from that
server inherit the same type:

```python
from dcaf.mcp import MCPTool

# Default: all tools show structured approval dialog
files_mcp = MCPTool(url="http://localhost:3001/mcp")

# Shell-oriented MCP server: all tools show terminal-style approval
kubectl_mcp = MCPTool(
    url="http://localhost:3002/mcp",
    approval_type="command",
)
```

Combining `approval_type` with `auto_approve_tools`:

```python
# Read-only tools auto-approve; destructive tools show terminal-style dialog
kubectl_mcp = MCPTool(
    url="http://localhost:3002/mcp",
    auto_approve_tools=["*_get*", "*_list*"],   # these never need approval
    approval_type="command",                    # the rest show terminal UI
)
```

## Client Implementation Guide

### Unified Clients (Recommended)

Listen for `approvals` events and dispatch based on `type`:

```javascript
if (event.type === "approvals") {
    for (const approval of event.approvals) {
        if (approval.type === "command") {
            showTerminalApprovalDialog(approval);  // terminal UI
        } else {
            showToolCallApprovalDialog(approval);  // structured UI
        }
    }
}
```

Send approvals back with `data.approvals`:

```json
{
  "messages": [...],
  "data": {
    "approvals": [
      {
        "id": "abc123",
        "type": "command",
        "name": "run_shell_command",
        "input": {"args": ["kubectl", "get", "pods"]},
        "execute": true
      }
    ]
  }
}
```

### Legacy Clients

Legacy clients use `data.tool_calls` for structured tools and `data.cmds` for
command-line tools. DCAF populates only the relevant collection based on `approval_type`.

See [Message Protocol](message-protocol.md) and [Streaming Responses](streaming.md) for
full schema details.

## Why the Distinction Matters

The two types serve different user expectations:

**`tool_call`** — The user sees what function is being called with what parameters.
They understand this is a structured API call. The UI can display parameter names,
types, and descriptions from the tool schema.

**`command`** — The user sees an actual command string that will run on their
infrastructure. Shell commands have a higher blast radius (they can do anything
the process has access to), so the terminal-style UI sets a clearer expectation
than a generic "approve tool call" dialog.
