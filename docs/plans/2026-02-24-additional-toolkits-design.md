# Additional Agno Toolkits via Environment Variable

**Date:** 2026-02-24
**Status:** Approved

## Problem

The `DCAF_DEFAULT_TOOLKIT` feature flag adds a fixed set of 5 Agno toolkits. Users need a way to inject additional Agno toolkits (e.g., Neo4jTools, DuckDbTools) into their agents without modifying code.

## Decision

Add a new environment variable `DCAF_ADDITIONAL_TOOLS` that accepts a comma-separated list of Agno toolkit references in short form. Each entry is dynamically imported and instantiated with its default constructor.

## Env Var Format

```bash
export DCAF_ADDITIONAL_TOOLS="neo4j.Neo4jTools,duckdb.DuckDbTools"
```

Each entry is `<submodule>.<ClassName>`, resolved as:

```python
from agno.tools.<submodule> import <ClassName>
```

## Approach

**New method `_load_additional_toolkits()` in `AgnoAdapter`** — parallel to existing `_build_default_toolkits()`.

### Changes

1. **`dcaf/core/config.py`** — Add `ADDITIONAL_TOOLS = "DCAF_ADDITIONAL_TOOLS"` to `EnvVars`.

2. **`dcaf/core/adapters/outbound/agno/adapter.py`** — Add `_load_additional_toolkits()` method and integrate into `_prepare_tools_with_defaults()`.

### New Method: `_load_additional_toolkits()`

1. Read `DCAF_ADDITIONAL_TOOLS` env var.
2. Split on comma, strip whitespace.
3. For each entry, split on the last `.` to get `(submodule, class_name)`.
4. `importlib.import_module(f"agno.tools.{submodule}")` then `getattr(module, class_name)`.
5. Instantiate with default constructor.
6. Log each loaded toolkit; warn and skip on failures (don't crash).

### Data Flow

```
DCAF_ADDITIONAL_TOOLS="neo4j.Neo4jTools,duckdb.DuckDbTools"
  → AgnoAdapter._prepare_tools_with_defaults()
    → _convert_tools_to_agno(user_tools)          # user tools
    → _build_default_toolkits()                    # if DCAF_DEFAULT_TOOLKIT=true
    → _load_additional_toolkits()                  # NEW: dynamic import
    → agno_tools = default_toolkits + user_tools + additional_toolkits
    → AgnoAgent(tools=agno_tools)
```

### Behavior

- **Env var unset (default):** No additional toolkits loaded.
- **Env var set:** Each entry is dynamically imported and appended to the tools list.
- **Works independently** of `DCAF_DEFAULT_TOOLKIT` — both can be used together or separately.
- **Error resilience:** Invalid entries log a warning and are skipped; the agent continues with whatever loaded successfully.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Invalid format (no `.`) | Log warning, skip entry |
| Import failure (module not found) | Log warning, skip entry |
| Class not found in module | Log warning, skip entry |
| Instantiation failure | Log warning, skip entry |

## Testing

- `_load_additional_toolkits()` returns empty list when env var unset.
- Returns correct toolkit instances when set with valid entries.
- Skips invalid entries with warning (does not raise).
- Integrates correctly in `_prepare_tools_with_defaults()` — appended after defaults and user tools.
- Case with both `DCAF_DEFAULT_TOOLKIT=true` and `DCAF_ADDITIONAL_TOOLS` set simultaneously.
