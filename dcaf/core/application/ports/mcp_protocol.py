"""
MCP Protocol - Interface for MCP tool containers.

This protocol defines the interface that MCP tool containers (like MCPTool)
implement. Using a Protocol allows isinstance() checks without circular imports
between the core application layer and the mcp module.

Usage:
    from dcaf.core.application.ports import MCPToolLike

    def _find_tool(self, name: str, tools: list) -> Any:
        for tool in tools:
            if isinstance(tool, MCPToolLike):
                continue  # Skip MCP toolkit containers
            if tool.name == name:
                return tool
        return None
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MCPToolLike(Protocol):
    """
    Protocol for MCP tool containers.

    MCP tools are special toolkit containers that hold multiple tools
    from an external MCP server. They need special handling because:
    - They're containers, not individual tools
    - The framework adapter handles their connection lifecycle
    - They provide tools dynamically via get_agno_toolkit()

    This protocol allows type-safe detection of MCP tools without
    importing the actual MCPTool class (avoiding circular imports).
    """

    @property
    def initialized(self) -> bool:
        """Whether the MCP connection is established and tools are loaded."""
        ...

    @property
    def refresh_connection(self) -> bool:
        """Whether to refresh the connection on each agent run."""
        ...

    def _get_agno_toolkit(self, auto_create: bool = True) -> Any:
        """
        Get the underlying framework toolkit instance.

        Used internally by framework adapters to pass the toolkit
        directly to the framework. Users should not need to call this.

        Args:
            auto_create: If True, create the toolkit if not yet created.

        Returns:
            The framework-specific toolkit instance.
        """
        ...

    async def connect(self, force: bool = False) -> None:
        """
        Connect to the MCP server and load available tools.

        Args:
            force: If True, force reconnection even if already connected.
        """
        ...

    async def close(self) -> None:
        """Close the MCP connection and clean up resources."""
        ...

    def get_tool_names(self) -> list[str]:
        """
        Get the names of all available tools.

        Returns:
            List of tool names from the MCP server.

        Raises:
            RuntimeError: If not connected.
        """
        ...
