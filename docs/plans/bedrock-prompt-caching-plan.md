# Bedrock Prompt Caching Implementation Plan (Revised)

## Overview

**Feature**: Add AWS Bedrock prompt caching support to DCAF agents  
**Priority**: Performance optimization  
**Estimated Effort**: 3-4 days (including testing and examples)  
**Target Engineer Level**: Junior  
**Status**: Experimental (v1) - Temporary implementation until Agno adds native support

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

### Important Note

**This is a temporary implementation.** Agno is expected to add native prompt caching support in a future release. Once that's available, we'll remove this custom implementation and use Agno's built-in support.

---

## Requirements

### Functional Requirements

1. **FR-1**: Developers can enable prompt caching on an Agent via `model_config`
2. **FR-2**: Developers can provide a static system prompt (cached) and dynamic context (not cached)
3. **FR-3**: DCAF places a cache checkpoint between static and dynamic parts
4. **FR-4**: Caching works with AWS Bedrock Claude models (3.5 Haiku, 3.7 Sonnet, etc.)
5. **FR-5**: Existing agents without caching continue to work unchanged (backward compatible)
6. **FR-6**: Cache performance metrics are logged when available

### Non-Functional Requirements

1. **NFR-1**: No breaking changes to existing Agent API
2. **NFR-2**: Clear error messages if caching is misconfigured
3. **NFR-3**: Extensive logging of cache-related information for debugging
4. **NFR-4**: All caching logic stays within adapter implementation (not exposed in public API)

---

## API Design

### Basic Usage (Simple Flag)

```python
from dcaf.core import Agent

agent = Agent(
    system="You are a Kubernetes expert...",  # This gets cached
    tools=[list_pods, delete_pod],
    model_config={
        "cache_system_prompt": True  # Enable caching
    }
)
```

### Separating Static and Dynamic Prompts

This is the **key pattern** for effective caching:

```python
from dcaf.core import Agent

agent = Agent(
    # Static part - gets cached (same for every request)
    system="You are a Kubernetes expert. Your job is to help users manage their clusters...",
    
    # Dynamic part - NOT cached (changes per request)
    system_context=lambda ctx: f"""
    Current tenant: {ctx.get('tenant_name', 'unknown')}
    Namespace: {ctx.get('k8s_namespace', 'default')}
    User: {ctx.get('user_email', 'anonymous')}
    """,
    
    tools=[list_pods, delete_pod],
    model_config={
        "cache_system_prompt": True
    }
)
```

**Why separate them?**
- Even without caching, this is good design (separates static instructions from runtime context)
- With caching, DCAF places a cache checkpoint between them automatically
- Works gracefully with non-caching providers (they just concatenate)

### How platform_context Flows

```python
# User request includes platform_context
{
  "messages": [...],
  "platform_context": {
    "tenant_name": "acme-corp",
    "k8s_namespace": "production"
  }
}

# Agent receives it and passes to system_context callable
result = agent.run(messages, context=platform_context)

# system_context function is called with platform_context
# Result is appended AFTER cache checkpoint
```

---

## Implementation Tasks

### Task 1: Update Agent Class to Accept system_context

**File**: `dcaf/core/agent.py`

**Purpose**: Add `system_context` parameter to separate static and dynamic prompt parts.

**Changes Required**:

1. **Add import** at top of file:
```python
from typing import Union, Callable
```

2. **Update Agent.__init__** signature:
```python
def __init__(
    self,
    # ... existing parameters ...
    system: Optional[str] = None,
    
    # NEW PARAMETER:
    system_context: Optional[Union[str, Callable[[dict], str]]] = None,
    
    # ... rest of existing parameters ...
    model_config: Optional[dict] = None,  # Ensure this exists
):
```

3. **Add docstring for new parameter**:
```python
"""
Args:
    system: Static system prompt/instructions. When caching is enabled,
            this content is cached for reuse across requests.
            
    system_context: Dynamic context appended to system prompt. Can be:
            - A string: Used as-is
            - A callable: Called with platform_context dict, returns string
            This content is NOT cached and is evaluated fresh each request.
            
    model_config: Configuration passed to the model adapter. For caching:
            {"cache_system_prompt": True}
"""
```

4. **Store the attributes**:
```python
self._system = system
self._system_context = system_context
self._model_config = model_config or {}
```

5. **Add method to build system prompt parts separately**:
```python
def _build_system_parts(self, platform_context: Optional[dict] = None) -> tuple[Optional[str], Optional[str]]:
    """
    Build static and dynamic system prompt parts separately.
    
    This separation is useful even without caching - it keeps static
    instructions separate from runtime context. When caching is enabled,
    adapters can place a cache checkpoint between these parts.
    
    Args:
        platform_context: Runtime context (tenant, namespace, etc.)
        
    Returns:
        (static_part, dynamic_part) where either can be None
    """
    static = self._system
    
    dynamic = None
    if self._system_context:
        if callable(self._system_context):
            # Call the function with platform_context
            dynamic = self._system_context(platform_context or {})
        else:
            # Use the string directly
            dynamic = self._system_context
    
    return static, dynamic
```

