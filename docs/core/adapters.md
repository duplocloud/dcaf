# Adapters

Adapters translate between our domain and external systems. Each framework gets its own cohesive module containing all related code.

---

## Overview

The adapters layer includes:

- **Inbound Adapters**: Handle incoming requests (HTTP, CLI)
- **Outbound Adapters**: Implement ports for external services (LLM frameworks, databases)

---

## Agno Adapter

The Agno adapter provides integration with the [Agno SDK](https://docs.agno.com/) for agent orchestration with Claude models on AWS Bedrock and other providers.

> **Note**: This adapter uses the real Agno SDK (`pip install agno`). For Bedrock, ensure you have valid AWS credentials configured:
> ```bash
> # Option 1: Environment variables
> export AWS_ACCESS_KEY_ID=your_access_key
> export AWS_SECRET_ACCESS_KEY=your_secret_key
> export AWS_REGION=us-east-1
>
> # Option 2: AWS Profile (recommended)
> # Uses ~/.aws/credentials profiles
> Agent(aws_profile="my-profile")
> ```

### Location

```
dcaf/core/adapters/outbound/agno/
├── __init__.py
├── adapter.py           # AgnoAdapter
├── tool_converter.py    # AgnoToolConverter
├── message_converter.py # AgnoMessageConverter
└── types.py             # Agno-specific types
```

### Features

The Agno adapter includes **production-proven patterns** for reliability:

| Feature | Description |
|---------|-------------|
| **Async Support** | Uses `aioboto3` for non-blocking AWS calls |
| **Message Filtering** | Removes tool messages to prevent Bedrock errors |
| **Alternation Validation** | Ensures user/assistant message alternation |
| **Parallel Tool Workaround** | Limits concurrent tool calls to prevent bugs |
| **Metrics Extraction** | Captures tokens, duration, and timing |
| **Region Inference** | Extracts region from ARN-style model IDs |

### Usage

```python
from dcaf.core.adapters.outbound.agno import AgnoAdapter

# Create adapter with AWS profile
adapter = AgnoAdapter(
    model_id="anthropic.claude-3-sonnet-20240229-v1:0",
    provider="bedrock",
    aws_profile="my-profile",
    aws_region="us-west-2",
    max_tokens=4096,
    temperature=0.1,
)

# Async invocation (preferred for FastAPI)
response = await adapter.ainvoke(
    messages=conversation.messages,
    tools=[my_tool],
    system_prompt="You are helpful.",
)

# Sync invocation (wraps async internally)
response = adapter.invoke(
    messages=conversation.messages,
    tools=[my_tool],
)
```

### AgnoAdapter

Implements the `AgentRuntime` port with both sync and async interfaces.

```python
class AgnoAdapter:
    def __init__(
        self,
        model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0",
        provider: str = "bedrock",
        max_tokens: int = 4096,
        temperature: float = 0.1,
        # AWS configuration
        aws_profile: Optional[str] = None,
        aws_region: Optional[str] = None,
        aws_access_key: Optional[str] = None,
        aws_secret_key: Optional[str] = None,
        # Generic API key (for non-AWS providers)
        api_key: Optional[str] = None,
        # Behavior flags
        tool_call_limit: Optional[int] = None,
        disable_history: bool = False,
        disable_tool_filtering: bool = False,
    ): ...
    
    # Async methods (preferred)
    async def ainvoke(
        self,
        messages: List[Any],
        tools: List[Any],
        system_prompt: Optional[str] = None,
    ) -> AgentResponse: ...
    
    async def ainvoke_stream(
        self,
        messages: List[Any],
        tools: List[Any],
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[StreamEvent]: ...
    
    # Sync methods (wrap async internally)
    def invoke(
        self,
        messages: List[Message],
        tools: List[Tool],
        system_prompt: Optional[str] = None,
    ) -> AgentResponse: ...
    
    def invoke_stream(
        self,
        messages: List[Message],
        tools: List[Tool],
        system_prompt: Optional[str] = None,
    ) -> Iterator[StreamEvent]: ...
    
    # Cleanup
    async def cleanup(self) -> None: ...
```

### Tracing and Observability

The Agno adapter supports distributed tracing through the `platform_context` parameter. Tracing IDs are passed to the Agno SDK and included in response metadata.

**Supported Tracing Fields:**

| Field | Agno Parameter | Description |
|-------|----------------|-------------|
| `user_id` | `user_id` | User identifier |
| `session_id` | `session_id` | Session grouping runs |
| `run_id` | `run_id` | Unique execution ID |
| `request_id` | `metadata.request_id` | HTTP correlation ID |
| `tenant_id` | `metadata.tenant_id` | Tenant identifier |

**Usage:**

```python
# Via AgentRequest (recommended)
request = AgentRequest(
    content="What pods are running?",
    user_id="user-123",
    session_id="session-abc",
    run_id="run-xyz",
    request_id="req-456",
    tools=[kubectl_tool],
)

# Via platform_context dict
response = await adapter.ainvoke(
    messages=messages,
    tools=tools,
    platform_context={
        "user_id": "user-123",
        "session_id": "session-abc",
        "run_id": "run-xyz",
        "request_id": "req-456",
        "tenant_id": "tenant-1",
    },
)

# Tracing IDs returned in response metadata
print(response.metadata)
# {'run_id': 'run-xyz', 'session_id': 'session-abc', ...}
```

**Debug Mode:**

Enable Agno's verbose debug logging:

```bash
# Option 1: Set Python log level to DEBUG
LOG_LEVEL=DEBUG python your_agent.py

# Option 2: Set AGNO_DEBUG directly
AGNO_DEBUG=true python your_agent.py
```

See [Tracing and Observability Guide](../guides/tracing-observability.md) for complete documentation.

### Environment Variables

The adapter supports configuration via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-west-2` | Default AWS region |
| `AGNO_TOOL_CALL_LIMIT` | `1` | Max concurrent tool calls |
| `AGNO_DISABLE_HISTORY` | `false` | Disable message history |
| `DISABLE_TOOL_FILTERING` | `false` | Disable tool message filtering |
| `LOG_LEVEL` | `INFO` | Python log level (`DEBUG` enables Agno verbose mode) |
| `AGNO_DEBUG` | `false` | Enable Agno debug mode directly |

### Bedrock Compatibility

The adapter includes workarounds for Bedrock-specific issues:

**1. Message Filtering**

Tool-related messages are filtered from history to prevent `ValidationException`:

```python
# These message types are automatically filtered:
# - Messages with content: null
# - Messages with empty string content
# - Messages with content: [...] (tool blocks)
```

**2. Message Alternation**

Bedrock requires strict user/assistant alternation:

```python
# Automatically fixed:
# - Leading assistant messages removed
# - Consecutive same-role messages deduplicated
```

**3. Parallel Tool Prevention**

A bug in Agno/Bedrock causes errors with parallel tool calls:

```python
# Workarounds applied:
# - tool_call_limit=1 (default)
# - System prompt instruction to call tools one at a time
```

### Metrics

The adapter extracts metrics from each run:

```python
@dataclass
class AgnoMetrics:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    duration: float = 0.0
    time_to_first_token: Optional[float] = None
```

Metrics are logged automatically:

```
📊 Agno Metrics: tokens=1234 (in=100, out=1134), duration=2.345s
🔧 Agno Tools: Executed 2 tool call(s)
```

### AgnoToolConverter

Converts dcaf Tools to Agno format.

```python
from dcaf.core.adapters.outbound.agno import AgnoToolConverter

converter = AgnoToolConverter()

# Convert single tool
agno_tool = converter.to_agno(dcaf_tool)

# Convert list of tools
agno_tools = converter.to_agno_list(dcaf_tools)
```

### AgnoMessageConverter

Converts messages bidirectionally.

```python
from dcaf.core.adapters.outbound.agno import AgnoMessageConverter

converter = AgnoMessageConverter()

# Convert to Agno format
agno_messages = converter.to_agno(dcaf_messages)

# Convert from Agno response
response = converter.from_agno(agno_response, conversation_id)

# Convert streaming events
stream_event = converter.stream_event_from_agno(agno_event)
```

---

## Persistence Adapters

### InMemoryConversationRepository

Simple in-memory implementation for testing and development.

```python
from dcaf.core.adapters.outbound.persistence import InMemoryConversationRepository

repo = InMemoryConversationRepository()

# Save conversation
repo.save(conversation)

# Retrieve
loaded = repo.get(conversation.id)

# Check existence
exists = repo.exists(conversation.id)

# Get or create
conv = repo.get_or_create(ConversationId("new-id"))

# Delete
deleted = repo.delete(conversation.id)

# Utility methods
repo.clear()      # Clear all conversations
repo.count()      # Get count
repo.all()        # Get all conversations
```

**Thread Safety**: Uses a reentrant lock for concurrent access.

**Limitations**:
- Data is lost when process ends
- Not suitable for distributed systems
- Use for testing and single-instance deployments only

---

## Adding a New Framework Adapter

Follow these steps to add support for a new LLM framework (e.g., LangChain).

### Step 1: Create the Module Structure

```
dcaf/core/adapters/outbound/langchain/
├── __init__.py
├── adapter.py
├── tool_converter.py
├── message_converter.py
└── types.py
```

### Step 2: Define Types

```python
# types.py
from typing import TypedDict, List, Dict, Any

class LangChainMessage(TypedDict):
    role: str
    content: str

class LangChainTool(TypedDict):
    name: str
    description: str
    parameters: Dict[str, Any]
```

### Step 3: Implement Tool Converter

```python
# tool_converter.py
from dcaf.tools import Tool

class LangChainToolConverter:
    def to_langchain(self, tool: Tool) -> dict:
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.schema.get("input_schema", {}),
        }
    
    def to_langchain_list(self, tools: List[Tool]) -> List[dict]:
        return [self.to_langchain(t) for t in tools]
