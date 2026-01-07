# Response to Feature Request: Tool Context Injection

**To:** Architecture Diagram Agent Team  
**From:** DCAF Core Team  
**Date:** January 6, 2026  
**Re:** Feature Request - Tool Context Injection  
**Status:** ✅ Resolved

---

## Summary

We reviewed your feature request and have good news: **the functionality you need already exists in DCAF**, but there was a bug preventing it from working when Agno executes tools. We've fixed that bug and pushed the changes to the `vnext` branch.

**You don't need a new `_context` convention.** Use the existing `platform_context` parameter instead.

---

## What Was Wrong

Your diagnosis was accurate. When Agno executes tools internally, it was bypassing DCAF's context injection mechanism. The flow was:

```
Interceptor → sets request.context["tenant_id"]
      ↓
AgentService → had the context
      ↓
AgnoAdapter → did NOT pass context to tools
      ↓
Agno → called raw functions with only LLM-provided args
      ↓
Tool → received NO platform_context ❌
```

---

## What We Fixed

We updated the Agno adapter to inject `platform_context` into tools that declare it. The fix (commit `0247d3f`) includes:

1. **AgentRuntime port** — Added `platform_context` parameter to `invoke()` and `invoke_stream()`
2. **AgentService** — Now passes context to the runtime
3. **AgnoAdapter** — Creates wrapper closures that inject `platform_context` into tools

---

## How to Use It

Use the existing `platform_context` parameter convention:

```python
from dcaf.tools import tool

@tool(description="Execute a Cypher query with tenant scoping")
def run_cypher_query(
    cypher: str,
    params: dict = None,
    platform_context: dict = None,  # ← DCAF injects this automatically
) -> str:
    """Execute a Cypher query with automatic tenant scoping."""
    tenant_id = platform_context.get("tenant_id")
    role = platform_context.get("_resolved_role", "User")
    
    # Now you can enforce security!
    if role != "Administrator":
        cypher = add_tenant_filter(cypher, tenant_id)
    
    return execute_query(cypher, params)
```

### Key Points

| Aspect | Behavior |
|--------|----------|
| Parameter name | Must be exactly `platform_context` |
| Hidden from LLM | ✅ Yes — not included in tool schema |
| Automatically injected | ✅ Yes — when Agno executes the tool |
| Contains interceptor values | ✅ Yes — same context object |
| Thread-safe | ✅ Yes — captured in closure, no globals |
| Testable | ✅ Yes — just pass the dict in unit tests |

---

## Testing Your Tools

```python
def test_query_with_tenant_scoping():
    result = run_cypher_query(
        cypher="MATCH (n) RETURN n",
        platform_context={"tenant_id": "test-tenant", "_resolved_role": "User"}
    )
    assert "IN_TENANT" in result  # Verify scoping was applied
```

---

## Why We Didn't Use the `_` Prefix Convention

Your proposed `_context` convention was well-designed, but we already had `platform_context` doing the same thing. Adding a parallel convention would:

1. Increase API surface area
2. Create confusion about which to use
3. Require documentation for both patterns

The existing convention works — it just needed the adapter bug fixed.

---

## Removing Your Workaround

You can now remove the thread-local global store workaround:

```python
# BEFORE (workaround) - can be removed
set_platform_context({"tenant_id": "abc"})
ctx = get_platform_context()

# AFTER (native DCAF) - just use the parameter
def my_tool(arg: str, platform_context: dict = None) -> str:
    ctx = platform_context  # Already injected!
```

---

## Questions?

The fix is available now on `vnext`. If you encounter any issues or need additional context fields exposed, please reach out.

---

**Commit:** `0247d3f` on `vnext`  
**Files changed:** 
- `dcaf/core/adapters/outbound/agno/adapter.py`
- `dcaf/core/application/ports/agent_runtime.py`
- `dcaf/core/application/services/agent_service.py`