6. **Update the agent execution flow** to pass system parts to adapter:

Find the method where the agent invokes the runtime (likely `run()` or similar) and update it to pass the system parts:

```python
def run(self, messages: list, context: dict = None) -> AgentResult:
    """Execute the agent with the given messages."""
    platform_context = context or {}
    
    # Build system prompt parts
    static_system, dynamic_system = self._build_system_parts(platform_context)
    
    # Pass to adapter with both parts
    response = self._runtime.invoke(
        messages=messages,
        static_system=static_system,
        dynamic_system=dynamic_system,
        tools=self._tools,
        # ... other params
    )
    
    return response
```

**Note**: The exact location will depend on current Agent implementation. Look for where `self._runtime` or the adapter is called.

**Acceptance Criteria**:
- [ ] `Agent(system="...", system_context="...")` stores both parts
- [ ] `Agent(system="...", system_context=lambda ctx: "...")` accepts callable
- [ ] `agent._build_system_parts({})` returns tuple of (static, dynamic)
- [ ] Callable context receives platform_context dict
- [ ] Existing agents without `system_context` continue to work
- [ ] `model_config` is stored and accessible

---

### Task 2: Create CachingAwsBedrock Model Class

**File**: `dcaf/core/adapters/outbound/agno/caching_bedrock.py` (new file)

**Purpose**: Extend Agno's AwsBedrock to add cache checkpoints to requests.

**Important**: This is a **temporary workaround** until Agno adds native caching support. Once Agno implements caching, we'll remove this class and use their implementation.

```python
"""
AWS Bedrock model with prompt caching support.

TEMPORARY IMPLEMENTATION: This module extends Agno's AwsBedrock class to add 
cache checkpoints to system prompts. This is a workaround until Agno adds 
native prompt caching support (expected in future release).

Once Agno supports caching natively, this module should be removed.
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
    
    TEMPORARY: Remove once Agno adds native caching support.
    
    Attributes:
        cache_system_prompt: Whether to add cache checkpoint to system prompt
        static_system: Static portion of system prompt (cached)
        dynamic_system: Dynamic portion of system prompt (not cached)
        
    Example:
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
            static_system="You are a helpful assistant...",
            dynamic_system="Tenant: acme-corp",
        )
    """
    
    # Minimum tokens required for caching (varies by model)
    # Claude 3.7 Sonnet: 1024, Claude 3.5 Haiku: 2048
    MIN_CACHE_TOKENS = 1024
    
    def __init__(
        self,
        cache_system_prompt: bool = False,
        static_system: Optional[str] = None,
        dynamic_system: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize the caching Bedrock model.
        
        Args:
            cache_system_prompt: Whether to add cache checkpoint to system prompt
            static_system: Static portion (cached)
            dynamic_system: Dynamic portion (not cached)
            **kwargs: Passed to parent AwsBedrock class
        """
        super().__init__(**kwargs)
        self._cache_system_prompt = cache_system_prompt
        self._static_system = static_system
        self._dynamic_system = dynamic_system
        
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
        
        Note: This override may be fragile if Agno updates their implementation.
        Last verified compatible with: agno==0.6.x
        
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
        
        # If we have static/dynamic parts, build custom system message
        if self._static_system or self._dynamic_system:
            system_message = self._build_cached_system_message()
        elif self._cache_system_prompt and system_message:
            # Just add checkpoint to existing system message
            system_message = self._add_cache_checkpoint(system_message)
        
        return formatted_messages, system_message
    
    def _build_cached_system_message(self) -> Optional[List[Dict[str, Any]]]:
        """
        Build system message with cache checkpoint between static and dynamic parts.
        
        Structure:
        [
            {"text": "static content..."},
            {"cachePoint": {"type": "default"}},  # ← Cache everything above
            {"text": "dynamic content..."}
        ]
        
        Returns:
            System message content blocks, or None if no content
        """
        parts = []
        
        # Add static part
        if self._static_system:
            # Check if it meets minimum token threshold
            if self._cache_system_prompt and not self._check_token_threshold(self._static_system):
                logger.warning(
                    "Static system prompt below minimum token threshold for caching. "
                    "Caching disabled for this request."
                )
                # Disable caching for this request, just concatenate
                combined = "\n\n".join([p for p in [self._static_system, self._dynamic_system] if p])
                return [{"text": combined}] if combined else None
            
            parts.append({"text": self._static_system})
        
        # Add cache checkpoint (only if we have static content to cache)
        if self._static_system and self._cache_system_prompt:
            parts.append({"cachePoint": {"type": "default"}})
            logger.debug(
                f"Added cache checkpoint after static system prompt "
                f"(~{len(self._static_system)//4} tokens)"
            )
        
        # Add dynamic part
        if self._dynamic_system:
            parts.append({"text": self._dynamic_system})
            logger.debug(
                f"Added dynamic system context "
                f"(~{len(self._dynamic_system)//4} tokens)"
            )
        
        return parts if parts else None
    
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
    
    def _check_token_threshold(self, text: str) -> bool:
        """
        Check if text meets minimum caching threshold.
        
        Args:
            text: The text to check
            
        Returns:
            True if text is long enough to cache, False otherwise
        """
        # Rough estimate: 4 chars ≈ 1 token
        estimated_tokens = len(text) // 4
        
        if estimated_tokens < self.MIN_CACHE_TOKENS:
            logger.warning(
                f"System prompt (~{estimated_tokens} tokens) below minimum "
                f"threshold ({self.MIN_CACHE_TOKENS} tokens). "
                f"Consider longer instructions or disable caching."
            )
            return False
        
        logger.info(
            f"System prompt (~{estimated_tokens} tokens) meets caching threshold"
        )
        return True
    
    def _log_cache_metrics(self, response: Dict[str, Any]) -> None:
        """
        Log cache performance metrics from Bedrock response.
        
        Bedrock returns cache metrics in the response under 'usage':
        - cacheReadInputTokens: Tokens retrieved from cache (cache HIT)
        - cacheCreationInputTokens: Tokens cached for first time (cache MISS)
        
        Args:
            response: The Bedrock API response
        """
        usage = response.get("usage", {})
        cache_hit = usage.get("cacheReadInputTokens", 0)
        cache_miss = usage.get("cacheCreationInputTokens", 0)
        
        if cache_hit > 0:
            logger.info(
                f"✅ Cache HIT: {cache_hit} tokens reused "
                f"(~{cache_hit * 0.9:.0f}% cost reduction)"
            )
        elif cache_miss > 0:
            logger.info(
                f"📝 Cache MISS: {cache_miss} tokens cached for next request "
                f"(cache created)"
            )
        elif self._cache_system_prompt:
            logger.warning(
                "⚠️ Caching enabled but no cache metrics in response. "
                "Possible reasons: system prompt too short, caching not supported "
                "by this model, or Bedrock API change."
            )


# Note: We intentionally don't export a create_caching_model() factory
# to keep the public API simple. Adapter handles instantiation.
```

