"""
Tests for DCAF MCPTool integration.

These tests verify:
1. MCPTool initialization and parameter validation
2. The adapter correctly recognizes MCPTool instances
3. MCPTool can be used alongside regular DCAF tools
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

    def test_in_all(self):
        """Should be in __all__."""
        from dcaf import mcp

        assert "MCPTool" in mcp.__all__


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
