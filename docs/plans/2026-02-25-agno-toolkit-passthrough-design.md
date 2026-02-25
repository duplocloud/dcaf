# Design: Native Agno Toolkit Pass-Through

**Date:** 2026-02-25
**Status:** Approved

## Problem

Native Agno `Toolkit` subclasses (e.g., `Neo4jTools`, `DuckDbTools`, `SqlTools`) passed via `Agent(tools=[...])` crash in `_convert_tools_to_agno()` because the DCAF tool converter accesses `.description`, which doesn't exist on Agno `Toolkit` instances.

```
ERROR | dcaf.core.agent | Streaming error: 'Neo4jTools' object has no attribute 'description'
```

## Root Cause

`_convert_tools_to_agno()` handles two cases:

1. **MCPToolLike** - detected via `isinstance()`, passed through directly
2. **Everything else** - assumed to be a DCAF `Tool`, sent to `AgnoToolConverter.to_agno()` which accesses `tool.description`

Native Agno `Toolkit` instances fall into case 2 but lack `.description`, causing `AttributeError`.

## Fix

Add an `isinstance(tool_obj, AgnoToolkit)` check between the MCP check and the DCAF converter in `_convert_tools_to_agno()`. Native Agno toolkits pass through directly to `AgnoAgent`, matching the existing pattern in `_build_default_toolkits()`.

### Changes

**`dcaf/core/adapters/outbound/agno/adapter.py`:**
- Import `Toolkit as AgnoToolkit` from `agno.tools.toolkit`
- Add `isinstance(tool_obj, AgnoToolkit)` guard after MCP check, before DCAF converter
- Log toolkit name when passing through

**Tests:**
- Verify native Agno `Toolkit` instances pass through without conversion
- Verify they don't crash `_convert_tools_to_agno()`
- Verify existing DCAF `Tool` and MCP paths are unaffected

## Decision

Pass through as-is (no approval wrapping), matching `_build_default_toolkits()` behavior.