**Acceptance Criteria**:
- [ ] `CachingAwsBedrock` extends `AwsBedrock` without breaking existing functionality
- [ ] When `cache_system_prompt=True` and static_system provided, cache checkpoint is added
- [ ] Cache checkpoint is placed BETWEEN static and dynamic parts
- [ ] Original system message is not mutated (copy is made)
- [ ] Token threshold is checked before enabling caching
- [ ] Logging indicates when caching is enabled/disabled
- [ ] Cache metrics are logged when available in response

---

### Task 3: Update AgnoAdapter to Use Caching

**File**: `dcaf/core/adapters/outbound/agno/adapter.py`

**Purpose**: Modify the adapter to use CachingAwsBedrock when caching is enabled.

**Changes Required**:

1. **Add import** at top of file:
```python
from .caching_bedrock import CachingAwsBedrock
```

2. **Update the method that creates the Bedrock model** to check for caching config:

Find the method that creates the AwsBedrock instance (likely `_create_bedrock_model_async` or similar). Update it to conditionally use `CachingAwsBedrock`:

```python
async def _create_bedrock_model_async(self, static_system=None, dynamic_system=None):
    """
    Create an AWS Bedrock model with async session.
    
    Args:
        static_system: Static portion of system prompt (for caching)
        dynamic_system: Dynamic portion of system prompt (for caching)
    """
    import aioboto3
    
    # ... existing session setup code ...
    
    # Check if caching is enabled via model_config
    cache_enabled = self._model_config.get("cache_system_prompt", False)
    
    # Log configuration
    logger.info(
        f"Agno: Initialized Bedrock model {self._model_id} "
        f"(temperature={self._temperature}, max_tokens={self._max_tokens}, "
        f"cache_system_prompt={cache_enabled})"
    )
    
    # Create the appropriate model
    if cache_enabled:
        logger.info("Using CachingAwsBedrock (temporary until Agno adds native support)")
        return CachingAwsBedrock(
            id=self._model_id,
            aws_region=region,
            async_session=async_session,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            cache_system_prompt=True,
            static_system=static_system,
            dynamic_system=dynamic_system,
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

3. **Update the `invoke` method** to accept and pass through system parts:

```python
def invoke(
    self, 
    messages: List[Message],
    static_system: Optional[str] = None,
    dynamic_system: Optional[str] = None,
    **kwargs
) -> AgentResponse:
    """
    Invoke the model with messages.
    
    Args:
        messages: Conversation messages
        static_system: Static portion of system prompt (cached)
        dynamic_system: Dynamic portion of system prompt (not cached)
        **kwargs: Additional arguments
    """
    # If we need to recreate the model with new system parts
    # (for caching), do so here
    if static_system or dynamic_system:
        # Store for model creation
        self._static_system = static_system
        self._dynamic_system = dynamic_system
    
    # ... rest of invoke logic ...
