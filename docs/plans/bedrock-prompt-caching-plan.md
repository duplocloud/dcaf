# Bedrock Prompt Caching Implementation Plan

## Overview

**Feature**: Add AWS Bedrock prompt caching support to DCAF agents  
**Priority**: Performance optimization  
**Estimated Effort**: 2-3 days  
**Target Engineer Level**: Junior  

---

## Background

### What is Prompt Caching?

AWS Bedrock offers a feature called "prompt caching" that can significantly reduce latency and costs when the same prompt content is used repeatedly. Instead of re-processing the same text on every request, Bedrock caches it and reuses the computed result.

**Benefits:**
- Up to 90% cost reduction on cached tokens
- Up to 85% latency reduction
- 5-minute cache TTL (resets on each cache hit)

### How It Works

Bedrock uses "cache checkpoints" - markers you place in your request to indicate what should be cached:

```json
{
  "system": [
    {"text": "You are a helpful assistant..."},
    {"cachePoint": {"type": "default"}}
  ],
  "messages": [...]
}
```

Everything **before** the `cachePoint` gets cached. Content **after** the checkpoint is processed fresh each time.

### Why This Matters for DCAF

DCAF agents typically have:
- **Static system prompts** (instructions that don't change) - CACHEABLE ✅
- **Static tool definitions** (same tools every request) - CACHEABLE ✅  
- **Dynamic context** (tenant, user, namespace) - NOT cacheable ❌
- **User messages** (different each turn) - NOT cacheable ❌

By caching the static parts, we can make agents faster and cheaper to run.

---

## Requirements

### Functional Requirements

1. **FR-1**: Developers can enable prompt caching on an Agent with a simple flag
2. **FR-2**: Developers can provide a static system prompt (cached) and dynamic context (not cached)
3. **FR-3**: DCAF combines static and dynamic parts with a cache checkpoint between them
4. **FR-4**: Caching works with AWS Bedrock Claude models (3.5 Haiku, 3.7 Sonnet, etc.)
5. **FR-5**: Existing agents without caching continue to work unchanged (backward compatible)

### Non-Functional Requirements

1. **NFR-1**: No breaking changes to existing Agent API
2. **NFR-2**: Clear error messages if caching is misconfigured
3. **NFR-3**: Logging of cache-related information for debugging

---

## API Design

### Basic Usage (Simple Flag)

```python
from dcaf.core import Agent

agent = Agent(
    system="You are a Kubernetes expert...",  # This gets cached
    tools=[list_pods, delete_pod],
    cache=True,  # Enable caching
)
```

### Advanced Usage (Static + Dynamic)

```python
from dcaf.core import Agent

agent = Agent(
    # Static part - gets cached
    system="You are a Kubernetes expert. Your job is to help users manage their clusters...",
    
    # Dynamic part - appended AFTER cache checkpoint (not cached)
    system_context="Current tenant: acme-corp\nNamespace: production",
    
    tools=[list_pods, delete_pod],
    cache=True,
)
```

### With Callable Context (Most Flexible)

```python
from dcaf.core import Agent

def build_context(platform_context: dict) -> str:
    return f"""
    Tenant: {platform_context.get('tenant_name', 'unknown')}
    Namespace: {platform_context.get('k8s_namespace', 'default')}
    User: {platform_context.get('user_email', 'anonymous')}
    """

agent = Agent(
    system="You are a Kubernetes expert...",
    system_context=build_context,  # Called at runtime with platform_context
    tools=[list_pods, delete_pod],
    cache=True,
)
```

---

## Implementation Tasks

### Task 1: Create CacheConfig Class

**File**: `dcaf/core/domain/value_objects/cache_config.py` (new file)

**Purpose**: Define the configuration options for caching.

```python
"""Cache configuration for Bedrock prompt caching."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CacheConfig:
    """
    Configuration for AWS Bedrock prompt caching.
    
    Prompt caching reduces latency and cost by caching static portions
    of your prompts. Cached content must meet minimum token requirements
    (varies by model, typically 1024-2048 tokens).
    
    Attributes:
        enabled: Whether caching is enabled
        system_prompt: Whether to cache the system prompt
        tools: Whether to cache tool definitions (future enhancement)
        
    Example:
        # Simple: just enable with defaults
        cache=True
        
        # Explicit configuration
        cache=CacheConfig(system_prompt=True, tools=True)
    """
    
    enabled: bool = True
    system_prompt: bool = True
    tools: bool = False  # Future enhancement
    
    @classmethod
    def from_value(cls, value) -> Optional["CacheConfig"]:
        """
        Create CacheConfig from various input types.
        
        Args:
            value: Can be:
                - None: Returns None (caching disabled)
                - False: Returns None (caching disabled)
                - True: Returns default CacheConfig
                - CacheConfig: Returns as-is
                
        Returns:
            CacheConfig or None
            
        Example:
            CacheConfig.from_value(True)  # Returns CacheConfig(enabled=True, ...)
            CacheConfig.from_value(False)  # Returns None
        """
        if value is None or value is False:
            return None
        if value is True:
            return cls()
        if isinstance(value, cls):
            return value
        raise TypeError(
            f"cache must be bool or CacheConfig, got {type(value).__name__}"
        )
```

**Acceptance Criteria**:
- [ ] `CacheConfig.from_value(True)` returns a default CacheConfig
- [ ] `CacheConfig.from_value(False)` returns None
- [ ] `CacheConfig.from_value(None)` returns None
- [ ] `CacheConfig.from_value(CacheConfig(...))` returns the same instance
- [ ] Invalid types raise TypeError with clear message

---

### Task 2: Update Agent Class to Accept Cache Parameters

**File**: `dcaf/core/agent.py`

**Purpose**: Add `cache` and `system_context` parameters to the Agent class.

**Changes Required**:

1. **Add imports** at top of file:
```python
from dcaf.core.domain.value_objects.cache_config import CacheConfig
from typing import Union, Callable
```

2. **Update Agent.__init__** signature to add new parameters:
```python
def __init__(
    self,
    # ... existing parameters ...
    system: Optional[str] = None,
    
    # NEW PARAMETERS:
    system_context: Optional[Union[str, Callable[[dict], str]]] = None,
    cache: Optional[Union[bool, CacheConfig]] = None,
    
    # ... rest of existing parameters ...
):
```

3. **Add docstring for new parameters**:
```python
"""
Args:
    system: Static system prompt/instructions. When caching is enabled,
            this content is cached for reuse across requests.
            
    system_context: Dynamic context appended to system prompt. Can be:
            - A string: Used as-is
            - A callable: Called with platform_context dict, returns string
            This content is NOT cached and is evaluated fresh each request.
            
    cache: Enable Bedrock prompt caching. Can be:
            - True: Enable with default settings
            - False/None: Disable caching
            - CacheConfig: Custom cache configuration
"""
```

4. **Store the new attributes**:
```python
self._system = system
self._system_context = system_context
self._cache_config = CacheConfig.from_value(cache)
```

5. **Add a method to build the complete system prompt**:
```python
def _build_system_prompt(self, platform_context: Optional[dict] = None) -> str:
    """
    Build the complete system prompt from static and dynamic parts.
    
    Args:
        platform_context: Runtime context (tenant, namespace, etc.)
        
    Returns:
        Complete system prompt string
    """
    parts = []
    
    # Add static system prompt
    if self._system:
        parts.append(self._system)
    
    # Add dynamic context
    if self._system_context:
        if callable(self._system_context):
            # Call the function with platform_context
            context = self._system_context(platform_context or {})
        else:
            # Use the string directly (could add template formatting here)
            context = self._system_context
        
        if context:
            parts.append(context)
    
    return "\n\n".join(parts)
```

6. **Add properties for external access**:
```python
@property
def cache_config(self) -> Optional[CacheConfig]:
    """Get the cache configuration."""
    return self._cache_config

@property
def has_caching_enabled(self) -> bool:
    """Check if caching is enabled."""
    return self._cache_config is not None and self._cache_config.enabled
```

**Acceptance Criteria**:
- [ ] `Agent(system="...", cache=True)` creates an agent with caching enabled
- [ ] `Agent(system="...", cache=False)` creates an agent with caching disabled
- [ ] `Agent(system="...", system_context="...")` stores both parts
- [ ] `Agent(system="...", system_context=lambda ctx: "...")` accepts callable
- [ ] `agent.has_caching_enabled` returns correct boolean
- [ ] `agent._build_system_prompt({})` combines static and dynamic parts
- [ ] Existing agents without `cache` parameter continue to work

---

### Task 3: Create CachingAwsBedrock Model Class

**File**: `dcaf/core/adapters/outbound/agno/caching_bedrock.py` (new file)

**Purpose**: Extend Agno's AwsBedrock to add cache checkpoints to requests.

```python
"""
AWS Bedrock model with prompt caching support.

This module extends Agno's AwsBedrock class to add cache checkpoints
to system prompts, enabling Bedrock's prompt caching feature.
"""

from typing import Any, Dict, List, Optional, Tuple
import logging

from agno.models.aws import AwsBedrock
from agno.models.message import Message

logger = logging.getLogger(__name__)


class CachingAwsBedrock(AwsBedrock):
    """
    AWS Bedrock model with prompt caching support.
    
    This class extends AwsBedrock to add cache checkpoints to the system
    prompt, enabling Bedrock's prompt caching feature for reduced latency
    and cost.
    
    The cache checkpoint is placed AFTER the static system prompt content,
    so that the static portion is cached and any dynamic content appended
    afterward is processed fresh.
    
    Attributes:
        cache_system_prompt: Whether to add cache checkpoint to system prompt
        
    Example:
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
        )
    """
    
    # Minimum tokens required for caching (varies by model)
    # Claude 3.7 Sonnet: 1024, Claude 3.5 Haiku: 2048
    MIN_CACHE_TOKENS = 1024
    
    def __init__(
        self,
        cache_system_prompt: bool = False,
        **kwargs: Any,
    ) -> None:
        """
        Initialize the caching Bedrock model.
        
        Args:
            cache_system_prompt: Whether to add cache checkpoint to system prompt
            **kwargs: Passed to parent AwsBedrock class
        """
        super().__init__(**kwargs)
        self._cache_system_prompt = cache_system_prompt
        
        if cache_system_prompt:
            logger.info(
                f"CachingAwsBedrock: Prompt caching enabled for model {self.id}"
            )
    
    def _format_messages(
        self, 
        messages: List[Message], 
        compress_tool_results: bool = False
    ) -> Tuple[List[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
        """
        Format messages for the request, adding cache checkpoints.
        
        This overrides the parent method to add a cachePoint to the
        system message when caching is enabled.
        
        Args:
            messages: List of messages to format
            compress_tool_results: Whether to compress tool results
            
        Returns:
            Tuple of (formatted_messages, system_message_with_cache)
        """
        # Get the base formatted messages from parent
        formatted_messages, system_message = super()._format_messages(
            messages, compress_tool_results
        )
        
        # Add cache checkpoint to system message if enabled
        if self._cache_system_prompt and system_message:
            system_message = self._add_cache_checkpoint(system_message)
        
        return formatted_messages, system_message
    
    def _add_cache_checkpoint(
        self, 
        system_message: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Add a cache checkpoint to the system message.
        
        The checkpoint is added after the text content, marking everything
        before it as cacheable.
        
        Args:
            system_message: The system message content blocks
            
        Returns:
            System message with cache checkpoint appended
            
        Example:
            Input:  [{"text": "You are a helpful assistant..."}]
            Output: [{"text": "You are a helpful assistant..."}, 
                     {"cachePoint": {"type": "default"}}]
        """
        # Create a copy to avoid mutating the original
        cached_system = list(system_message)
        
        # Add the cache checkpoint at the end
        cached_system.append({
            "cachePoint": {
                "type": "default"
            }
        })
        
        logger.debug(
            f"Added cache checkpoint to system message "
            f"({len(system_message)} content blocks)"
        )
        
        return cached_system


def create_caching_model(
    model_id: str,
    cache_system_prompt: bool = False,
    **kwargs: Any,
) -> AwsBedrock:
    """
    Factory function to create a Bedrock model with optional caching.
    
    Args:
        model_id: The Bedrock model ID
        cache_system_prompt: Whether to enable system prompt caching
        **kwargs: Additional arguments for the model
        
    Returns:
        AwsBedrock or CachingAwsBedrock instance
    """
    if cache_system_prompt:
        return CachingAwsBedrock(
            id=model_id,
            cache_system_prompt=True,
            **kwargs,
        )
    else:
        return AwsBedrock(id=model_id, **kwargs)
```

**Acceptance Criteria**:
- [ ] `CachingAwsBedrock` extends `AwsBedrock` without breaking existing functionality
- [ ] When `cache_system_prompt=True`, system message includes `cachePoint`
- [ ] When `cache_system_prompt=False`, system message is unchanged
- [ ] Cache checkpoint is added at the END of system message content
- [ ] Original system message is not mutated (copy is made)
- [ ] Logging indicates when caching is enabled

---

### Task 4: Update AgnoAdapter to Use Caching

**File**: `dcaf/core/adapters/outbound/agno/adapter.py`

**Purpose**: Modify the adapter to use CachingAwsBedrock when caching is enabled.

**Changes Required**:

1. **Add import** at top of file:
```python
from .caching_bedrock import CachingAwsBedrock, create_caching_model
```

2. **Update `__init__`** to accept cache configuration:
```python
def __init__(
    self,
    # ... existing parameters ...
    
    # NEW PARAMETER:
    cache_system_prompt: bool = False,
    
    # ... rest of parameters ...
):
    # ... existing init code ...
    
    # Store cache setting
    self._cache_system_prompt = cache_system_prompt
```

3. **Update `_create_bedrock_model_async`** to use caching model:
```python
async def _create_bedrock_model_async(self):
    """Create an AWS Bedrock model with async session."""
    import aioboto3
    
    # ... existing session setup code ...
    
    # Create the model (with or without caching)
    logger.info(
        f"Agno: Initialized Bedrock model {self._model_id} "
        f"(temperature={self._temperature}, max_tokens={self._max_tokens}, "
        f"cache_system_prompt={self._cache_system_prompt})"
    )
    
    if self._cache_system_prompt:
        return CachingAwsBedrock(
            id=self._model_id,
            aws_region=region,
            async_session=async_session,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            cache_system_prompt=True,
        )
    else:
        return AwsBedrock(
            id=self._model_id,
            aws_region=region,
            async_session=async_session,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
```

**Acceptance Criteria**:
- [ ] `AgnoAdapter(cache_system_prompt=True)` uses `CachingAwsBedrock`
- [ ] `AgnoAdapter(cache_system_prompt=False)` uses regular `AwsBedrock`
- [ ] Logging shows whether caching is enabled
- [ ] All existing tests continue to pass

---

### Task 5: Wire Up Agent to Adapter

**File**: `dcaf/core/agent.py` (or wherever Agent creates the adapter)

**Purpose**: Pass cache configuration from Agent to AgnoAdapter.

Find where the Agent creates or configures the AgnoAdapter and update it to pass the cache setting:

```python
# When creating the adapter
adapter = AgnoAdapter(
    model_id=self._model_id,
    provider="bedrock",
    # ... other params ...
    cache_system_prompt=self.has_caching_enabled,
)
```

**Acceptance Criteria**:
- [ ] Agent with `cache=True` creates adapter with `cache_system_prompt=True`
- [ ] Agent without cache setting creates adapter with `cache_system_prompt=False`

---

### Task 6: Handle Static + Dynamic System Prompt

**File**: `dcaf/core/adapters/outbound/agno/caching_bedrock.py`

**Purpose**: Support separate static (cached) and dynamic (not cached) system prompt parts.

**Update the model to accept both parts**:

```python
class CachingAwsBedrock(AwsBedrock):
    
    def __init__(
        self,
        cache_system_prompt: bool = False,
        static_system: Optional[str] = None,   # Cached part
        dynamic_system: Optional[str] = None,  # Not cached part
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._cache_system_prompt = cache_system_prompt
        self._static_system = static_system
        self._dynamic_system = dynamic_system
    
    def _format_messages(
        self, 
        messages: List[Message], 
        compress_tool_results: bool = False
    ) -> Tuple[List[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
        """Format messages with static/dynamic system prompt handling."""
        
        formatted_messages, system_message = super()._format_messages(
            messages, compress_tool_results
        )
        
        # If we have static/dynamic parts, build the system message ourselves
        if self._static_system or self._dynamic_system:
            system_message = self._build_cached_system_message()
        elif self._cache_system_prompt and system_message:
            # Just add checkpoint to existing system message
            system_message = self._add_cache_checkpoint(system_message)
        
        return formatted_messages, system_message
    
    def _build_cached_system_message(self) -> List[Dict[str, Any]]:
        """
        Build system message with cache checkpoint between static and dynamic parts.
        
        Structure:
        [
            {"text": "static content..."},
            {"cachePoint": {"type": "default"}},
            {"text": "dynamic content..."}
        ]
        """
        parts = []
        
        # Add static part
        if self._static_system:
            parts.append({"text": self._static_system})
        
        # Add cache checkpoint (only if we have static content to cache)
        if self._static_system and self._cache_system_prompt:
            parts.append({"cachePoint": {"type": "default"}})
        
        # Add dynamic part
        if self._dynamic_system:
            parts.append({"text": self._dynamic_system})
        
        return parts if parts else None
```

**Acceptance Criteria**:
- [ ] Static + dynamic parts are correctly combined
- [ ] Cache checkpoint is placed BETWEEN static and dynamic parts
- [ ] If only static part exists, checkpoint is at the end
- [ ] If only dynamic part exists, no checkpoint is added
- [ ] Empty parts are handled gracefully

---

### Task 7: Add Unit Tests

**File**: `tests/test_prompt_caching.py` (new file)

```python
"""Tests for Bedrock prompt caching functionality."""

import pytest
from dcaf.core.domain.value_objects.cache_config import CacheConfig
from dcaf.core.adapters.outbound.agno.caching_bedrock import CachingAwsBedrock


class TestCacheConfig:
    """Tests for CacheConfig class."""
    
    def test_from_value_true(self):
        """True returns default CacheConfig."""
        config = CacheConfig.from_value(True)
        assert config is not None
        assert config.enabled is True
        assert config.system_prompt is True
    
    def test_from_value_false(self):
        """False returns None."""
        config = CacheConfig.from_value(False)
        assert config is None
    
    def test_from_value_none(self):
        """None returns None."""
        config = CacheConfig.from_value(None)
        assert config is None
    
    def test_from_value_config_instance(self):
        """CacheConfig instance is returned as-is."""
        original = CacheConfig(enabled=True, system_prompt=False)
        config = CacheConfig.from_value(original)
        assert config is original
    
    def test_from_value_invalid_type(self):
        """Invalid type raises TypeError."""
        with pytest.raises(TypeError, match="cache must be bool or CacheConfig"):
            CacheConfig.from_value("invalid")


class TestCachingAwsBedrock:
    """Tests for CachingAwsBedrock class."""
    
    def test_add_cache_checkpoint(self):
        """Cache checkpoint is added to system message."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
        )
        
        system_message = [{"text": "You are a helpful assistant."}]
        result = model._add_cache_checkpoint(system_message)
        
        assert len(result) == 2
        assert result[0] == {"text": "You are a helpful assistant."}
        assert result[1] == {"cachePoint": {"type": "default"}}
    
    def test_add_cache_checkpoint_does_not_mutate_original(self):
        """Original system message is not modified."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
        )
        
        original = [{"text": "You are a helpful assistant."}]
        original_copy = list(original)
        
        model._add_cache_checkpoint(original)
        
        assert original == original_copy  # Original unchanged
    
    def test_build_cached_system_message_static_only(self):
        """Static-only system message has checkpoint at end."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
            static_system="Static instructions here.",
        )
        
        result = model._build_cached_system_message()
        
        assert len(result) == 2
        assert result[0] == {"text": "Static instructions here."}
        assert result[1] == {"cachePoint": {"type": "default"}}
    
    def test_build_cached_system_message_static_and_dynamic(self):
        """Static + dynamic has checkpoint between them."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
            static_system="Static instructions.",
            dynamic_system="Dynamic context.",
        )
        
        result = model._build_cached_system_message()
        
        assert len(result) == 3
        assert result[0] == {"text": "Static instructions."}
        assert result[1] == {"cachePoint": {"type": "default"}}
        assert result[2] == {"text": "Dynamic context."}
    
    def test_build_cached_system_message_dynamic_only(self):
        """Dynamic-only system message has no checkpoint."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
            dynamic_system="Dynamic context only.",
        )
        
        result = model._build_cached_system_message()
        
        assert len(result) == 1
        assert result[0] == {"text": "Dynamic context only."}
        # No cache checkpoint - nothing static to cache


class TestAgentWithCaching:
    """Tests for Agent class with caching enabled."""
    
    def test_agent_cache_true(self):
        """Agent with cache=True has caching enabled."""
        from dcaf.core import Agent
        
        agent = Agent(
            system="Test prompt",
            cache=True,
        )
        
        assert agent.has_caching_enabled is True
    
    def test_agent_cache_false(self):
        """Agent with cache=False has caching disabled."""
        from dcaf.core import Agent
        
        agent = Agent(
            system="Test prompt",
            cache=False,
        )
        
        assert agent.has_caching_enabled is False
    
    def test_agent_no_cache_param(self):
        """Agent without cache param has caching disabled."""
        from dcaf.core import Agent
        
        agent = Agent(system="Test prompt")
        
        assert agent.has_caching_enabled is False
    
    def test_agent_build_system_prompt_static_only(self):
        """Build system prompt with static content only."""
        from dcaf.core import Agent
        
        agent = Agent(system="Static instructions")
        
        result = agent._build_system_prompt({})
        assert result == "Static instructions"
    
    def test_agent_build_system_prompt_with_context_string(self):
        """Build system prompt with static + string context."""
        from dcaf.core import Agent
        
        agent = Agent(
            system="Static instructions",
            system_context="Dynamic context",
        )
        
        result = agent._build_system_prompt({})
        assert "Static instructions" in result
        assert "Dynamic context" in result
    
    def test_agent_build_system_prompt_with_context_callable(self):
        """Build system prompt with static + callable context."""
        from dcaf.core import Agent
        
        agent = Agent(
            system="Static instructions",
            system_context=lambda ctx: f"Tenant: {ctx.get('tenant', 'unknown')}",
        )
        
        result = agent._build_system_prompt({"tenant": "acme"})
        assert "Static instructions" in result
        assert "Tenant: acme" in result
```

**Acceptance Criteria**:
- [ ] All tests pass
- [ ] Tests cover CacheConfig creation
- [ ] Tests cover cache checkpoint placement
- [ ] Tests cover static + dynamic prompt building
- [ ] Tests verify original data is not mutated

---

### Task 8: Update Documentation

**File**: `docs/guides/prompt-caching.md` (new file)

Create a user guide explaining:
1. What prompt caching is
2. When to use it
3. How to enable it
4. Static vs dynamic prompts
5. Troubleshooting tips

**File**: `docs/api-reference/agent.md`

Update to document the new parameters:
- `cache`: Enable/disable caching
- `system_context`: Dynamic system prompt context

---

### Task 9: Export New Classes

**File**: `dcaf/core/__init__.py`

Add exports for new public classes:

```python
from .domain.value_objects.cache_config import CacheConfig

__all__ = [
    # ... existing exports ...
    "CacheConfig",
]
```

---

## Testing Strategy

### Unit Tests
- CacheConfig creation and validation
- Cache checkpoint placement in system messages
- Static + dynamic prompt combination
- Agent parameter handling

### Integration Tests
- End-to-end test with mock Bedrock client
- Verify cache checkpoint appears in actual request

### Manual Testing
1. Create an agent with `cache=True`
2. Make a request and check logs for cache info
3. Verify the Bedrock request includes `cachePoint`

---

## Rollout Plan

1. **Phase 1**: Implement CacheConfig and Agent parameter changes
2. **Phase 2**: Implement CachingAwsBedrock model
3. **Phase 3**: Wire up Agent → Adapter → Model
4. **Phase 4**: Add tests
5. **Phase 5**: Documentation
6. **Phase 6**: Code review and merge

---

## Success Criteria

- [ ] `Agent(cache=True)` enables caching with no other changes required
- [ ] `Agent(system="...", system_context="...")` correctly separates cached/uncached content
- [ ] Bedrock requests include `cachePoint` when caching is enabled
- [ ] All existing tests pass (no regressions)
- [ ] New tests cover caching functionality
- [ ] Documentation is clear for new users

---

## Questions for Tech Lead

1. Should we log cache hit/miss metrics from Bedrock responses?
2. Should we warn if system prompt is below minimum token count?
3. Should we support tool definition caching in v1 or defer to v2?

---

## Resources

- [AWS Bedrock Prompt Caching Docs](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html)
- [Agno AwsBedrock Source](https://github.com/agno-agi/agno/blob/main/agno/models/aws/bedrock.py)
- [DCAF AgnoAdapter](dcaf/core/adapters/outbound/agno/adapter.py)

