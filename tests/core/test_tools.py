"""Tests for Tool class and @tool decorator — approval_type field."""

import pytest
from pydantic import ValidationError

from dcaf.core.tools import tool


def test_tool_approval_type_defaults_to_tool_call():
    @tool(description="A test tool")
    def my_tool(x: str) -> str:
        return x

    assert my_tool.approval_type == "tool_call"


def test_tool_approval_type_can_be_set_to_command():
    @tool(description="Run a shell command", approval_type="command")
    def run_cmd(cmd: str) -> str:
        return cmd

    assert run_cmd.approval_type == "command"


def test_tool_approval_type_rejects_invalid_value():
    with pytest.raises(ValidationError):

        @tool(description="bad", approval_type="invalid")  # type: ignore[arg-type]
        def bad_tool(x: str) -> str:
            return x