```

**Note**: The exact implementation depends on how AgnoAdapter currently handles system prompts. You may need to:
- Store static/dynamic parts as instance variables
- Pass them when creating the model
- Or handle them in the message formatting step

**Acceptance Criteria**:
- [ ] `AgnoAdapter` with `model_config={"cache_system_prompt": True}` uses `CachingAwsBedrock`
- [ ] `AgnoAdapter` without cache config uses regular `AwsBedrock`
- [ ] Static and dynamic system parts are passed to the model
- [ ] Logging shows whether caching is enabled
- [ ] All existing tests continue to pass

---

### Task 4: Add Cache Metrics Logging to Response Handling

**File**: `dcaf/core/adapters/outbound/agno/caching_bedrock.py` (update)

**Purpose**: Extract and log cache metrics from Bedrock responses.

**Changes Required**:

In the `CachingAwsBedrock` class, find where Bedrock responses are processed and add cache metrics logging:

```python
# In whatever method processes the Bedrock response
def _process_response(self, response: Dict[str, Any]) -> Any:
    """Process Bedrock response."""
    
    # Log cache metrics if caching is enabled
    if self._cache_system_prompt:
        self._log_cache_metrics(response)
    
    # ... rest of response processing ...
```

**Note**: The exact location depends on Agno's response handling flow. Look for where the raw Bedrock API response is received.

If Agno doesn't expose the raw response with usage metrics, add a comment:

```python
# TODO: Cache metrics logging currently not available through Agno API
# Once Agno exposes usage metrics, add logging here
# Expected format: response['usage']['cacheReadInputTokens']
```

**Acceptance Criteria**:
- [ ] Cache HIT is logged when tokens are reused
- [ ] Cache MISS is logged when cache is created
- [ ] Warning is logged if caching is enabled but no metrics returned
- [ ] Logging includes token counts and cost savings estimate

---

### Task 5: Add Unit Tests

**File**: `tests/test_prompt_caching.py` (new file)

```python
"""Tests for Bedrock prompt caching functionality."""

import pytest
from dcaf.core.adapters.outbound.agno.caching_bedrock import CachingAwsBedrock


