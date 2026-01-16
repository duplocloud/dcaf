"""
MCP Tools integration for DCAF.

This module provides a framework-agnostic wrapper for connecting to external
MCP (Model Context Protocol) servers and using their tools with DCAF agents.

Example:
    from dcaf.core import Agent
    from dcaf.mcp import MCPTools

    # Connect to an MCP server
    mcp_tools = MCPTools(
        url="http://localhost:8000/mcp",
        transport="streamable-http",
    )

    # Use with async context manager
    async with mcp_tools:
        agent = Agent(tools=[my_local_tool, mcp_tools])
        result = await agent.arun("Use the MCP tools to help me")

    # Or for stdio transport (local MCP server process)
    mcp_tools = MCPTools(
        command="python my_mcp_server.py",
        transport="stdio",
    )
"""

from typing import Optional, List, Literal, Dict, Any
import logging

logger = logging.getLogger(__name__)


class MCPTools:
    """
    A toolkit for connecting to external MCP servers and using their tools.

    This class provides a DCAF-native interface for MCP tool integration.
    It can be passed directly to Agent(tools=[...]) alongside regular DCAF tools.

    Supports three transport protocols:
    - stdio: Run a local command that speaks MCP protocol
    - sse: Connect via Server-Sent Events (deprecated, use streamable-http)
    - streamable-http: Connect via HTTP streaming (recommended)

    Example:
        # HTTP transport (recommended)
        mcp = MCPTools(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
        )

        # stdio transport (local process)
        mcp = MCPTools(
            command="python my_mcp_server.py",
            transport="stdio",
            env={"API_KEY": "secret"},
        )

        # With tool filtering
        mcp = MCPTools(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
            include_tools=["tool1", "tool2"],  # Only include these
            exclude_tools=["dangerous_tool"],   # Exclude these
            tool_name_prefix="mcp",             # Prefix all tool names
        )

        # Use with agent
        async with mcp:
            agent = Agent(tools=[mcp])
            result = await agent.arun("Help me with something")

    Attributes:
        initialized: Whether the connection has been established and tools loaded
    """

    def __init__(
        self,
        command: Optional[str] = None,
        *,
        url: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        transport: Literal["stdio", "sse", "streamable-http"] = "stdio",
        timeout_seconds: int = 10,
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
        tool_name_prefix: Optional[str] = None,
        refresh_connection: bool = False,
    ):
        """
        Initialize the MCP toolkit.

        Args:
            command: Command to run for stdio transport (e.g., "python server.py").
                    Required when transport is "stdio".
            url: URL for SSE or streamable-http transport.
                Required when transport is "sse" or "streamable-http".
            env: Environment variables to pass to the stdio command.
            transport: Transport protocol - "stdio", "sse", or "streamable-http".
            timeout_seconds: Connection timeout in seconds.
            include_tools: List of tool names to include (if None, includes all).
            exclude_tools: List of tool names to exclude (if None, excludes none).
            tool_name_prefix: Prefix to add to all tool names (e.g., "mcp" -> "mcp_toolname").
            refresh_connection: If True, refresh connection and tools on each agent run.

        Raises:
            ValueError: If required parameters are missing for the transport type.
            ImportError: If the Agno MCP integration is not available.
        """
        # Validate parameters based on transport
        if transport == "stdio" and command is None:
            raise ValueError(
                "The 'command' parameter is required when using stdio transport. "
                "Example: MCPTools(command='python my_server.py', transport='stdio')"
            )
        if transport in ("sse", "streamable-http") and url is None:
            raise ValueError(
                f"The 'url' parameter is required when using {transport} transport. "
                f"Example: MCPTools(url='http://localhost:8000/mcp', transport='{transport}')"
            )

        # Store configuration
        self._command = command
        self._url = url
        self._env = env
        self._transport = transport
        self._timeout_seconds = timeout_seconds
        self._include_tools = include_tools
        self._exclude_tools = exclude_tools
        self._tool_name_prefix = tool_name_prefix
        self._refresh_connection = refresh_connection

        # Internal state
        self._agno_mcp_tools = None
        self._initialized = False

        logger.info(
            f"MCPTools configured: transport={transport}, "
            f"url={url}, command={command}, "
            f"include={include_tools}, exclude={exclude_tools}"
        )

    @property
    def initialized(self) -> bool:
        """Whether the MCP connection is established and tools are loaded."""
        return self._initialized

    @property
    def refresh_connection(self) -> bool:
        """Whether to refresh the connection on each agent run."""
        return self._refresh_connection

    def _create_agno_mcp_tools(self):
        """
        Create the underlying Agno MCPTools instance.

        This is called lazily on first connect() to avoid import issues
        if Agno's MCP integration isn't installed.
        """
        if self._agno_mcp_tools is not None:
            return self._agno_mcp_tools

        try:
            from agno.tools.mcp import MCPTools as AgnoMCPTools
        except ImportError as e:
            raise ImportError(
                "MCP tools require the 'mcp' package. "
                "Install it with: pip install mcp"
            ) from e

        # Create the Agno MCPTools with our configuration
        self._agno_mcp_tools = AgnoMCPTools(
            command=self._command,
            url=self._url,
            env=self._env,
            transport=self._transport,
            timeout_seconds=self._timeout_seconds,
            include_tools=self._include_tools,
            exclude_tools=self._exclude_tools,
            tool_name_prefix=self._tool_name_prefix,
            refresh_connection=self._refresh_connection,
        )

        return self._agno_mcp_tools

    async def connect(self, force: bool = False) -> None:
        """
        Connect to the MCP server and load available tools.

        This method establishes the connection to the MCP server and
        fetches the list of available tools. It's called automatically
        when using the async context manager.

        Args:
            force: If True, force reconnection even if already connected.
        """
        agno_tools = self._create_agno_mcp_tools()
        await agno_tools.connect(force=force)
        self._initialized = agno_tools.initialized

        if self._initialized:
            tool_count = len(agno_tools.functions)
            logger.info(f"MCPTools connected: {tool_count} tools available")
            for name in agno_tools.functions.keys():
                logger.debug(f"  - {name}")

    async def close(self) -> None:
        """
        Close the MCP connection and clean up resources.

        This method is called automatically when exiting the async context manager.
        """
        if self._agno_mcp_tools is not None:
            await self._agno_mcp_tools.close()
            self._initialized = False
            logger.info("MCPTools connection closed")

    async def is_alive(self) -> bool:
        """
        Check if the MCP connection is still alive.

        Returns:
            True if connected and responsive, False otherwise.
        """
        if self._agno_mcp_tools is None:
            return False
        return await self._agno_mcp_tools.is_alive()

    async def __aenter__(self) -> "MCPTools":
        """Enter the async context manager, connecting to the MCP server."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager, closing the connection."""
        await self.close()

    def get_tool_names(self) -> List[str]:
        """
        Get the names of all available tools.

        Returns:
            List of tool names from the MCP server.

        Raises:
            RuntimeError: If not connected (call connect() first).
        """
        if not self._initialized or self._agno_mcp_tools is None:
            raise RuntimeError(
                "MCPTools not connected. Use 'async with mcp_tools:' or call 'await mcp_tools.connect()' first."
            )
        return list(self._agno_mcp_tools.functions.keys())

    def _get_agno_toolkit(self):
        """
        Get the underlying Agno MCPTools instance.

        This is used internally by the Agno adapter to pass the toolkit
        directly to Agno's Agent. Users should not need to call this.

        Returns:
            The Agno MCPTools instance.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._initialized or self._agno_mcp_tools is None:
            raise RuntimeError(
                "MCPTools not connected. Use 'async with mcp_tools:' or call 'await mcp_tools.connect()' first."
            )
        return self._agno_mcp_tools

    def __repr__(self) -> str:
        """String representation for debugging."""
        if self._transport == "stdio":
            target = f"command={self._command}"
        else:
            target = f"url={self._url}"

        status = "connected" if self._initialized else "not connected"
        tool_count = len(self._agno_mcp_tools.functions) if self._initialized and self._agno_mcp_tools else 0

        return f"<MCPTools {target} transport={self._transport} {status} tools={tool_count}>"
