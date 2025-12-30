# Framework Adapters

DCAF uses a **plugin-style architecture** for LLM frameworks. This allows you to swap between different agent orchestration frameworks (Agno, Strands, LangChain, etc.) without changing your application code.

---

## Quick Start

```python
from dcaf.core import Agent

# Using Agno (default)
agent = Agent(
    framework="agno",
    provider="bedrock",
    model="anthropic.claude-3-sonnet-20240229-v1:0",
)

# Using a different framework (when available)
agent = Agent(
    framework="strands",  # or "langchain", etc.
    model="anthropic.claude-3-sonnet-20240229-v1:0",
)
```

---

## How Discovery Works

DCAF uses **convention-based discovery** - no manifest files or registration required.

### The Convention

```
dcaf/core/adapters/outbound/{framework_name}/
├── __init__.py      ← Must export create_adapter(**kwargs)
└── adapter.py       ← Your adapter implementation
```

### Discovery Flow

```
┌─────────────────────────────────────────────────────────────┐
│  Agent(framework="myframework")                             │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  loader.py: load_adapter("myframework")                     │
│                                                             │
│  1. import dcaf.core.adapters.outbound.myframework          │
│  2. call module.create_adapter(**kwargs)                    │
│  3. return adapter instance                                 │
└─────────────────────────────────────────────────────────────┘
```

### Listing Available Frameworks

```python
from dcaf.core.adapters.loader import list_frameworks

frameworks = list_frameworks()
print(frameworks)  # ['agno', 'strands', 'langchain']
```

---

## Creating a New Adapter

Adding a new framework adapter requires **just two files**:

### Step 1: Create the Folder

```bash
mkdir -p dcaf/core/adapters/outbound/myframework
```

### Step 2: Create `__init__.py`

This file **must** export a `create_adapter()` function:

```python
# dcaf/core/adapters/outbound/myframework/__init__.py

"""
MyFramework Adapter.

This module provides integration with MyFramework for agent orchestration.
"""

def create_adapter(**kwargs):
    """
    Factory function for creating a MyFrameworkAdapter.
    
    This function is REQUIRED by the adapter loader convention.
    
    Args:
        **kwargs: Configuration passed from Agent():
            - model_id: Model identifier
            - provider: Provider name (if applicable)
            - aws_profile: AWS profile (for AWS-based frameworks)
            - aws_region: AWS region
            - api_key: API key (for API-based providers)
            - max_tokens: Maximum response tokens
            - temperature: Sampling temperature
            
    Returns:
        Configured adapter instance
    """
    from .adapter import MyFrameworkAdapter
    return MyFrameworkAdapter(**kwargs)


__all__ = ["create_adapter"]
```

### Step 3: Create `adapter.py`

Your adapter must implement the `RuntimeAdapter` protocol:

```python
# dcaf/core/adapters/outbound/myframework/adapter.py

"""MyFramework adapter implementing the RuntimeAdapter protocol."""

from typing import List, Optional, Iterator, Any
import logging

# Import your framework
# from myframework import Agent as MyAgent

from ....application.dto.responses import AgentResponse, StreamEvent, ToolCallDTO

logger = logging.getLogger(__name__)


class MyFrameworkAdapter:
    """
    Adapts MyFramework to DCAF's RuntimeAdapter protocol.
    
    This adapter translates between DCAF's domain model and MyFramework,
    enabling seamless integration while keeping framework-specific code isolated.
    """
    
    def __init__(
        self,
        model_id: str = "default-model",
        provider: str = "default",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        # Add framework-specific parameters
        **kwargs,
    ) -> None:
        """
        Initialize the adapter.
        
        Args:
            model_id: The model identifier
            provider: The provider name
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional framework-specific configuration
        """
        self._model_id = model_id
        self._provider = provider
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._extra_config = kwargs
        
        logger.info(f"MyFrameworkAdapter initialized: model={model_id}")
    
    @property
    def model_id(self) -> str:
        """Get the model identifier."""
        return self._model_id
    
    @property
    def provider(self) -> str:
        """Get the provider name."""
        return self._provider
    
    def invoke(
        self,
        messages: List[Any],
        tools: List[Any],
        system_prompt: Optional[str] = None,
    ) -> AgentResponse:
        """
        Execute a single request and return the response.
        
        This method:
        1. Converts DCAF messages to framework format
        2. Converts DCAF tools to framework format
        3. Calls the framework
        4. Converts the response back to DCAF format
        
        Args:
            messages: List of DCAF Message objects
            tools: List of DCAF Tool objects
            system_prompt: Optional system instructions
            
        Returns:
            AgentResponse with the result
        """
        # TODO: Implement your framework integration
        
        # 1. Convert messages to framework format
        # framework_messages = self._convert_messages(messages)
        
        # 2. Convert tools to framework format
        # framework_tools = self._convert_tools(tools)
        
        # 3. Call the framework
        # result = my_framework_agent.run(framework_messages, framework_tools)
        
        # 4. Convert response back
        # return self._convert_response(result)
        
        raise NotImplementedError("MyFrameworkAdapter.invoke() not implemented")
    
    def invoke_stream(
        self,
        messages: List[Any],
        tools: List[Any],
        system_prompt: Optional[str] = None,
    ) -> Iterator[StreamEvent]:
        """
        Execute with streaming response.
        
        Args:
            messages: List of DCAF Message objects
            tools: List of DCAF Tool objects
            system_prompt: Optional system instructions
            
        Yields:
            StreamEvent objects for real-time updates
        """
        # TODO: Implement streaming
        
        yield StreamEvent.message_start()
        yield StreamEvent.text_delta("Not implemented")
        yield StreamEvent.message_end(AgentResponse(
            conversation_id="",
            text="Streaming not implemented",
            is_complete=True,
        ))
```