class TestCachingAwsBedrock:
    """Tests for CachingAwsBedrock class."""
    
    def test_build_cached_system_message_static_only(self):
        """Static-only system message has checkpoint at end."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
            static_system="Static instructions here." * 300,  # Make it long enough
        )
        
        result = model._build_cached_system_message()
        
        assert len(result) == 2
        assert result[0]["text"].startswith("Static instructions")
        assert result[1] == {"cachePoint": {"type": "default"}}
    
    def test_build_cached_system_message_static_and_dynamic(self):
        """Static + dynamic has checkpoint between them."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
            static_system="Static instructions." * 300,
            dynamic_system="Dynamic context.",
        )
        
        result = model._build_cached_system_message()
        
        assert len(result) == 3
        assert result[0]["text"].startswith("Static instructions")
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
    
    def test_add_cache_checkpoint(self):
        """Cache checkpoint is added to system message."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
        )
        
        system_message = [{"text": "You are a helpful assistant." * 300}]
        result = model._add_cache_checkpoint(system_message)
        
        assert len(result) == 2
        assert result[0]["text"].startswith("You are a helpful assistant")
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
    
    def test_check_token_threshold_below_minimum(self):
        """Short text below threshold returns False."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
        )
        
        short_text = "Too short"
        result = model._check_token_threshold(short_text)
        
        assert result is False
    
    def test_check_token_threshold_above_minimum(self):
        """Long text above threshold returns True."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
        )
        
        # Create text with ~2000 tokens (8000 chars)
        long_text = "This is a long system prompt. " * 270
        result = model._check_token_threshold(long_text)
        
        assert result is True
    
    def test_log_cache_metrics_cache_hit(self, caplog):
        """Cache HIT is logged correctly."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
        )
        
        response = {
            "usage": {
                "inputTokens": 100,
                "outputTokens": 50,
                "cacheReadInputTokens": 950,
            }
        }
        
        model._log_cache_metrics(response)
        
        assert "Cache HIT" in caplog.text
        assert "950 tokens" in caplog.text
    
    def test_log_cache_metrics_cache_miss(self, caplog):
        """Cache MISS is logged correctly."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
        )
        
        response = {
            "usage": {
                "inputTokens": 1000,
                "outputTokens": 50,
                "cacheCreationInputTokens": 950,
            }
        }
        
        model._log_cache_metrics(response)
        
        assert "Cache MISS" in caplog.text
        assert "950 tokens" in caplog.text


class TestAgentWithCaching:
    """Tests for Agent class with caching enabled."""
    
    def test_agent_build_system_parts_static_only(self):
        """Build system parts with static content only."""
        from dcaf.core import Agent
        
        agent = Agent(system="Static instructions")
        
        static, dynamic = agent._build_system_parts({})
        
        assert static == "Static instructions"
        assert dynamic is None
    
    def test_agent_build_system_parts_with_context_string(self):
        """Build system parts with static + string context."""
        from dcaf.core import Agent
        
        agent = Agent(
            system="Static instructions",
            system_context="Dynamic context",
        )
        
        static, dynamic = agent._build_system_parts({})
        
        assert static == "Static instructions"
        assert dynamic == "Dynamic context"
    
    def test_agent_build_system_parts_with_context_callable(self):
        """Build system parts with static + callable context."""
        from dcaf.core import Agent
        
        agent = Agent(
            system="Static instructions",
            system_context=lambda ctx: f"Tenant: {ctx.get('tenant', 'unknown')}",
        )
        
        static, dynamic = agent._build_system_parts({"tenant": "acme"})
        
        assert static == "Static instructions"
        assert dynamic == "Tenant: acme"
    
    def test_agent_with_model_config_caching(self):
        """Agent with cache in model_config."""
        from dcaf.core import Agent
        
        agent = Agent(
            system="Test prompt",
            model_config={"cache_system_prompt": True}
        )
        
        assert agent._model_config.get("cache_system_prompt") is True
    
    def test_agent_without_caching(self):
        """Agent without caching config."""
        from dcaf.core import Agent
        
        agent = Agent(system="Test prompt")
        
        assert agent._model_config.get("cache_system_prompt", False) is False
```

**Acceptance Criteria**:
- [ ] All tests pass
- [ ] Tests cover cache checkpoint placement
- [ ] Tests cover static + dynamic prompt building
- [ ] Tests verify original data is not mutated
- [ ] Tests verify token threshold checking
- [ ] Tests verify cache metrics logging

---

### Task 6: Create Example Application

**File**: `examples/prompt_caching_example.py` (new file)

```python
"""
Example: Using Bedrock Prompt Caching with DCAF