```

### Step 4: Implement Message Converter

```python
# message_converter.py
from dcaf.core.domain.entities import Message, MessageRole
from dcaf.core.application.dto import AgentResponse

class LangChainMessageConverter:
    def to_langchain(self, messages: List[Message]) -> List[dict]:
        return [
            {
                "role": self._convert_role(m.role),
                "content": m.text or "",
            }
            for m in messages
        ]
    
    def from_langchain(
        self, 
        response: dict,
        conversation_id: str,
    ) -> AgentResponse:
        # Parse LangChain response format
        ...
    
    def _convert_role(self, role: MessageRole) -> str:
        mapping = {
            MessageRole.USER: "human",
            MessageRole.ASSISTANT: "ai",
            MessageRole.SYSTEM: "system",
        }
        return mapping.get(role, "human")
```

### Step 5: Implement Adapter

```python
# adapter.py
from dcaf.core.application.ports import AgentRuntime
from .tool_converter import LangChainToolConverter
from .message_converter import LangChainMessageConverter

class LangChainAdapter:
    def __init__(self, model: str):
        self._tool_converter = LangChainToolConverter()
        self._message_converter = LangChainMessageConverter()
        # Initialize LangChain components
        
    def invoke(
        self,
        messages: List[Message],
        tools: List[Tool],
        system_prompt: Optional[str] = None,
    ) -> AgentResponse:
        # 1. Convert to LangChain format
        lc_messages = self._message_converter.to_langchain(messages)
        lc_tools = self._tool_converter.to_langchain_list(tools)
        
        # 2. Call LangChain
        response = self._chain.invoke(lc_messages, tools=lc_tools)
        
        # 3. Convert back
        return self._message_converter.from_langchain(
            response, 
            conversation_id="..."
        )
```

### Step 6: Export from `__init__.py`

```python
# __init__.py
from .adapter import LangChainAdapter
from .tool_converter import LangChainToolConverter
from .message_converter import LangChainMessageConverter

__all__ = [
    "LangChainAdapter",
    "LangChainToolConverter", 
    "LangChainMessageConverter",
]
```

---

## Best Practices

1. **Isolate framework code**: All framework-specific code stays in its adapter folder
2. **Don't leak abstractions**: Convert to/from domain types at adapter boundaries
3. **Handle errors gracefully**: Catch framework exceptions and convert to domain exceptions
4. **Support streaming**: Implement both sync and streaming methods
5. **Test converters independently**: Unit test converters without the full framework
6. **Document framework requirements**: Note which framework version is supported
