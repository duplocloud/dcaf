"""
MCP Tool integration for DCAF.

This module provides a framework-agnostic wrapper for connecting to external
MCP (Model Context Protocol) servers and using their tools with DCAF agents.

DCAF automatically manages the MCP connection lifecycle - just pass MCPTool
to your agent and the framework handles connect/disconnect automatically.

Example (Automatic Lifecycle - Recommended):
    from dcaf.core import Agent
    from dcaf.mcp import MCPTool

    # Configure MCP server connection
    mcp_tool = MCPTool(
        url="http://localhost:8000/mcp",
        transport="streamable-http",
    )

    # Just pass to agent - DCAF manages the connection automatically!
    agent = Agent(tools=[my_local_tool, mcp_tool])
    result = await agent.arun("Use the MCP tools to help me")

Example (Manual Lifecycle - Optional):
    # For explicit control, use async context manager
    async with mcp_tool:
        agent = Agent(tools=[mcp_tool])
        result = await agent.arun("Use the MCP tools")

Example (stdio transport):
    mcp_tool = MCPTool(
        command="python my_mcp_server.py",
        transport="stdio",
    )

Example (With Hooks - Intercept Tool Calls):
    from dcaf.mcp import MCPTool, MCPToolCall

    # Pre-hook: called before each MCP tool execution
    async def my_pre_hook(call: MCPToolCall) -> None:
        print(f"About to call: {call.tool_name}")
        print(f"Arguments: {call.arguments}")

    # Post-hook: called after each MCP tool execution
    # Can modify and return a different result
    async def my_post_hook(call: MCPToolCall) -> Any:
        print(f"Tool {call.tool_name} returned: {call.result}")
        # Optionally transform the result
        return call.result

    mcp_tool = MCPTool(
        url="http://localhost:8000/mcp",
        transport="streamable-http",
        pre_hook=my_pre_hook,
        post_hook=my_post_hook,
    )
"""

import functools
import inspect
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

logger = logging.getLogger(__name__)


@dataclass
class MCPToolCall:
    """
    Context object passed to MCP tool hooks.

    This provides information about the tool being called, its arguments,
    and (for post-hooks) the result of the tool execution.

    Attributes:
        tool_name: Name of the MCP tool being called.
        arguments: Dictionary of arguments passed to the tool.
        result: The result from the tool (only populated in post-hooks).
        duration: Execution time in seconds (only populated in post-hooks).
        error: Exception if the tool failed (only populated in post-hooks on error).
        metadata: Additional metadata (target URL/command, transport type).
    """

    tool_name: str
    arguments: dict[str, Any]
    result: Any = None
    duration: float | None = None
    error: Exception | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# Type aliases for hook functions
PreHookFunc = Callable[[MCPToolCall], Awaitable[None] | None]
PostHookFunc = Callable[[MCPToolCall], Awaitable[Any] | Any]