This example demonstrates how to use prompt caching to reduce costs and latency
when working with agents that have static instructions and dynamic context.
"""

from dcaf.core import Agent, tool
import logging

# Enable detailed logging to see cache metrics
logging.basicConfig(level=logging.INFO)

# Define some example tools
@tool(description="List all Kubernetes pods in a namespace")
def list_pods(namespace: str = "default") -> str:
    """List pods (simulated)."""
    return f"Pods in {namespace}: pod-1, pod-2, pod-3"

@tool(description="Get details about a specific pod")
def get_pod(name: str, namespace: str = "default") -> str:
    """Get pod details (simulated)."""
    return f"Pod {name} in {namespace}: Running, 2 containers"


# Example 1: Basic caching with static prompt only
def example_basic_caching():
    """Simple caching example with just a static prompt."""
    print("\n=== Example 1: Basic Caching ===\n")
    
    agent = Agent(
        system="""
        You are a Kubernetes expert assistant. Your role is to help users
        manage their Kubernetes clusters safely and efficiently.
        
        Guidelines:
        - Always verify namespace before operations
        - Explain what each command does
        - Ask for confirmation on destructive operations
        - Use kubectl best practices
        - Provide helpful error messages
        
        (Add more detailed instructions here to exceed 1024 tokens for caching)
        """ * 3,  # Repeat to exceed minimum token threshold
        
        tools=[list_pods, get_pod],
        
        model_config={
            "cache_system_prompt": True  # Enable caching
        }
    )
    
    # First request - cache MISS (creates cache)
    print("First request (cache MISS):")
    result1 = agent.run([{"role": "user", "content": "List pods"}])
    print(f"Response: {result1.text}\n")
    
    # Second request - cache HIT (reuses cache)
    print("Second request (cache HIT):")
    result2 = agent.run([{"role": "user", "content": "Get details for pod-1"}])
    print(f"Response: {result2.text}\n")
    
    print("Check logs above for cache HIT/MISS indicators")


# Example 2: Static instructions + dynamic context
def example_static_and_dynamic():
    """Caching with separated static and dynamic parts."""
    print("\n=== Example 2: Static + Dynamic Context ===\n")
    
    agent = Agent(
        # Static part - cached (same for all requests)
        system="""
        You are a Kubernetes expert assistant for a multi-tenant platform.
        
        Your responsibilities:
        - Help users manage pods, services, and deployments
        - Ensure operations are scoped to the correct tenant and namespace
        - Follow security best practices
        - Provide clear explanations
        
        Guidelines:
        - Always check tenant context before operations
        - Verify namespace matches tenant configuration
        - Ask for confirmation on destructive operations
        - Log all operations for audit trail
        
        (Add detailed instructions to exceed 1024 tokens)
        """ * 3,
        
        # Dynamic part - NOT cached (changes per request)
        system_context=lambda ctx: f"""
        === CURRENT CONTEXT ===
        Tenant: {ctx.get('tenant_name', 'unknown')}
        Namespace: {ctx.get('k8s_namespace', 'default')}
        User: {ctx.get('user_email', 'anonymous')}
        Environment: {ctx.get('environment', 'production')}
        
        You MUST scope all operations to the above context.
        """,
        
        tools=[list_pods, get_pod],
        
        model_config={
            "cache_system_prompt": True
        }
    )
    
    # Request 1: Tenant A
    print("Request for Tenant A:")
    context_a = {
        "tenant_name": "acme-corp",
        "k8s_namespace": "acme-prod",
        "user_email": "alice@acme.com",
        "environment": "production"
    }
    result1 = agent.run(
        [{"role": "user", "content": "List all pods"}],
        context=context_a
    )
    print(f"Response: {result1.text}\n")
    
    # Request 2: Tenant B (cache HIT for static, fresh dynamic)
    print("Request for Tenant B:")
    context_b = {
        "tenant_name": "widgets-inc",
        "k8s_namespace": "widgets-dev",
        "user_email": "bob@widgets.com",
        "environment": "development"
    }
    result2 = agent.run(
        [{"role": "user", "content": "Show pod-1 details"}],
        context=context_b
    )
    print(f"Response: {result2.text}\n")
    
    print("Static instructions are cached, dynamic context is fresh each time")


# Example 3: Cost comparison (conceptual)
def example_cost_comparison():
    """Show the cost impact of caching."""
    print("\n=== Example 3: Cost Impact ===\n")
    
    # Simulated token counts
    static_tokens = 1500  # Long system prompt
    dynamic_tokens = 100   # Short context
    
    print("Without caching:")
    print(f"  Per request: {static_tokens + dynamic_tokens} input tokens")
    print(f"  100 requests: {(static_tokens + dynamic_tokens) * 100} tokens")
    print(f"  Approx cost: ${((static_tokens + dynamic_tokens) * 100) * 0.000003:.4f}")
    
    print("\nWith caching:")
    print(f"  First request: {static_tokens + dynamic_tokens} tokens (cache MISS)")
    print(f"  Subsequent 99: {dynamic_tokens * 99} tokens (cache HIT)")
    print(f"  Total: {static_tokens + dynamic_tokens + (dynamic_tokens * 99)} tokens")
    print(f"  Approx cost: ${(static_tokens + dynamic_tokens + (dynamic_tokens * 99)) * 0.000003:.4f}")
    
    savings = 100 - ((static_tokens + dynamic_tokens + (dynamic_tokens * 99)) / 
                     ((static_tokens + dynamic_tokens) * 100) * 100)
    print(f"\n  Savings: ~{savings:.1f}%")


if __name__ == "__main__":
    print("Bedrock Prompt Caching Examples")
    print("=" * 50)
    
    # Run examples
    example_basic_caching()
    example_static_and_dynamic()
    example_cost_comparison()
    
    print("\n" + "=" * 50)
    print("Examples complete!")
    print("\nKey takeaways:")
    print("1. Enable caching with model_config={'cache_system_prompt': True}")
    print("2. Separate static (cached) and dynamic (fresh) content")
    print("3. Ensure static content exceeds 1024 tokens for best results")
    print("4. Monitor logs for cache HIT/MISS indicators")
```

**Acceptance Criteria**:
- [ ] Example runs without errors
- [ ] Shows basic caching usage
- [ ] Shows static/dynamic separation
- [ ] Demonstrates cost savings
- [ ] Includes helpful comments and explanations

---

### Task 7: Update Documentation

**File**: `docs/guides/prompt-caching.md` (new file)

```markdown
# Bedrock Prompt Caching Guide

## Overview

AWS Bedrock's prompt caching feature can reduce costs by up to 90% and latency by up to 85% for agents with static instructions and dynamic context.

**Status**: Experimental (v1) - Temporary implementation until Agno adds native support

## How It Works

When you enable caching, DCAF places a "cache checkpoint" in your system prompt. Everything before the checkpoint is cached by Bedrock for 5 minutes (TTL resets on each use).

```
[Static Instructions] ← CACHED
      ↓
[Cache Checkpoint]
      ↓
[Dynamic Context]     ← NOT cached (fresh each time)
```

## Quick Start

### Basic Usage

```python
from dcaf.core import Agent

agent = Agent(
    system="You are a Kubernetes expert... [long instructions]",
    tools=[list_pods, delete_pod],
    model_config={
        "cache_system_prompt": True
    }
)
```

### Separating Static and Dynamic Content

For maximum benefit, separate static instructions from dynamic context:

```python
agent = Agent(
    # Static - cached
    system="You are a Kubernetes expert...",
    
    # Dynamic - NOT cached
    system_context=lambda ctx: f"Tenant: {ctx['tenant']}\nNamespace: {ctx['namespace']}",
    
    model_config={
        "cache_system_prompt": True
    }
)
```

## Requirements

### Minimum Token Count

Your static system prompt must be at least:
- **Claude 3.7 Sonnet**: 1024 tokens
- **Claude 3.5 Haiku**: 2048 tokens

If below threshold, caching is automatically disabled with a warning log.

**Rule of thumb**: ~4 characters = 1 token, so aim for 4000+ character prompts.

## Best Practices

### 1. Put Static Content First

✅ **Good**: Static instructions, then dynamic context
```python
system="You are a K8s expert. [lengthy guidelines]"
system_context="Current tenant: acme-corp"
```

❌ **Bad**: Mixing static and dynamic
```python
system="You are a K8s expert for tenant: acme-corp. [guidelines]"
```

### 2. Make Static Content Detailed

The more static content you cache, the bigger the savings:

✅ **Good**: Detailed instructions (1500+ tokens)
```python
system="""
You are a Kubernetes expert assistant.

