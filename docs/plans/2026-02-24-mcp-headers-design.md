# MCPTool: Add headers Support

## Problem

DCAF's `MCPTool` wraps Agno's `MCPTools` but does not forward headers when creating the Agno instance. Users connecting to authenticated MCP servers (e.g., behind Bearer tokens) have no way to pass HTTP headers through DCAF's API.

## Approach

Use Agno's existing `header_provider` parameter. Wrap a static `headers` dict as a `lambda: headers` callable. Agno handles merging headers into `StreamableHTTPClientParams` or `SSEClientParams` internally.

## Changes

### `dcaf/mcp/tools.py`

1. Add `headers: dict[str, str] | None = None` parameter to `MCPTool.__init__`
2. Validate: raise `ValueError` if `headers` is provided with `stdio` transport
3. Store as `self._headers`
4. In `_create_agno_mcp_tools()`, wrap as `header_provider=lambda: _headers` and pass to `AgnoMCPTools`

### `tests/core/test_mcp_tools.py`

- `test_headers_stored_on_init` — verify `_headers` is stored
- `test_headers_raises_for_stdio` — verify `ValueError` for stdio transport
- `test_headers_forwarded_as_header_provider` — verify Agno instance gets a callable
- `test_headers_none_by_default` — verify default behavior unchanged

## Usage

```python
from dcaf.mcp import MCPTool

mcp_tool = MCPTool(
    url="https://mcp-ai-studio.test21-apps.duplocloud.net/mcp",
    transport="streamable-http",
    headers={"Authorization": f"Bearer {os.environ['DUPLO_HELPDESK_MCP_TOKEN']}"},
)

agent = Agent(tools=[mcp_tool])
```