class MCPTool:
    """
    A tool for connecting to external MCP servers and using their tools.

    This class provides a DCAF-native interface for MCP tool integration.
    It can be passed directly to Agent(tools=[...]) alongside regular DCAF tools.

    **Automatic Lifecycle Management**: DCAF automatically manages the MCP
    connection - just pass MCPTool to your agent and it handles connect/disconnect.

    Supports three transport protocols:
    - stdio: Run a local command that speaks MCP protocol
    - sse: Connect via Server-Sent Events (deprecated, use streamable-http)
    - streamable-http: Connect via HTTP streaming (recommended)

    Example (Automatic - Recommended):
        # Just configure and pass to agent
        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
        )

        agent = Agent(tools=[mcp])
        result = await agent.arun("Help me with something")
        # Connection is managed automatically!

    Example (With Filtering):
        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
            include_tools=["tool1", "tool2"],  # Only include these
            exclude_tools=["dangerous_tool"],   # Exclude these
            tool_name_prefix="mcp",             # Prefix all tool names
        )

    Example (Manual Context Manager):
        # For explicit control over connection lifecycle
        async with mcp:
            agent = Agent(tools=[mcp])
            result = await agent.arun("Help me with something")

    Attributes:
        initialized: Whether the connection has been established and tools loaded
    """

    def __init__(
        self,
        command: str | None = None,
        *,
        url: str | None = None,
        env: dict[str, str] | None = None,
        transport: Literal["stdio", "sse", "streamable-http"] = "stdio",
        timeout_seconds: int = 10,
        include_tools: list[str] | None = None,
        exclude_tools: list[str] | None = None,
        tool_name_prefix: str | None = None,
        refresh_connection: bool = False,
        pre_hook: PreHookFunc | None = None,
        post_hook: PostHookFunc | None = None,
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
            pre_hook: Async or sync function called before each tool execution.
                     Receives MCPToolCall with tool_name and arguments.
                     Use for logging, validation, or modifying arguments.
            post_hook: Async or sync function called after each tool execution.
                      Receives MCPToolCall with tool_name, arguments, result, and duration.
                      Return value replaces the tool result (return call.result to keep original).

        Raises:
            ValueError: If required parameters are missing for the transport type.
            ImportError: If the Agno MCP integration is not available.
        """
        # Validate parameters based on transport
        if transport == "stdio" and command is None:
            raise ValueError(
                "The 'command' parameter is required when using stdio transport. "
                "Example: MCPTool(command='python my_server.py', transport='stdio')"
            )
        if transport in ("sse", "streamable-http") and url is None:
            raise ValueError(
                f"The 'url' parameter is required when using {transport} transport. "
                f"Example: MCPTool(url='http://localhost:8000/mcp', transport='{transport}')"
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
        self._pre_hook = pre_hook
        self._post_hook = post_hook

        # Internal state
        self._agno_mcp_tools: Any = None
        self._initialized = False

        # Log configuration at INFO level for visibility
        target = url if transport in ("sse", "streamable-http") else command
        logger.info(f"🔌 MCP: Configured MCPTool (transport={transport}, target={target})")
        if include_tools:
            logger.info(f"🔌 MCP: Tool filter - include: {include_tools}")
        if exclude_tools:
            logger.info(f"🔌 MCP: Tool filter - exclude: {exclude_tools}")
        if tool_name_prefix:
            logger.info(f"🔌 MCP: Tool name prefix: {tool_name_prefix}")

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
            logger.debug("🔌 MCP: Reusing existing Agno MCPTools instance")
            return self._agno_mcp_tools

        logger.info("🔌 MCP: Creating Agno MCPTools instance...")

        try:
            from agno.tools.mcp import MCPTools as AgnoMCPTools
        except ImportError as e:
            logger.error("🔌 MCP: Failed to import - 'mcp' package not installed")
            raise ImportError(
                "MCP tools require the 'mcp' package. Install it with: pip install mcp"
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

        target = self._url or self._command
        logger.info(f"🔌 MCP: Agno MCPTools created (target={target})")

        # Wrap the toolkit to add logging for tool execution
        self._wrap_tools_with_logging()

        return self._agno_mcp_tools

    def _wrap_tools_with_logging(self) -> None:
        """
        Wrap MCP tool entrypoints with logging to track tool execution.

        This modifies the Agno MCPTools functions in-place to add logging
        before and after each tool call, including timing and result info.
        """
        if self._agno_mcp_tools is None:
            return

        # Store original build_tools and wrap it
        original_build_tools = self._agno_mcp_tools.build_tools

        async def wrapped_build_tools():
            """Build tools and then wrap them with logging."""
            await original_build_tools()
            # After tools are built, wrap each function's entrypoint
            self._wrap_function_entrypoints()

        # Replace the build_tools method
        self._agno_mcp_tools.build_tools = wrapped_build_tools

    def _wrap_function_entrypoints(self) -> None:
        """Wrap each function's entrypoint with logging and hooks."""
        if self._agno_mcp_tools is None:
            return

        target = self._url or self._command
        metadata = {"target": target, "transport": self._transport}

        for func_name, func in self._agno_mcp_tools.functions.items():
            if not hasattr(func, "entrypoint") or func.entrypoint is None:
                continue

            original_entrypoint = func.entrypoint

            # Create a wrapper for async functions with logging and hooks
            @functools.wraps(original_entrypoint)
            async def hooked_entrypoint(
                *args,
                _tool_name=func_name,
                _target=target,
                _original=original_entrypoint,
                _metadata=metadata,
                _pre_hook=self._pre_hook,
                _post_hook=self._post_hook,
                **kwargs,
            ):
                """Wrapper that logs MCP tool execution and invokes hooks."""
                # Log tool call start
                logger.info(f"🔧 MCP Tool Call: {_tool_name} (target={_target})")
                if kwargs:
                    # Truncate long values for readability
                    logged_kwargs = {}
                    for k, v in kwargs.items():
                        str_v = str(v)
                        if len(str_v) > 200:
                            logged_kwargs[k] = str_v[:200] + "..."
                        else:
                            logged_kwargs[k] = v
                    logger.info(f"🔧 MCP Tool Args: {logged_kwargs}")

                # Create the tool call context for hooks
                tool_call = MCPToolCall(
                    tool_name=_tool_name,
                    arguments=dict(kwargs),
                    metadata=dict(_metadata),
                )

                # Invoke pre-hook if provided
                if _pre_hook is not None:
                    try:
                        logger.debug(f"🔧 MCP Pre-Hook: invoking for {_tool_name}")
                        hook_result = _pre_hook(tool_call)
                        if inspect.isawaitable(hook_result):
                            await hook_result
                    except Exception as e:
                        logger.error(f"🔧 MCP Pre-Hook Error: {type(e).__name__}: {e}")
                        raise

                start_time = time.time()
                try:
                    result = await _original(*args, **kwargs)
                    duration = time.time() - start_time

                    # Log result (truncated if long)
                    result_str = str(result)
                    if len(result_str) > 500:
                        result_preview = result_str[:500] + "..."
                    else:
                        result_preview = result_str

                    logger.info(f"🔧 MCP Tool Result: {_tool_name} completed in {duration:.3f}s")
                    logger.debug(f"🔧 MCP Tool Result Preview: {result_preview}")

                    # Invoke post-hook if provided
                    if _post_hook is not None:
                        try:
                            logger.debug(f"🔧 MCP Post-Hook: invoking for {_tool_name}")
                            tool_call.result = result
                            tool_call.duration = duration
                            hook_result = _post_hook(tool_call)
                            if inspect.isawaitable(hook_result):
                                hook_result = await hook_result
                            # Post-hook can transform the result
                            if hook_result is not None:
                                result = hook_result
                        except Exception as e:
                            logger.error(f"🔧 MCP Post-Hook Error: {type(e).__name__}: {e}")
                            raise

                    return result

                except Exception as e:
                    duration = time.time() - start_time
                    logger.error(
                        f"🔧 MCP Tool Error: {_tool_name} failed after {duration:.3f}s - {type(e).__name__}: {e}"
                    )

                    # Invoke post-hook with error info if provided
                    if _post_hook is not None:
                        try:
                            tool_call.error = e
                            tool_call.duration = duration
                            hook_result = _post_hook(tool_call)
                            if inspect.isawaitable(hook_result):
                                await hook_result
                        except Exception as hook_error:
                            logger.error(f"🔧 MCP Post-Hook Error (on tool error): {type(hook_error).__name__}: {hook_error}")

                    raise

            # Replace the entrypoint
            func.entrypoint = hooked_entrypoint

    async def connect(self, force: bool = False) -> None:
        """
        Connect to the MCP server and load available tools.

        This method establishes the connection to the MCP server and
        fetches the list of available tools. It's called automatically
        when using the async context manager.

        Args:
            force: If True, force reconnection even if already connected.
        """
        target = self._url or self._command
        logger.info(f"🔌 MCP: Connecting to MCP server (target={target}, force={force})...")

        agno_tools = self._create_agno_mcp_tools()
        await agno_tools.connect(force=force)
        self._initialized = agno_tools.initialized

        if self._initialized:
            tool_count = len(agno_tools.functions)
            tool_names = list(agno_tools.functions.keys())
            logger.info(f"🔌 MCP: ✅ Connected successfully - {tool_count} tools available")
            logger.info(f"🔌 MCP: Available tools: {tool_names}")
            for name in tool_names:
                logger.debug(f"🔌 MCP:   - {name}")
        else:
            logger.warning("🔌 MCP: ⚠️ Connection completed but not initialized")

    async def close(self) -> None:
        """
        Close the MCP connection and clean up resources.

        This method is called automatically when exiting the async context manager.
        """
        target = self._url or self._command
        if self._agno_mcp_tools is not None:
            logger.info(f"🔌 MCP: Closing connection (target={target})...")
            await self._agno_mcp_tools.close()
            self._initialized = False
            logger.info("🔌 MCP: ✅ Connection closed successfully")
        else:
            logger.debug(f"🔌 MCP: No connection to close (target={target})")

    async def is_alive(self) -> bool:
        """
        Check if the MCP connection is still alive.

        Returns:
            True if connected and responsive, False otherwise.
        """
        if self._agno_mcp_tools is None:
            logger.debug("🔌 MCP: is_alive() = False (no connection)")
            return False
        alive = await self._agno_mcp_tools.is_alive()
        logger.debug(f"🔌 MCP: is_alive() = {alive}")
        return bool(alive)

    async def __aenter__(self) -> "MCPTool":
        """Enter the async context manager, connecting to the MCP server."""
        target = self._url or self._command
        logger.debug(f"🔌 MCP: Entering context manager (target={target})")
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager, closing the connection."""
        target = self._url or self._command
        if exc_type:
            logger.warning(
                f"🔌 MCP: Exiting context manager with exception: {exc_type.__name__}: {exc_val}"
            )
        else:
            logger.debug(f"🔌 MCP: Exiting context manager (target={target})")
        await self.close()

    def get_tool_names(self) -> list[str]:
        """
        Get the names of all available tools.

        Returns:
            List of tool names from the MCP server.

        Raises:
            RuntimeError: If not connected (call connect() first).
        """
        if not self._initialized or self._agno_mcp_tools is None:
            raise RuntimeError(
                "MCPTool not connected. Use 'async with mcp_tool:' or call 'await mcp_tool.connect()' first."
            )
        tool_names = list(self._agno_mcp_tools.functions.keys())
        logger.debug(f"🔌 MCP: get_tool_names() returning {len(tool_names)} tools: {tool_names}")
        return tool_names

    def _get_agno_toolkit(self, auto_create: bool = True):
        """
        Get the underlying Agno MCPTools instance.

        This is used internally by the Agno adapter to pass the toolkit
        directly to Agno's Agent. Users should not need to call this.

        When auto_create=True (the default), this will create the Agno MCPTools
        instance if it doesn't exist yet, allowing Agno's Agent to handle the
        connection lifecycle automatically.

        Args:
            auto_create: If True, create the Agno MCPTools if not yet created.
                        This allows Agno to manage the connection lifecycle.

        Returns:
            The Agno MCPTools instance.

        Raises:
            RuntimeError: If auto_create=False and not connected.
        """
        if auto_create:
            # Create the Agno MCPTools if needed - Agno will handle connection
            logger.debug(
                "🔌 MCP: _get_agno_toolkit(auto_create=True) - creating/returning toolkit for Agno lifecycle management"
            )
            return self._create_agno_mcp_tools()

        # Legacy behavior: require initialization
        if not self._initialized or self._agno_mcp_tools is None:
            raise RuntimeError(
                "MCPTool not connected. Use 'async with mcp_tool:' or call 'await mcp_tool.connect()' first."
            )
        logger.debug(
            "🔌 MCP: _get_agno_toolkit(auto_create=False) - returning pre-connected toolkit"
        )
        return self._agno_mcp_tools

    def __repr__(self) -> str:
        """String representation for debugging."""
        target = f"command={self._command}" if self._transport == "stdio" else f"url={self._url}"

        status = "connected" if self._initialized else "not connected"
        tool_count = (
            len(self._agno_mcp_tools.functions) if self._initialized and self._agno_mcp_tools else 0
        )

        return f"<MCPTool {target} transport={self._transport} {status} tools={tool_count}>"