Guidelines:
- Always verify namespace before operations
- Explain commands clearly
- Ask for confirmation on destructive operations
- Follow kubectl best practices
- Provide helpful error messages

[More detailed guidelines...]
"""
```

❌ **Bad**: Brief instructions (50 tokens)
```python
system="You are a helpful Kubernetes assistant."
```

### 3. Use Callable for Dynamic Context

For runtime data, use a lambda or function:

```python
system_context=lambda ctx: f"""
Tenant: {ctx.get('tenant_name')}
Namespace: {ctx.get('k8s_namespace')}
User: {ctx.get('user_email')}
"""
```

## Monitoring

### Cache Performance Logs

DCAF logs cache performance when available:

```
INFO: ✅ Cache HIT: 950 tokens reused (~90% cost reduction)
INFO: 📝 Cache MISS: 950 tokens cached for next request (cache created)
```

### First Request is Always a MISS

The first request creates the cache (MISS). Subsequent requests within 5 minutes are HITs:

```
Request 1: MISS (creates cache)  → Full cost
Request 2: HIT  (uses cache)     → 10% cost
Request 3: HIT  (uses cache)     → 10% cost
...
Request N: MISS (cache expired)  → Full cost
```

## Troubleshooting

### No Cache Metrics in Logs

**Symptom**: Caching enabled but no "Cache HIT/MISS" logs

**Possible causes**:
1. System prompt below minimum token threshold
2. Model doesn't support caching
3. Bedrock API change

**Solution**: Check logs for warnings about token threshold

### Caching Not Enabled

**Symptom**: No cache-related logs at all

**Checklist**:
- [ ] `model_config={"cache_system_prompt": True}` set?
- [ ] Using Bedrock provider (not OpenAI)?
- [ ] Using supported model (Claude 3.5/3.7)?

## Cost Comparison

### Example Scenario

- Static prompt: 1500 tokens
- Dynamic context: 100 tokens
- 100 requests

**Without caching:**
- Per request: 1600 tokens
- Total: 160,000 tokens
- Cost: ~$0.48

**With caching:**
- First request: 1600 tokens (MISS)
- Next 99 requests: 100 tokens each (HIT)
- Total: 11,500 tokens
- Cost: ~$0.035

**Savings: ~93%** 💰

## Supported Models

Prompt caching is supported on:
- `anthropic.claude-3-7-sonnet-20250219-v1:0`
- `anthropic.claude-3-5-sonnet-20241022-v2:0`
- `anthropic.claude-3-5-haiku-20241022-v1:0`

## When NOT to Use Caching

❌ **Don't use caching when**:
- System prompt changes frequently
- System prompt is very short (<1024 tokens)
- Low request volume (cache expires between requests)
- Using non-Bedrock providers

✅ **DO use caching when**:
- Long, static system prompts
- High request volume (multiple requests per 5 minutes)
- Multi-tenant scenarios (static instructions, dynamic tenant context)

## Future Plans

This is a temporary implementation. Once Agno adds native prompt caching support, we'll migrate to their implementation and remove the custom code.

## Related Documentation

See the [DCAF documentation](../index.md) for more information.
```

**File**: `docs/api-reference/agents.md` (update)

Add to the Agent class documentation:

```markdown
### system_context

Optional dynamic context appended to the system prompt.

**Type**: `Optional[Union[str, Callable[[dict], str]]]`

**Purpose**: Separate dynamic runtime data from static instructions. When caching is enabled, this content is NOT cached and is evaluated fresh each request.

**Examples**:

```python
# String
agent = Agent(
    system="Static instructions",
    system_context="Tenant: acme-corp"
)

# Callable
agent = Agent(
    system="Static instructions",
    system_context=lambda ctx: f"Tenant: {ctx['tenant']}"
)
```

### model_config

Configuration passed to the model adapter.

**Type**: `Optional[dict]`

**Caching Options**:
- `cache_system_prompt` (bool): Enable Bedrock prompt caching. Requires static system prompt ≥1024 tokens.

**Example**:

```python
agent = Agent(
    system="Long static instructions...",
    model_config={
        "cache_system_prompt": True
    }
)
```
```

**Acceptance Criteria**:
- [ ] Guide explains what caching is and how it works
- [ ] Guide shows when to use and not use caching
- [ ] Guide includes troubleshooting section
- [ ] Guide includes cost comparison
- [ ] API reference documents new parameters

---

## Testing Strategy

### Unit Tests
- Cache checkpoint placement in system messages
- Static + dynamic prompt combination
- Token threshold checking
- Cache metrics logging
- Agent parameter handling

### Integration Tests
- End-to-end test with mock Bedrock client
- Verify cache checkpoint appears in actual request
- Test with real Bedrock (optional, in dev environment)

### Manual Testing

1. **Create test agent**:
```python
agent = Agent(
    system="..." * 300,  # Long prompt
    system_context=lambda ctx: f"Tenant: {ctx['tenant']}",
    model_config={"cache_system_prompt": True}
)
```

2. **Make first request** - look for "Cache MISS" in logs

3. **Make second request** - look for "Cache HIT" in logs

4. **Check Bedrock console** - verify requests include `cachePoint`

---

## Rollout Plan

1. **Phase 1** (Day 1): 
   - Task 1: Update Agent class
   - Task 2: Create CachingAwsBedrock

2. **Phase 2** (Day 2):
   - Task 3: Update AgnoAdapter
   - Task 4: Add cache metrics logging
   - Task 5: Unit tests

3. **Phase 3** (Day 3):
   - Task 6: Example application
   - Task 7: Documentation
   - Manual testing with real Bedrock

4. **Phase 4** (Day 4):
   - Code review
   - Integration testing
   - Documentation review

---

## Success Criteria

- [ ] `Agent(model_config={"cache_system_prompt": True})` enables caching
- [ ] `Agent(system="...", system_context="...")` correctly separates cached/uncached content
- [ ] Bedrock requests include `cachePoint` when caching is enabled
- [ ] Cache metrics are logged when available in Bedrock responses
- [ ] Token threshold is checked with appropriate warnings
- [ ] All existing tests pass (no regressions)
- [ ] New tests cover caching functionality
- [ ] Example application demonstrates usage
- [ ] Documentation is clear for new users

---

## Questions for Tech Lead

1. Should we log cache hit/miss metrics from Bedrock responses?
   **→ YES - if available through Agno**

2. Should we warn if system prompt is below minimum token count?
   **→ YES - warn and skip caching**

3. Should we support tool definition caching in v1 or defer to v2?
   **→ DEFER to v2 (experimental only)**

4. Where exactly in Agent is the runtime called?
   **→ Need to identify in current implementation**

5. Does Agno expose Bedrock response metrics?
   **→ Need to verify in Agno source**

---

## Resources

- [AWS Bedrock Prompt Caching Docs](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html)
- [Agno AwsBedrock Source](https://github.com/agno-agi/agno/blob/main/agno/models/aws/bedrock.py)

---

## Notes

- This is a **temporary implementation** until Agno adds native caching support
- All caching logic is internal to adapters (not exposed in public API)
- Caching is always **opt-in** via `model_config`
- Extensive logging for debugging and monitoring
- Token threshold checked automatically with warnings