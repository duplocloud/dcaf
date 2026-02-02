# MCP Approval Test Server Design

**Date**: 2025-02-02
**Purpose**: Create a test MCP server and integration test to exercise the blacklist, auto-accept, and glob-based approval features.

## Test MCP Server

**File**: `tests/mcp_test_server.py`

A lightweight FastMCP server running over stdio with 9 dummy tools. Each tool returns a string confirming it was called.

### Tools

| Tool | Category | Expected Classification |
|------|----------|------------------------|
| `user_get` | read-like | auto-approved via `*_get*` |
| `file_read` | read-like | auto-approved via `*_read*` |
| `items_list` | read-like | auto-approved via `*_list*` |
| `user_delete` | write-like | requires approval |
| `file_write` | write-like | requires approval |
| `admin_reset` | write-like | blocked via `exclude_tools=["admin_*"]` |
| `data_export` | ambiguous | requires approval |
| `config_update` | ambiguous | requires approval |
| `system_status` | ambiguous | requires approval |

## Integration Test

**File**: `tests/test_mcp_approval_flow.py`

Connects to the test server using `MCPTool` with:

```python
mcp = MCPTool(
    command=".venv/bin/python tests/mcp_test_server.py",
    transport="stdio",
    exclude_tools=["admin_*"],
    auto_approve_tools=["*_get*", "*_read*", "*_list*"],
)
```

### Assertions

1. **Blocked tools**: `admin_reset` not present in available tools
2. **Auto-approved tools**: `user_get`, `file_read`, `items_list` have `requires_confirmation` unset (None)
3. **Approval-required tools**: `user_delete`, `file_write`, `data_export`, `config_update`, `system_status` have `requires_confirmation = True`
4. **Tool execution**: Calling an auto-approved tool returns the expected dummy string
