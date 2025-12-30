# HelpDesk Protocol Compatibility

DCAF Core provides **full compatibility** with the DuploCloud HelpDesk messaging protocol. This enables seamless integration with the HelpDesk frontend and existing agent infrastructure.

---

## Overview

The HelpDesk protocol defines a rich message format that includes:

- **Commands**: Terminal commands for user approval and execution
- **Tool Calls**: Structured tool invocations with approval workflow
- **Platform Context**: Runtime context (tenant, namespace, credentials)
- **Streaming Events**: Real-time updates during agent execution

DCAF Core replicates this protocol in the `dcaf.core` module, ensuring compatibility while providing a cleaner, more Pythonic API.

---

## Quick Start

```python
from dcaf.core import (
    Agent,
    PlatformContext,
    ChatMessage,
    # HelpDesk DTOs
    DataDTO,
    CommandDTO,
    ExecutedCommandDTO,
    ToolCallDTO,
    ExecutedToolCallDTO,
    StreamEvent,
)
from dcaf.tools import tool

# Define tools
@tool(description="List Kubernetes pods")
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

@tool(requires_approval=True, description="Delete a pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")

# Create agent
agent = Agent(tools=[list_pods, delete_pod])

# Create message with platform context
context = PlatformContext(
    tenant_name="acme-prod",
    k8s_namespace="default",
    duplo_base_url="https://acme.duplocloud.net",
)

response = agent.run(
    messages=[ChatMessage.user("Delete the nginx pod", context=context)]
)
```

---

## Platform Context

`PlatformContext` carries runtime information about the user's environment:

```python
from dcaf.core import PlatformContext

context = PlatformContext(
    # Kubernetes
    k8s_namespace="production",
    kubeconfig="/path/to/kubeconfig",
    
    # DuploCloud
    tenant_name="acme-prod",
    duplo_base_url="https://acme.duplocloud.net",
    duplo_token="eyJ...",
    
    # AWS
    aws_credentials={
        "access_key": "AKIA...",
        "secret_key": "...",
        "session_token": "...",
        "region": "us-west-2",
    },
)
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `k8s_namespace` | `str` | Kubernetes namespace for kubectl operations |
| `kubeconfig` | `str` | Path to kubeconfig or inline content |
| `tenant_name` | `str` | DuploCloud tenant name |
| `duplo_base_url` | `str` | DuploCloud API base URL |
| `duplo_token` | `str` | DuploCloud authentication token |
| `aws_credentials` | `dict` | AWS credentials (access_key, secret_key, etc.) |

### Using with Messages

```python
from dcaf.core import ChatMessage, PlatformContext

# Pass context with a message
msg = ChatMessage.user(
    content="Delete the nginx pod",
    context=PlatformContext(tenant_name="acme", k8s_namespace="default"),
)

# Or use a dict
msg = ChatMessage.user(
    content="Delete the nginx pod",
    context={"tenant_name": "acme", "k8s_namespace": "default"},
)
```

---

## Command DTOs

Commands represent terminal commands for user approval.

### CommandDTO

```python
from dcaf.core import CommandDTO

# Command awaiting approval
cmd = CommandDTO(
    command="kubectl delete pod nginx-1",
    execute=False,  # Not yet approved
)

# Approved command
approved_cmd = CommandDTO(
    command="kubectl delete pod nginx-1",
    execute=True,
)

# Rejected command
rejected_cmd = CommandDTO(
    command="rm -rf /",
    execute=False,
    rejection_reason="This command is too dangerous",
)
```

### ExecutedCommandDTO

```python
from dcaf.core import ExecutedCommandDTO

# Result of executed command
result = ExecutedCommandDTO(
    command="kubectl get pods",
    output="NAME         READY   STATUS\nnginx-1      1/1     Running",
)
```

### With Files

Commands can include files to create before execution:

```python
from dcaf.core.application.dto import CommandDTO, FileObject

cmd = CommandDTO(
    command="kubectl apply -f /tmp/deployment.yaml",
    files=[
        FileObject(
            file_path="/tmp/deployment.yaml",
            file_content="apiVersion: apps/v1\nkind: Deployment...",
        )
    ],
)
```

---

## Tool Call DTOs

Tool calls follow the HelpDesk protocol format with all required fields.

### ToolCallDTO

```python
from dcaf.core import ToolCallDTO

tool_call = ToolCallDTO(
    id="call_abc123",
    name="delete_pod",
    input={"name": "nginx-1", "namespace": "default"},
    execute=False,  # Awaiting approval
    tool_description="Delete a Kubernetes pod",
    input_description={
        "name": {"type": "string", "description": "Pod name"},
        "namespace": {"type": "string", "description": "Namespace"},
    },
    intent="User wants to delete the failing nginx pod",
)
```

### ExecutedToolCallDTO

```python
from dcaf.core import ExecutedToolCallDTO

executed = ExecutedToolCallDTO(
    id="call_abc123",
    name="delete_pod",
    input={"name": "nginx-1", "namespace": "default"},
    output="pod \"nginx-1\" deleted",
)
```

---

## Data Container

`DataDTO` is the container that holds all commands and tool calls:

```python
from dcaf.core import DataDTO, CommandDTO, ToolCallDTO

data = DataDTO(
    cmds=[
        CommandDTO(command="kubectl get pods"),
    ],
    executed_cmds=[
        ExecutedCommandDTO(command="kubectl get nodes", output="..."),
    ],
    tool_calls=[
        ToolCallDTO(id="1", name="list_pods", input={}),
    ],
    executed_tool_calls=[
        ExecutedToolCallDTO(id="0", name="get_status", input={}, output="OK"),
    ],
)

