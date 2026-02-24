# Default Agno Toolkit Feature Flag

**Date:** 2026-02-23
**Status:** Approved

## Problem

DCAF agents have no built-in tools — every tool must be explicitly provided by the caller. For development and interactive use cases, it's useful to have a standard set of Agno toolkits available out of the box without requiring callers to wire them up manually.

## Decision

Add a feature flag (`DCAF_DEFAULT_TOOLKIT=true`) that, when enabled, automatically includes 5 Agno built-in toolkits in every agent invocation. The flag is **off by default** so existing behavior is unchanged.

## Toolkits Included

| Toolkit | Import | Purpose |
|---------|--------|---------|
| `FileTools` | `agno.tools.file` | Read/write/search files |
| `LocalFileSystemTools` | `agno.tools.local_file_system` | Write files with directory management |
| `PythonTools` | `agno.tools.python` | Run Python code, pip install, save & run |
| `ShellTools` | `agno.tools.shell` | Run shell commands |
| `FileGenerationTools` | `agno.tools.file_generation` | Generate JSON, CSV, PDF, TXT files |

## Approach

**Approach A: Toolkit factory in AgnoAdapter** (selected over standalone module and config registry alternatives for simplicity).

### Changes

1. **`dcaf/core/config.py`** — Add `DEFAULT_TOOLKIT = "DCAF_DEFAULT_TOOLKIT"` to `EnvVars` class.

2. **`dcaf/core/adapters/outbound/agno/adapter.py`** — Add `_build_default_toolkits()` method and merge into `_create_agent_async()`.

### Data Flow

```
DCAF_DEFAULT_TOOLKIT=true
  → AgnoAdapter._create_agent_async()
    → _build_default_toolkits() returns [FileTools(), LocalFileSystemTools(), PythonTools(), ShellTools(), FileGenerationTools()]
    → agno_tools = default_toolkits + converted_user_tools
    → AgnoAgent(tools=agno_tools)
```

### Behavior

- **Flag off (default):** No change to current behavior.
- **Flag on:** Default toolkits are prepended to the tools list, additive with any user-provided tools.
- Agno toolkit instances are passed directly to `AgnoAgent(tools=...)` — they don't need conversion through `_convert_tools_to_agno()`.

## Testing

- `_build_default_toolkits()` returns 5 toolkit instances of correct types.
- With env var off, no default toolkits are added to agent.
- With env var on, default toolkits are merged with user tools.
