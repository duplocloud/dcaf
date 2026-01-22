"""
Tests for DCAF MCPTool integration.

These tests verify:
1. MCPTool initialization and parameter validation
2. The adapter correctly recognizes MCPTool instances
3. MCPTool can be used alongside regular DCAF tools
4. Pre-hook and post-hook functionality
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest


class TestMCPToolInitialization:
    """Test MCPTool initialization and validation."""

    def test_stdio_transport_requires_command(self):
        """Should raise ValueError if stdio transport without command."""
        from dcaf.mcp import MCPTool

        with pytest.raises(ValueError, match="command.*required"):
            MCPTool(transport="stdio")

    def test_streamable_http_transport_requires_url(self):
        """Should raise ValueError if streamable-http transport without url."""
        from dcaf.mcp import MCPTool

        with pytest.raises(ValueError, match="url.*required"):
            MCPTool(transport="streamable-http")

    def test_sse_transport_requires_url(self):
        """Should raise ValueError if sse transport without url."""
        from dcaf.mcp import MCPTool

        with pytest.raises(ValueError, match="url.*required"):
            MCPTool(transport="sse")

    def test_stdio_transport_with_command_succeeds(self):
        """Should succeed when stdio transport has command."""
        from dcaf.mcp import MCPTool

        mcp = MCPTool(command="python server.py", transport="stdio")
        assert mcp._command == "python server.py"
        assert mcp._transport == "stdio"
        assert not mcp.initialized

    def test_streamable_http_transport_with_url_succeeds(self):
        """Should succeed when streamable-http transport has url."""
        from dcaf.mcp import MCPTool

        mcp = MCPTool(url="http://localhost:8000/mcp", transport="streamable-http")
        assert mcp._url == "http://localhost:8000/mcp"
        assert mcp._transport == "streamable-http"
        assert not mcp.initialized

    def test_tool_filtering_options(self):
        """Should store include/exclude tool options."""
        from dcaf.mcp import MCPTool

        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
            include_tools=["tool1", "tool2"],
            exclude_tools=["tool3"],
            tool_name_prefix="mcp",
        )
        assert mcp._include_tools == ["tool1", "tool2"]
        assert mcp._exclude_tools == ["tool3"]
        assert mcp._tool_name_prefix == "mcp"

    def test_hook_options(self):
        """Should store pre_hook and post_hook options."""
        from dcaf.mcp import MCPTool, MCPToolCall

        async def my_pre_hook(call: MCPToolCall) -> None:
            pass

        async def my_post_hook(call: MCPToolCall):
            return call.result

        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
            pre_hook=my_pre_hook,
            post_hook=my_post_hook,
        )
        assert mcp._pre_hook == my_pre_hook
        assert mcp._post_hook == my_post_hook

    def test_hooks_default_to_none(self):
        """Hooks should default to None when not provided."""
        from dcaf.mcp import MCPTool

        mcp = MCPTool(url="http://localhost:8000/mcp", transport="streamable-http")
        assert mcp._pre_hook is None
        assert mcp._post_hook is None


class TestMCPToolNotConnectedErrors:
    """Test that appropriate errors are raised when not connected."""

    def test_get_tool_names_requires_connection(self):
        """Should raise RuntimeError if not connected."""
        from dcaf.mcp import MCPTool

        mcp = MCPTool(url="http://localhost:8000/mcp", transport="streamable-http")

        with pytest.raises(RuntimeError, match="not connected"):
            mcp.get_tool_names()

    def test_get_agno_toolkit_auto_create_false_requires_connection(self):
        """Should raise RuntimeError if auto_create=False and not connected."""
        from dcaf.mcp import MCPTool

        mcp = MCPTool(url="http://localhost:8000/mcp", transport="streamable-http")

        with pytest.raises(RuntimeError, match="not connected"):
            mcp._get_agno_toolkit(auto_create=False)


class TestMCPToolAutoConnect:
    """Test automatic connection behavior for framework integration."""

    def test_get_agno_toolkit_auto_creates_by_default(self):
        """Should auto-create Agno MCPTool when auto_create=True (default)."""
        from dcaf.mcp import MCPTool

        mcp = MCPTool(url="http://localhost:8000/mcp", transport="streamable-http")

        # Mock the Agno import
        with patch("dcaf.mcp.tools.MCPTool._create_agno_mcp_tools") as mock_create:
            mock_agno = Mock()
            mock_agno.initialized = False
            mock_create.return_value = mock_agno

            # Should NOT raise - it creates the toolkit for Agno to manage
            result = mcp._get_agno_toolkit()

            mock_create.assert_called_once()
            assert result == mock_agno

    def test_adapter_handles_uninitialized_mcp_tools(self):
        """Adapter should accept uninitialized MCPTool and let Agno manage lifecycle."""
        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter
        from dcaf.mcp import MCPTool

        mcp = MCPTool(url="http://localhost:8000/mcp", transport="streamable-http")

        # Mock the Agno MCPTool creation
        mock_agno = Mock()
        mock_agno.initialized = False
        mock_agno.functions = {}

        with patch.object(mcp, "_create_agno_mcp_tools", return_value=mock_agno):
            adapter = AgnoAdapter()

            # Convert tools - should not raise even though not connected
            agno_tools = adapter._convert_tools_to_agno([mcp])

            assert len(agno_tools) == 1
            assert agno_tools[0] == mock_agno


class TestAdapterMCPToolDetection:
    """Test that AgnoAdapter correctly detects DCAF MCPTool."""

    def test_adapter_detects_mcp_tools(self):
        """Adapter should identify DCAF MCPTool instances."""
        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter
        from dcaf.mcp import MCPTool

        mcp = MCPTool(url="http://localhost:8000/mcp", transport="streamable-http")
        adapter = AgnoAdapter()

        assert adapter._is_dcaf_mcp_tools(mcp) is True

    def test_adapter_does_not_detect_regular_tools(self):
        """Adapter should not identify regular tools as MCPTool."""
        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter
        from dcaf.tools import tool

        @tool(description="A regular tool")
        def my_tool(x: str) -> str:
            return x

        adapter = AgnoAdapter()
        assert adapter._is_dcaf_mcp_tools(my_tool) is False

    def test_adapter_does_not_detect_other_objects(self):
        """Adapter should not identify random objects as MCPTool."""
        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter()

        # Various objects that shouldn't be detected
        assert adapter._is_dcaf_mcp_tools("string") is False
        assert adapter._is_dcaf_mcp_tools(123) is False
        assert adapter._is_dcaf_mcp_tools({"dict": "value"}) is False
        assert adapter._is_dcaf_mcp_tools(lambda x: x) is False


class TestMCPToolRepr:
    """Test string representations."""

    def test_repr_not_connected(self):
        """Should show not connected status."""
        from dcaf.mcp import MCPTool

        mcp = MCPTool(url="http://localhost:8000/mcp", transport="streamable-http")
        repr_str = repr(mcp)

        assert "url=http://localhost:8000/mcp" in repr_str
        assert "streamable-http" in repr_str
        assert "not connected" in repr_str

    def test_repr_stdio(self):
        """Should show command for stdio transport."""
        from dcaf.mcp import MCPTool

        mcp = MCPTool(command="python server.py", transport="stdio")
        repr_str = repr(mcp)

        assert "command=python server.py" in repr_str
        assert "stdio" in repr_str


class TestMCPToolExport:
    """Test that MCPTool is properly exported."""

    def test_import_from_dcaf_mcp(self):
        """Should be importable from dcaf.mcp."""
        from dcaf.mcp import MCPTool

        assert MCPTool is not None

    def test_mcp_tool_call_import_from_dcaf_mcp(self):
        """MCPToolCall should be importable from dcaf.mcp."""
        from dcaf.mcp import MCPToolCall

        assert MCPToolCall is not None

    def test_in_all(self):
        """Should be in __all__."""
        from dcaf import mcp

        assert "MCPTool" in mcp.__all__
        assert "MCPToolCall" in mcp.__all__


@pytest.mark.asyncio
class TestMCPToolConnection:
    """Test MCPTool connection behavior (mocked)."""

    async def test_connect_creates_agno_mcp_tools(self):
        """Connect should create underlying Agno MCPTool."""
        from dcaf.mcp import MCPTool

        mcp = MCPTool(url="http://localhost:8000/mcp", transport="streamable-http")

        # Mock the Agno MCPTool
        with patch("dcaf.mcp.tools.MCPTool._create_agno_mcp_tools") as mock_create:
            mock_agno = AsyncMock()
            mock_agno.connect = AsyncMock()
            mock_agno.initialized = True
            mock_agno.functions = {"tool1": Mock(), "tool2": Mock()}
            mock_create.return_value = mock_agno

            await mcp.connect()

            mock_create.assert_called_once()
            mock_agno.connect.assert_called_once_with(force=False)
            assert mcp.initialized is True

    async def test_context_manager_connects_and_closes(self):
        """Async context manager should connect on enter and close on exit."""
        from dcaf.mcp import MCPTool

        mcp = MCPTool(url="http://localhost:8000/mcp", transport="streamable-http")

        # Mock the Agno MCPTool
        mock_agno = AsyncMock()
        mock_agno.connect = AsyncMock()
        mock_agno.close = AsyncMock()
        mock_agno.initialized = True
        mock_agno.functions = {}

        # Patch _create_agno_mcp_tools to set _agno_mcp_tools
        def create_mock():
            mcp._agno_mcp_tools = mock_agno
            return mock_agno

        with patch.object(mcp, "_create_agno_mcp_tools", side_effect=create_mock):
            async with mcp:
                assert mcp.initialized is True
                mock_agno.connect.assert_called_once()

            mock_agno.close.assert_called_once()
            assert mcp.initialized is False

    async def test_get_tool_names_after_connect(self):
        """Should return tool names after connecting."""
        from dcaf.mcp import MCPTool

        mcp = MCPTool(url="http://localhost:8000/mcp", transport="streamable-http")

        mock_agno = AsyncMock()
        mock_agno.connect = AsyncMock()
        mock_agno.initialized = True
        mock_agno.functions = {"search": Mock(), "query": Mock()}

        # Patch _create_agno_mcp_tools to set _agno_mcp_tools
        def create_mock():
            mcp._agno_mcp_tools = mock_agno
            return mock_agno

        with patch.object(mcp, "_create_agno_mcp_tools", side_effect=create_mock):
            await mcp.connect()
            tool_names = mcp.get_tool_names()

            assert "search" in tool_names
            assert "query" in tool_names
            assert len(tool_names) == 2


class TestMCPToolCallDataclass:
    """Test MCPToolCall dataclass."""

    def test_mcp_tool_call_creation(self):
        """Should create MCPToolCall with required fields."""
        from dcaf.mcp import MCPToolCall

        call = MCPToolCall(
            tool_name="search",
            arguments={"query": "test"},
        )
        assert call.tool_name == "search"
        assert call.arguments == {"query": "test"}
        assert call.result is None
        assert call.duration is None
        assert call.error is None
        assert call.metadata == {}

    def test_mcp_tool_call_with_all_fields(self):
        """Should create MCPToolCall with all fields."""
        from dcaf.mcp import MCPToolCall

        error = ValueError("test error")
        call = MCPToolCall(
            tool_name="search",
            arguments={"query": "test"},
            result="found results",
            duration=1.5,
            error=error,
            metadata={"target": "http://localhost:8000"},
        )
        assert call.tool_name == "search"
        assert call.arguments == {"query": "test"}
        assert call.result == "found results"
        assert call.duration == 1.5
        assert call.error == error
        assert call.metadata == {"target": "http://localhost:8000"}


@pytest.mark.asyncio
class TestMCPToolHooks:
    """Test pre-hook and post-hook functionality."""

    async def test_pre_hook_called_before_tool_execution(self):
        """Pre-hook should be called before tool execution with correct context."""
        from dcaf.mcp import MCPTool, MCPToolCall

        hook_calls = []

        async def pre_hook(call: MCPToolCall) -> None:
            hook_calls.append({
                "tool_name": call.tool_name,
                "arguments": call.arguments,
                "has_result": call.result is not None,
            })

        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
            pre_hook=pre_hook,
        )

        # Mock the Agno MCPTool with a function that has an entrypoint
        mock_func = Mock()
        mock_func.entrypoint = AsyncMock(return_value="tool result")

        mock_agno = Mock()
        mock_agno.functions = {"search": mock_func}
        mock_agno.build_tools = AsyncMock()

        mcp._agno_mcp_tools = mock_agno

        # Manually trigger the wrapping (normally happens during build_tools)
        mcp._wrap_function_entrypoints()

        # Call the wrapped entrypoint
        result = await mock_func.entrypoint(query="test query")

        # Verify pre-hook was called
        assert len(hook_calls) == 1
        assert hook_calls[0]["tool_name"] == "search"
        assert hook_calls[0]["arguments"] == {"query": "test query"}
        assert hook_calls[0]["has_result"] is False  # Pre-hook doesn't have result yet
        assert result == "tool result"

    async def test_post_hook_called_after_tool_execution(self):
        """Post-hook should be called after tool execution with result."""
        from dcaf.mcp import MCPTool, MCPToolCall

        hook_calls = []

        async def post_hook(call: MCPToolCall):
            hook_calls.append({
                "tool_name": call.tool_name,
                "arguments": call.arguments,
                "result": call.result,
                "has_duration": call.duration is not None,
            })
            return call.result

        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
            post_hook=post_hook,
        )

        mock_func = Mock()
        mock_func.entrypoint = AsyncMock(return_value="search results")

        mock_agno = Mock()
        mock_agno.functions = {"search": mock_func}

        mcp._agno_mcp_tools = mock_agno
        mcp._wrap_function_entrypoints()

        result = await mock_func.entrypoint(query="test")

        assert len(hook_calls) == 1
        assert hook_calls[0]["tool_name"] == "search"
        assert hook_calls[0]["result"] == "search results"
        assert hook_calls[0]["has_duration"] is True
        assert result == "search results"

    async def test_post_hook_can_transform_result(self):
        """Post-hook should be able to transform the result."""
        from dcaf.mcp import MCPTool, MCPToolCall

        async def post_hook(call: MCPToolCall):
            # Transform the result
            return f"TRANSFORMED: {call.result}"

        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
            post_hook=post_hook,
        )

        mock_func = Mock()
        mock_func.entrypoint = AsyncMock(return_value="original result")

        mock_agno = Mock()
        mock_agno.functions = {"search": mock_func}

        mcp._agno_mcp_tools = mock_agno
        mcp._wrap_function_entrypoints()

        result = await mock_func.entrypoint()

        assert result == "TRANSFORMED: original result"

    async def test_sync_hooks_are_supported(self):
        """Sync hooks should work correctly."""
        from dcaf.mcp import MCPTool, MCPToolCall

        pre_called = []
        post_called = []

        def sync_pre_hook(call: MCPToolCall) -> None:
            pre_called.append(call.tool_name)

        def sync_post_hook(call: MCPToolCall):
            post_called.append(call.result)
            return call.result

        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
            pre_hook=sync_pre_hook,
            post_hook=sync_post_hook,
        )

        mock_func = Mock()
        mock_func.entrypoint = AsyncMock(return_value="result")

        mock_agno = Mock()
        mock_agno.functions = {"tool": mock_func}

        mcp._agno_mcp_tools = mock_agno
        mcp._wrap_function_entrypoints()

        await mock_func.entrypoint()

        assert pre_called == ["tool"]
        assert post_called == ["result"]

    async def test_post_hook_called_on_error_with_error_info(self):
        """Post-hook should be called even when tool fails, with error info."""
        from dcaf.mcp import MCPTool, MCPToolCall

        hook_calls = []

        async def post_hook(call: MCPToolCall):
            hook_calls.append({
                "tool_name": call.tool_name,
                "error": call.error,
                "has_duration": call.duration is not None,
            })
            # Don't return anything - let the error propagate

        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
            post_hook=post_hook,
        )

        test_error = ValueError("Tool failed!")
        mock_func = Mock()
        mock_func.entrypoint = AsyncMock(side_effect=test_error)

        mock_agno = Mock()
        mock_agno.functions = {"failing_tool": mock_func}

        mcp._agno_mcp_tools = mock_agno
        mcp._wrap_function_entrypoints()

        with pytest.raises(ValueError, match="Tool failed!"):
            await mock_func.entrypoint()

        assert len(hook_calls) == 1
        assert hook_calls[0]["tool_name"] == "failing_tool"
        assert hook_calls[0]["error"] == test_error
        assert hook_calls[0]["has_duration"] is True

    async def test_pre_hook_error_stops_execution(self):
        """If pre-hook raises, tool should not execute."""
        from dcaf.mcp import MCPTool, MCPToolCall

        tool_executed = []

        async def failing_pre_hook(call: MCPToolCall) -> None:
            raise RuntimeError("Pre-hook failed!")

        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
            pre_hook=failing_pre_hook,
        )

        async def track_execution(**kwargs):
            tool_executed.append(True)
            return "result"

        mock_func = Mock()
        mock_func.entrypoint = track_execution

        mock_agno = Mock()
        mock_agno.functions = {"tool": mock_func}

        mcp._agno_mcp_tools = mock_agno
        mcp._wrap_function_entrypoints()

        with pytest.raises(RuntimeError, match="Pre-hook failed!"):
            await mock_func.entrypoint()

        # Tool should NOT have been executed
        assert tool_executed == []

    async def test_metadata_includes_target_and_transport(self):
        """MCPToolCall metadata should include target and transport."""
        from dcaf.mcp import MCPTool, MCPToolCall

        received_metadata = []

        async def pre_hook(call: MCPToolCall) -> None:
            received_metadata.append(call.metadata)

        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
            pre_hook=pre_hook,
        )

        mock_func = Mock()
        mock_func.entrypoint = AsyncMock(return_value="result")

        mock_agno = Mock()
        mock_agno.functions = {"tool": mock_func}

        mcp._agno_mcp_tools = mock_agno
        mcp._wrap_function_entrypoints()

        await mock_func.entrypoint()

        assert len(received_metadata) == 1
        assert received_metadata[0]["target"] == "http://localhost:8000/mcp"
        assert received_metadata[0]["transport"] == "streamable-http"

    async def test_both_hooks_called_in_order(self):
        """Both pre and post hooks should be called in correct order."""
        from dcaf.mcp import MCPTool, MCPToolCall

        call_order = []

        async def pre_hook(call: MCPToolCall) -> None:
            call_order.append("pre")

        async def post_hook(call: MCPToolCall):
            call_order.append("post")
            return call.result

        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
            pre_hook=pre_hook,
            post_hook=post_hook,
        )

        async def tool_execution(**kwargs):
            call_order.append("tool")
            return "result"

        mock_func = Mock()
        mock_func.entrypoint = tool_execution

        mock_agno = Mock()
        mock_agno.functions = {"tool": mock_func}

        mcp._agno_mcp_tools = mock_agno
        mcp._wrap_function_entrypoints()

        await mock_func.entrypoint()

        assert call_order == ["pre", "tool", "post"]