# Check for pending items
if data.has_pending_items:
    print("User approval required")
```

---

## Agent Response

`AgentResponse` includes the full HelpDesk data structure:

```python
from dcaf.core import Agent
from dcaf.tools import tool

@tool(description="List pods")
def list_pods() -> str:
    return "nginx-1, nginx-2"

agent = Agent(tools=[list_pods])
response = agent.run(messages=[{"role": "user", "content": "List pods"}])

# Access the response
print(response.text)                    # Agent's text response
print(response.data.to_dict())          # Full HelpDesk data structure
print(response.commands)                # Pending commands
print(response.tool_calls)              # Pending tool calls
print(response.executed_commands)       # Commands that were run
print(response.executed_tool_calls)     # Tools that were run

# Convert to HelpDesk message format
helpdesk_msg = response.to_helpdesk_message()
# {'role': 'assistant', 'content': '...', 'data': {...}, 'meta_data': {...}}
```

---

## Stream Events

DCAF Core supports all HelpDesk streaming event types:

```python
from dcaf.core import StreamEvent, StreamEventType

# Create events programmatically
events = [
    # Text streaming
    StreamEvent.text_delta("Hello, "),
    StreamEvent.text_delta("world!"),
    
    # Commands for approval
    StreamEvent.commands_event([
        CommandDTO(command="kubectl get pods"),
    ]),
    
    # Tool calls for approval
    StreamEvent.tool_calls_event([
        ToolCallDTO(id="1", name="list_pods", input={}),
    ]),
    
    # Executed items
    StreamEvent.executed_commands_event([
        ExecutedCommandDTO(command="kubectl get nodes", output="..."),
    ]),
    StreamEvent.executed_tool_calls_event([
        ExecutedToolCallDTO(id="1", name="list_pods", input={}, output="..."),
    ]),
    
    # Completion
    StreamEvent.done(),
]

# Convert to HelpDesk NDJSON format
for event in events:
    print(event.to_dict())
    # {"type": "text_delta", "text": "Hello, "}
    # {"type": "commands", "commands": [...]}
    # etc.
```

### Event Types

| Event Type | Description | Data Fields |
|------------|-------------|-------------|
| `text_delta` | Streaming text chunk | `text` |
| `commands` | Commands for approval | `commands` |
| `tool_calls` | Tool calls for approval | `tool_calls` |
| `executed_commands` | Executed command results | `executed_cmds` |
| `executed_tool_calls` | Executed tool results | `executed_tool_calls` |
| `done` | Stream complete | `stop_reason` (optional) |
| `error` | Error occurred | `error`, `code` |

---

## Server Integration

When using `serve()`, responses are automatically formatted for HelpDesk:

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool

@tool(description="List pods")
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

agent = Agent(tools=[list_pods])
serve(agent)  # Responses are HelpDesk-compatible
```

The server endpoints return HelpDesk-formatted responses:

```bash
# Synchronous
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{
      "role": "user",
      "content": "List pods",
      "platform_context": {
        "tenant_name": "acme",
        "k8s_namespace": "default"
      }
    }]
  }'

# Response
{
  "role": "assistant",
  "content": "Here are the pods...",
  "data": {
    "cmds": [],
    "executed_cmds": [],
    "tool_calls": [],
    "executed_tool_calls": [...]
  }
}
```

---

## Mapping: Legacy vs Core

| Legacy (dcaf/schemas) | Core (dcaf/core) | Notes |
|-----------------------|------------------|-------|
| `PlatformContext` | `PlatformContext` | Same structure |
| `Command` | `CommandDTO` | Same structure |
| `ExecutedCommand` | `ExecutedCommandDTO` | Same structure |
| `ToolCall` | `ToolCallDTO` | Same structure |
| `ExecutedToolCall` | `ExecutedToolCallDTO` | Same structure |
| `Data` | `DataDTO` | Same structure |
| `AgentMessage` | `AgentResponse` | Core uses dataclass |
| `TextDeltaEvent` | `StreamEvent.text_delta()` | Factory method |
| `CommandsEvent` | `StreamEvent.commands_event()` | Factory method |
| `DoneEvent` | `StreamEvent.done()` | Factory method |

---

## Complete Example

```python
from dcaf.core import (
    Agent, serve, PlatformContext, ChatMessage,
    CommandDTO, ToolCallDTO, DataDTO,
)
from dcaf.tools import tool

# Define tools
@tool(description="Get pod status")
def get_pods(namespace: str = "default") -> str:
    """List all pods in a namespace."""
    return subprocess.run(
        ["kubectl", "get", "pods", "-n", namespace],
        capture_output=True, text=True
    ).stdout

@tool(requires_approval=True, description="Delete a pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    """Delete a pod. Requires user approval."""
    return subprocess.run(
        ["kubectl", "delete", "pod", name, "-n", namespace],
        capture_output=True, text=True
    ).stdout

# Create agent
agent = Agent(
    tools=[get_pods, delete_pod],
    system_prompt="You are a Kubernetes assistant.",
)

# Run with full HelpDesk context
context = PlatformContext(
    tenant_name="production",
    k8s_namespace="default",
    duplo_base_url="https://prod.duplocloud.net",
)

response = agent.run(
    messages=[
        ChatMessage.user("Delete the crashing pod", context=context)
    ]
)

# Check for pending approvals
if response.has_pending_approvals:
    print("The following actions need approval:")
    
    for cmd in response.pending_commands:
        print(f"  Command: {cmd.command}")
    
    for tc in response.pending_tool_calls:
        print(f"  Tool: {tc.name}({tc.input})")
        print(f"  Intent: {tc.intent}")

# Serve it
serve(agent)  # http://localhost:8000
```
