"""
Integration tests for MCP tool approval flow.

Connects to a real test MCP server (tests/mcp_test_server.py) via stdio
and verifies that exclude_tools, auto_approve_tools, and default approval
behaviors work correctly end-to-end.
"""

import os
import sys

import pytest

from dcaf.mcp import MCPTool

# Path to the test MCP server, resolved relative to this file
SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "mcp_test_server.py")
PYTHON = sys.executable


@pytest.fixture
async def mcp_connected():
    """Create and connect an MCPTool to the test server with all three tiers configured."""
    mcp = MCPTool(
        command=f"{PYTHON} {SERVER_SCRIPT}",
        transport="stdio",
        exclude_tools=["admin_*"],
        auto_approve_tools=["*_get*", "*_read*", "*_list*"],
    )
    async with mcp:
        yield mcp


@pytest.mark.asyncio
class TestBlockedTools:
    """Verify exclude_tools prevents tools from appearing."""

    async def test_admin_reset_not_available(self, mcp_connected):
        """Blocked tool should not appear in available tools."""
        tool_names = mcp_connected.get_tool_names()
        assert "admin_reset" not in tool_names

    async def test_other_tools_still_available(self, mcp_connected):
        """Non-blocked tools should still be available."""
        tool_names = mcp_connected.get_tool_names()
        assert len(tool_names) == 8  # 9 total minus 1 blocked


@pytest.mark.asyncio
class TestAutoApprovedTools:
    """Verify auto_approve_tools glob patterns mark tools as auto-approved."""

    @pytest.mark.parametrize("tool_name", ["user_get", "file_read", "items_list"])
    async def test_read_like_tools_auto_approved(self, mcp_connected, tool_name):
        """Tools matching *_get*, *_read*, *_list* should NOT require confirmation."""
        func = mcp_connected._agno_mcp_tools.functions[tool_name]
        requires = getattr(func, "requires_confirmation", None)
        assert requires is not True, (
            f"{tool_name} should be auto-approved but has requires_confirmation={requires}"
        )


@pytest.mark.asyncio
class TestApprovalRequiredTools:
    """Verify tools not matching any auto-approve pattern require confirmation."""

    @pytest.mark.parametrize(
        "tool_name",
        ["user_delete", "file_write", "data_export", "config_update", "system_status"],
    )
    async def test_write_like_tools_require_approval(self, mcp_connected, tool_name):
        """Tools not matching auto-approve patterns should require confirmation."""
        func = mcp_connected._agno_mcp_tools.functions[tool_name]
        assert func.requires_confirmation is True, (
            f"{tool_name} should require approval but has "
            f"requires_confirmation={func.requires_confirmation}"
        )


@pytest.mark.asyncio
class TestToolExecution:
    """Verify tools actually execute and return expected responses."""

    async def test_auto_approved_tool_returns_response(self, mcp_connected):
        """An auto-approved tool should execute and return a response."""
        func = mcp_connected._agno_mcp_tools.functions["user_get"]
        result = await func.entrypoint(user_id="123")
        assert "user_get" in str(result)
        assert "123" in str(result)

    async def test_approval_required_tool_returns_response(self, mcp_connected):
        """A tool requiring approval should still execute when called directly."""
        func = mcp_connected._agno_mcp_tools.functions["user_delete"]
        result = await func.entrypoint(user_id="456")
        assert "user_delete" in str(result)
        assert "456" in str(result)


@pytest.mark.asyncio
class TestGlobPatternEdgeCases:
    """Test glob pattern matching with different configurations."""

    async def test_wildcard_all_auto_approves_everything(self):
        """Pattern ['*'] should auto-approve all tools."""
        mcp = MCPTool(
            command=f"{PYTHON} {SERVER_SCRIPT}",
            transport="stdio",
            auto_approve_tools=["*"],
        )
        async with mcp:
            for tool_name, func in mcp._agno_mcp_tools.functions.items():
                requires = getattr(func, "requires_confirmation", None)
                assert requires is not True, f"{tool_name} should be auto-approved with '*' pattern"

    async def test_empty_patterns_requires_all_approval(self):
        """Empty auto_approve_tools list should require approval for all tools."""
        mcp = MCPTool(
            command=f"{PYTHON} {SERVER_SCRIPT}",
            transport="stdio",
            auto_approve_tools=[],
        )
        async with mcp:
            for tool_name, func in mcp._agno_mcp_tools.functions.items():
                assert func.requires_confirmation is True, (
                    f"{tool_name} should require approval with empty patterns"
                )

    async def test_no_auto_approve_means_no_confirmation_required(self):
        """When auto_approve_tools is None (default), no tools require confirmation."""
        mcp = MCPTool(
            command=f"{PYTHON} {SERVER_SCRIPT}",
            transport="stdio",
        )
        async with mcp:
            for tool_name, func in mcp._agno_mcp_tools.functions.items():
                requires = getattr(func, "requires_confirmation", None)
                assert requires is not True, (
                    f"{tool_name} should not require confirmation when auto_approve_tools is None"
                )