### Step 4: Use It!

```python
from dcaf.core import Agent

agent = Agent(
    framework="myframework",
    model="my-model-id",
)
```

**That's it!** No registration, no manifest, no if-statements.

---

## The RuntimeAdapter Protocol

All adapters must implement this interface:

```python
from typing import Protocol, List, Iterator, Any, Optional

class RuntimeAdapter(Protocol):
    """Protocol that all framework adapters must implement."""
    
    @property
    def model_id(self) -> str:
        """Get the model identifier."""
        ...
    
    @property
    def provider(self) -> str:
        """Get the provider name."""
        ...
    
    def invoke(
        self,
        messages: List[Any],
        tools: List[Any],
        system_prompt: Optional[str] = None,
    ) -> AgentResponse:
        """Execute a single request and return response."""
        ...
    
    def invoke_stream(
        self,
        messages: List[Any],
        tools: List[Any],
        system_prompt: Optional[str] = None,
    ) -> Iterator[StreamEvent]:
        """Execute with streaming response."""
        ...
```

---

## Available Frameworks

### Agno (Default)

The [Agno SDK](https://docs.agno.com/) provides a unified interface for multiple LLM providers.

```python
agent = Agent(
    framework="agno",
    provider="bedrock",  # or "anthropic", "openai", "ollama"
    model="anthropic.claude-3-sonnet-20240229-v1:0",
    aws_profile="my-profile",
)
```

**Supported Providers:**

| Provider | Install | Model Examples |
|----------|---------|----------------|
| `bedrock` | *(included)* | `anthropic.claude-3-sonnet-20240229-v1:0` |
| `anthropic` | *(included)* | `claude-3-sonnet-20240229` |
| `openai` | `pip install openai` | `gpt-4`, `gpt-4-turbo` |
| `azure` | `pip install openai` | Azure deployment names |
| `google` | `pip install google-generativeai` | `gemini-pro` |
| `ollama` | `pip install ollama` | `llama2`, `mistral` |

**Production Features:**

The Agno adapter includes battle-tested patterns:

- ✅ **Async Support** - Uses `aioboto3` for non-blocking AWS calls
- ✅ **Message Filtering** - Removes tool messages for Bedrock compatibility
- ✅ **Alternation Validation** - Ensures user/assistant message order
- ✅ **Parallel Tool Workaround** - Prevents `ValidationException` errors
- ✅ **Metrics Logging** - Token counts, duration, timing

### Strands (Coming Soon)

AWS Strands Agent is AWS's native agent framework for Bedrock.

```python
agent = Agent(
    framework="strands",
    model="anthropic.claude-3-sonnet-20240229-v1:0",
    aws_profile="production",
)
```

### LangChain (Future)

LangChain integration for those who prefer its ecosystem.

```python
agent = Agent(
    framework="langchain",
    provider="bedrock",
    model="anthropic.claude-3-sonnet-20240229-v1:0",
)
```

---

## Best Practices

### 1. Keep Framework Code Isolated

All framework-specific code should live in its adapter folder:

```
dcaf/core/adapters/outbound/myframework/
├── __init__.py           # Factory function
├── adapter.py            # Main adapter
├── message_converter.py  # Message format conversion
├── tool_converter.py     # Tool format conversion
└── types.py              # Framework-specific types
```

### 2. Handle Errors Gracefully

```python
def invoke(self, messages, tools, system_prompt=None):
    try:
        result = self._call_framework(messages, tools)
        return self._convert_response(result)
    except FrameworkError as e:
        logger.error(f"Framework error: {e}")
        return AgentResponse(
            conversation_id="",
            text=f"Error: {str(e)}",
            is_complete=True,
        )
```

### 3. Log Important Events

```python
import logging
logger = logging.getLogger(__name__)

def invoke(self, messages, tools, system_prompt=None):
    logger.info(f"Invoking with {len(messages)} messages, {len(tools)} tools")
    # ...
    logger.debug(f"Response: {result}")
```

### 4. Support Optional Dependencies

```python
def _create_model(self):
    try:
        from some_optional_package import Model
    except ImportError:
        raise ImportError(
            "This provider requires 'some-package'. "
            "Install it with: pip install some-package"
        )
    return Model(...)
```

### 5. Support Async Operations

For non-blocking operation in async contexts (FastAPI, etc.):

```python
class MyFrameworkAdapter:
    # Async methods (preferred for web servers)
    async def ainvoke(self, messages, tools, system_prompt=None):
        # Use async session/client
        result = await self._async_client.call(...)
        return self._convert_response(result)
    
    async def ainvoke_stream(self, messages, tools, system_prompt=None):
        async for chunk in self._async_client.stream(...):
            yield self._convert_event(chunk)
    
    # Sync methods (wrap async internally)
    def invoke(self, messages, tools, system_prompt=None):
        import asyncio
        return asyncio.run(self.ainvoke(messages, tools, system_prompt))
```

### 6. Handle Provider-Specific Quirks

Document and work around provider-specific issues:

```python
# Example: Bedrock message filtering
def _filter_messages(self, messages):
    """
    Bedrock requires:
    1. First message from 'user'
    2. Strict user/assistant alternation
    3. No tool blocks in history
    """
    filtered = []
    for msg in messages:
        # Skip tool messages
        if isinstance(msg.get("content"), list):
            continue
        filtered.append(msg)
    return self._ensure_alternation(filtered)
```

---

## Troubleshooting

### Framework Not Found

```
ValueError: Unknown framework: 'myframework'. Available frameworks: agno, strands
```

**Check:**
1. Folder exists at `dcaf/core/adapters/outbound/myframework/`
2. `__init__.py` exists and exports `create_adapter()`
3. No syntax errors in the module

### Missing create_adapter

```
ValueError: Framework 'myframework' is missing the required create_adapter() function
```

**Fix:** Add to `__init__.py`:

```python
def create_adapter(**kwargs):
    from .adapter import MyAdapter
    return MyAdapter(**kwargs)
```

### Import Errors

```
ModuleNotFoundError: No module named 'somepackage'
```

**Fix:** Install the required dependency:

```bash
pip install somepackage
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Your Code                                │
│                   Agent(framework="agno")                        │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Agent Class                              │
│                   (dcaf/core/agent.py)                          │
│                                                                  │
│   self._runtime = load_adapter(framework, **kwargs)             │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Adapter Loader                              │
│                 (dcaf/core/adapters/loader.py)                  │
│                                                                  │
│   module = import(f"dcaf.core.adapters.outbound.{framework}")   │
│   return module.create_adapter(**kwargs)                         │
└─────────────────────────────┬───────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│     agno/       │ │    strands/     │ │   langchain/    │
│                 │ │                 │ │                 │
│ AgnoAdapter     │ │ StrandsAdapter  │ │ LangChainAdapter│
│                 │ │                 │ │                 │
│ create_adapter()│ │ create_adapter()│ │ create_adapter()│
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   Agno SDK      │ │   Strands SDK   │ │   LangChain     │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

---

## Summary

| Task | How |
|------|-----|
| Use a framework | `Agent(framework="name")` |
| List frameworks | `list_frameworks()` |
| Add new framework | Create folder + `create_adapter()` |
| No registration needed | Convention-based discovery |
| Swap frameworks | Change one parameter |
