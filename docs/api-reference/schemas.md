# Schemas API Reference

The Schemas module defines the data models used throughout DCAF for message handling, tool calls, commands, and events.

---

## Table of Contents

1. [Overview](#overview)
2. [Message Schemas](#message-schemas)
3. [Data Schemas](#data-schemas)
4. [Event Schemas](#event-schemas)
5. [Context Schemas](#context-schemas)
6. [Examples](#examples)

---

## Overview

DCAF uses Pydantic models for type-safe data handling. All schemas are located in:

- `dcaf/schemas/messages.py` - Message and data models
- `dcaf/schemas/events.py` - Streaming event models

### Import

```python
from dcaf.schemas.messages import (
    AgentMessage,
    Messages,
    Message,
    UserMessage,
    Data,
    ToolCall,
    ExecutedToolCall,
    Command,
    ExecutedCommand,
    PlatformContext
)

from dcaf.schemas.events import (
    TextDeltaEvent,
    ToolCallsEvent,
    ExecutedToolCallsEvent,
    CommandsEvent,
    ExecutedCommandsEvent,
    DoneEvent,
    ErrorEvent
)
```

---

## Message Schemas

### Messages

Container for a list of messages.

```python
class Messages(BaseModel):
    messages: List[Union[UserMessage, AgentMessage]]
```

#### Example

```python
from dcaf.schemas.messages import Messages, UserMessage

msgs = Messages(messages=[
    UserMessage(role="user", content="Hello!"),
    AgentMessage(role="assistant", content="Hi there!")
])
```

---

### Message

Base message model.

```python
class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = ""
    data: Data = Field(default_factory=Data)
    meta_data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None
    user: Optional[User] = None
    agent: Optional[Agent] = None
```

#### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `role` | `"user"` \| `"assistant"` | Required | Message sender role |
| `content` | `str` | `""` | Message text content |
| `data` | `Data` | `Data()` | Associated data payload |
| `meta_data` | `Dict` | `{}` | Additional metadata |
| `timestamp` | `datetime` | `None` | Message timestamp |
| `user` | `User` | `None` | User information |
| `agent` | `Agent` | `None` | Agent information |

---

### UserMessage

Message from a user.

```python
class UserMessage(Message):
    role: Literal["user"] = "user"
    platform_context: Optional[PlatformContext] = None
    ambient_context: Optional[AmbientContext] = None
```

#### Additional Fields

| Field | Type | Description |
|-------|------|-------------|
| `platform_context` | `PlatformContext` | Runtime platform context |
| `ambient_context` | `AmbientContext` | Ambient user context |

#### Example

```python
from dcaf.schemas.messages import UserMessage, PlatformContext

user_msg = UserMessage(
    content="Deploy my application",
    platform_context=PlatformContext(
        tenant_name="production",
        k8s_namespace="my-app"
    )
)
```

---

### AgentMessage

Response message from an agent.

```python
class AgentMessage(Message):
    role: Literal["assistant"] = "assistant"
```

#### Example

```python
from dcaf.schemas.messages import AgentMessage, Data, Command

response = AgentMessage(
    content="I'll help you deploy. Please approve the command below.",
    data=Data(
        cmds=[
            Command(command="kubectl apply -f deployment.yaml")
        ]
    )
)
```

---

### User

User identification.

```python
class User(BaseModel):
    name: str
    id: str
```

---

### Agent

Agent identification.

```python
class Agent(BaseModel):
    name: str
    id: str
```

---

## Data Schemas

### Data

Container for all data associated with a message.

```python
class Data(BaseModel):
    cmds: List[Command] = Field(default_factory=list)
    executed_cmds: List[ExecutedCommand] = Field(default_factory=list)
    tool_calls: List[ToolCall] = Field(default_factory=list)
    executed_tool_calls: List[ExecutedToolCall] = Field(default_factory=list)
    url_configs: List[URLConfig] = Field(default_factory=list)
```

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `cmds` | `List[Command]` | Suggested terminal commands |
| `executed_cmds` | `List[ExecutedCommand]` | Commands that were executed |
| `tool_calls` | `List[ToolCall]` | Tools requiring approval |
| `executed_tool_calls` | `List[ExecutedToolCall]` | Tools that were executed |
| `url_configs` | `List[URLConfig]` | URL configurations |

---

### Command

A suggested terminal command.

```python
class Command(BaseModel):
    command: str
    execute: bool = False
    rejection_reason: Optional[str] = None
    files: Optional[List[FileObject]] = None
```

#### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `command` | `str` | Required | Command string to execute |
| `execute` | `bool` | `False` | Whether to execute (set by client) |
| `rejection_reason` | `str` | `None` | Reason for rejection |
| `files` | `List[FileObject]` | `None` | Files to create before command |

#### Example

```python
from dcaf.schemas.messages import Command, FileObject

cmd = Command(
    command="helm install my-app ./chart",
    files=[
        FileObject(
            file_path="chart/values.yaml",
            file_content="replicaCount: 3\n..."
        )
    ]
)
```

---

### ExecutedCommand

A command that was executed.

```python
class ExecutedCommand(BaseModel):
    command: str
    output: str
```

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `command` | `str` | The command that was executed |
| `output` | `str` | Command output (stdout/stderr) |

---

### ToolCall

A tool call requiring user approval.

```python
class ToolCall(BaseModel):
    id: str
    name: str
    input: Dict[str, Any]
    execute: bool = False
    tool_description: str
    input_description: Dict[str, Any]
    intent: Optional[str] = None
    rejection_reason: Optional[str] = None
```

#### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | Required | Unique tool use ID |
| `name` | `str` | Required | Tool name |
| `input` | `Dict` | Required | Tool input parameters |
| `execute` | `bool` | `False` | Whether to execute |
| `tool_description` | `str` | Required | Human-readable description |
| `input_description` | `Dict` | Required | Parameter descriptions |
| `intent` | `str` | `None` | Intent description |
| `rejection_reason` | `str` | `None` | Reason for rejection |

#### Example

```python
from dcaf.schemas.messages import ToolCall

tool_call = ToolCall(
    id="toolu_abc123",
    name="delete_file",
    input={"path": "/tmp/old-file.txt"},
    tool_description="Delete a file from the filesystem",
    input_description={
        "path": {
            "type": "string",
            "description": "Path to the file to delete"
        }
    },
    intent="Remove temporary file"
)
```

---

### ExecutedToolCall

A tool that was executed.

```python
class ExecutedToolCall(BaseModel):
    id: str
    name: str
    input: Dict[str, Any]
    output: str
```

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Tool use ID |
| `name` | `str` | Tool name |
| `input` | `Dict` | Input parameters used |
| `output` | `str` | Tool output result |

---

### FileObject

A file to be created for command execution.

```python
class FileObject(BaseModel):
    file_path: str
    file_content: str
```

---

### URLConfig

URL configuration for display.

```python
class URLConfig(BaseModel):
    url: HttpUrl
    description: str
```

---

## Event Schemas

Events are used for streaming responses.

### StreamEvent (Base)

```python
class StreamEvent(BaseModel):
    """Base for all stream events. Type field discriminates."""
    type: str
```

---

### TextDeltaEvent

Streaming text tokens.

```python
class TextDeltaEvent(StreamEvent):
    type: Literal["text_delta"] = "text_delta"
    text: str
```

#### Example

```json
{"type": "text_delta", "text": "Hello"}
```

---

### ToolCallsEvent

Tool calls requiring approval.

```python
class ToolCallsEvent(StreamEvent):
    type: Literal["tool_calls"] = "tool_calls"
    tool_calls: List[ToolCall]
```

#### Example

```json
{
    "type": "tool_calls",
    "tool_calls": [
        {
            "id": "toolu_123",
            "name": "get_weather",
            "input": {"location": "NYC"},
            "execute": false,
            "tool_description": "Get weather",
            "input_description": {}
        }
    ]
}
```

---

### ExecutedToolCallsEvent

Tools that were executed.

```python
class ExecutedToolCallsEvent(StreamEvent):
    type: Literal["executed_tool_calls"] = "executed_tool_calls"
    executed_tool_calls: List[ExecutedToolCall]
```

---

### CommandsEvent

Commands for approval.

```python
class CommandsEvent(StreamEvent):
    type: Literal["commands"] = "commands"
    commands: List[Command]
```

---

### ExecutedCommandsEvent

Commands that were executed.

```python
class ExecutedCommandsEvent(StreamEvent):
    type: Literal["executed_commands"] = "executed_commands"
    executed_cmds: List[ExecutedCommand]
```

---

### DoneEvent

Stream completed.

```python
class DoneEvent(StreamEvent):
    type: Literal["done"] = "done"
    stop_reason: Optional[str] = None
```

#### Example

```json
{"type": "done", "stop_reason": "end_turn"}
```

---

### ErrorEvent

Error during streaming.

```python
class ErrorEvent(StreamEvent):
    type: Literal["error"] = "error"
    error: str
```

#### Example

```json
{"type": "error", "error": "Connection timeout"}
```

---

## Context Schemas

### PlatformContext

Runtime context passed from the platform.

```python
class PlatformContext(BaseModel):
    k8s_namespace: Optional[str] = None
    duplo_base_url: Optional[str] = None
    duplo_token: Optional[str] = None
    tenant_name: Optional[str] = None
    aws_credentials: Optional[Dict[str, Any]] = None
    kubeconfig: Optional[str] = None
```

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `k8s_namespace` | `str` | Kubernetes namespace |
| `duplo_base_url` | `str` | DuploCloud API URL |
| `duplo_token` | `str` | DuploCloud API token |
| `tenant_name` | `str` | DuploCloud tenant name |
| `aws_credentials` | `Dict` | AWS credential info |
| `kubeconfig` | `str` | Base64-encoded kubeconfig |

#### Example

```python
from dcaf.schemas.messages import PlatformContext

context = PlatformContext(
    tenant_name="production",
    k8s_namespace="my-app-namespace",
    duplo_base_url="https://api.duplocloud.net",
    duplo_token="eyJ..."
)
```

---

### AmbientContext

Ambient context from user environment.

```python
class AmbientContext(BaseModel):
    user_terminal_cmds: List[ExecutedCommand] = Field(default_factory=list)
```

---

## Examples

### Example 1: Creating a Complete Request

```python
from dcaf.schemas.messages import (
    Messages, UserMessage, PlatformContext, Data, Command
)

# Create a user message with context and approved command
request = Messages(
    messages=[
        UserMessage(
            content="Deploy my app",
            platform_context=PlatformContext(
                tenant_name="staging",
                k8s_namespace="my-app"
            ),
            data=Data(
                cmds=[
                    Command(
                        command="kubectl apply -f deploy.yaml",
                        execute=True  # User approved this command
                    )
                ]
            )
        )
    ]
)

# Convert to dict for API call
request_dict = request.model_dump()
```

### Example 2: Parsing Agent Response

```python
from dcaf.schemas.messages import AgentMessage
import json

# Parse response from API
response_json = '''{
    "role": "assistant",
    "content": "I've found the issue. Here's a command to fix it:",
    "data": {
        "cmds": [
            {
                "command": "kubectl rollout restart deployment/my-app",
                "execute": false
            }
        ],
        "tool_calls": [],
        "executed_tool_calls": []
    }
}'''

response = AgentMessage.model_validate_json(response_json)

print(f"Content: {response.content}")
print(f"Commands: {len(response.data.cmds)}")

for cmd in response.data.cmds:
    print(f"  - {cmd.command}")
```

### Example 3: Handling Tool Calls

```python
from dcaf.schemas.messages import AgentMessage, ToolCall

# Agent response with tool calls
response = AgentMessage(
    content="I need to check the weather. Please approve:",
    data=Data(
        tool_calls=[
            ToolCall(
                id="toolu_weather_123",
                name="get_weather",
                input={"location": "San Francisco, CA", "unit": "fahrenheit"},
                tool_description="Get current weather for a location",
                input_description={
                    "location": {"type": "string", "description": "City and state"},
                    "unit": {"type": "string", "description": "Temperature unit"}
                }
            )
        ]
    )
)

# Display for user approval
for tc in response.data.tool_calls:
    print(f"Tool: {tc.name}")
    print(f"Description: {tc.tool_description}")
    print(f"Input: {tc.input}")
    print()
    
    # User approves
    tc.execute = True
```

### Example 4: Stream Event Processing

```python
from dcaf.schemas.events import (
    TextDeltaEvent, ToolCallsEvent, DoneEvent, ErrorEvent
)
import json

def process_stream_event(line: str):
    """Process a single NDJSON line from the stream."""
    event = json.loads(line)
    event_type = event.get("type")
    
    if event_type == "text_delta":
        delta = TextDeltaEvent.model_validate(event)
        print(delta.text, end="", flush=True)
        
    elif event_type == "tool_calls":
        tc_event = ToolCallsEvent.model_validate(event)
        print("\n[Tool calls pending approval]")
        for tc in tc_event.tool_calls:
            print(f"  - {tc.name}: {tc.input}")
            
    elif event_type == "done":
        done = DoneEvent.model_validate(event)
        print(f"\n[Stream complete: {done.stop_reason}]")
        return True
        
    elif event_type == "error":
        error = ErrorEvent.model_validate(event)
        print(f"\n[Error: {error.error}]")
        return True
    
    return False

# Example usage
stream_lines = [
    '{"type": "text_delta", "text": "Hello, "}',
    '{"type": "text_delta", "text": "how can I help?"}',
    '{"type": "done", "stop_reason": "end_turn"}'
]

for line in stream_lines:
    if process_stream_event(line):
        break
```

### Example 5: Validation and Error Handling

```python
from dcaf.schemas.messages import AgentMessage, Messages
from pydantic import ValidationError

# Validate incoming message
try:
    msgs = Messages.model_validate({
        "messages": [
            {"role": "user", "content": "Hello"}
        ]
    })
except ValidationError as e:
    print(f"Validation error: {e}")

# Create response safely
try:
    response = AgentMessage(
        content="Response text",
        data={"invalid": "data"}  # This will fail
    )
except ValidationError as e:
    print(f"Invalid response: {e}")
    
# Correct way
response = AgentMessage(content="Response text")
```

---

## See Also

- [Message Protocol Guide](../guides/message-protocol.md)
- [Streaming Guide](../guides/streaming.md)
- [Agent Server API Reference](./agent-server.md)

