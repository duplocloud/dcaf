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
    system_prompt="You are a Kubernetes expert... [long instructions]",
    tools=[list_pods, delete_pod],
    model_config={
        "cache_system_prompt": True  # Enable caching
    }
)
```

### Separating Static and Dynamic Content

This is the **key pattern** for effective caching:

```python
from dcaf.core import Agent

agent = Agent(
    # Static - cached
    system_prompt="You are a Kubernetes expert. Your job is to help users manage their clusters...",
    
    # Dynamic - NOT cached
    system_context=lambda ctx: f"""
    Current tenant: {ctx['tenant_name']}
    Namespace: {ctx['k8s_namespace']}
    User: {ctx['user_email']}
    """,
    
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
system_prompt="You are a K8s expert. [lengthy guidelines]"
system_context="Current tenant: acme-corp"
```

❌ **Bad**: Mixing static and dynamic
```python
system_prompt="You are a K8s expert for tenant: acme-corp. [guidelines]"
```

### 2. Make Static Content Detailed

The more static content you cache, the bigger the savings:

✅ **Good**: Detailed instructions (1500+ tokens)
```python
system_prompt="""
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
system_prompt="You are a helpful Kubernetes assistant."
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

- [Agent API Reference](../api-reference/agents.md)
- [Creating Custom Agents](./custom-agents.md)
- [AWS Bedrock Guide](./working-with-bedrock.md)

