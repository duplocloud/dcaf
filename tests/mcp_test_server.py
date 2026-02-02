"""
Test MCP server with dummy tools for exercising approval/blacklist/auto-accept features.

Run via stdio: python tests/mcp_test_server.py

Tools are named to exercise glob pattern matching:
- *_get*, *_read*, *_list*  → intended for auto-approve
- *_delete*, *_write*       → intended for approval-required
- admin_*                   → intended for blacklist (exclude_tools)
- data_export, config_update, system_status → ambiguous, approval-required
"""

from mcp.server.fastmcp import FastMCP

server = FastMCP("test-approval-server")


@server.tool()
def user_get(user_id: str) -> str:
    """Get a user by ID."""
    return f"Tool 'user_get' executed with user_id={user_id}"


@server.tool()
def file_read(path: str) -> str:
    """Read a file by path."""
    return f"Tool 'file_read' executed with path={path}"


@server.tool()
def items_list(category: str = "all") -> str:
    """List items in a category."""
    return f"Tool 'items_list' executed with category={category}"


@server.tool()
def user_delete(user_id: str) -> str:
    """Delete a user by ID."""
    return f"Tool 'user_delete' executed with user_id={user_id}"


@server.tool()
def file_write(path: str, content: str) -> str:
    """Write content to a file."""
    return f"Tool 'file_write' executed with path={path}"


@server.tool()
def admin_reset(target: str) -> str:
    """Reset an admin target (dangerous operation)."""
    return f"Tool 'admin_reset' executed with target={target}"


@server.tool()
def data_export(format: str = "csv") -> str:
    """Export data in the specified format."""
    return f"Tool 'data_export' executed with format={format}"


@server.tool()
def config_update(key: str, value: str) -> str:
    """Update a configuration value."""
    return f"Tool 'config_update' executed with key={key}, value={value}"


@server.tool()
def system_status() -> str:
    """Check system status."""
    return "Tool 'system_status' executed"


if __name__ == "__main__":
    server.run(transport="stdio")
