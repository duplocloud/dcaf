# Stream event types for NDJSON streaming

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..discovery import DiscoveryPayload
from .messages import (
    Approval,
    Command,
    ExecutedApproval,
    ExecutedCommand,
    ExecutedToolCall,
    ToolCall,
)


class StreamEvent(BaseModel):
    """Base for all stream events. Type field discriminates."""

    type: str


class ExecutedCommandsEvent(StreamEvent):
    """Commands that were just executed (before LLM call)"""

    type: Literal["executed_commands"] = "executed_commands"
    executed_cmds: list[ExecutedCommand]


class ExecutedToolCallsEvent(StreamEvent):
    """Tool calls that were just executed (before LLM call)"""

    type: Literal["executed_tool_calls"] = "executed_tool_calls"
    executed_tool_calls: list[ExecutedToolCall]


class TextDeltaEvent(StreamEvent):
    """Streaming text token(s) from LLM"""

    type: Literal["text_delta"] = "text_delta"
    text: str


class ToolCallsEvent(StreamEvent):
    """Tool calls to show approval boxes"""

    type: Literal["tool_calls"] = "tool_calls"
    tool_calls: list[ToolCall]


class CommandsEvent(StreamEvent):
    """Commands to show approval boxes"""

    type: Literal["commands"] = "commands"
    commands: list[Command]


class ApprovalsEvent(StreamEvent):
    """Unified approval requests for frontend UI (commands, tool calls, etc.)"""

    type: Literal["approvals"] = "approvals"
    approvals: list[Approval]


class ExecutedApprovalsEvent(StreamEvent):
    """Results of executed approvals (before LLM call)"""

    type: Literal["executed_approvals"] = "executed_approvals"
    executed_approvals: list[ExecutedApproval]


class DoneEvent(StreamEvent):
    """Stream finished successfully"""

    type: Literal["done"] = "done"
    stop_reason: str | None = None
    meta_data: dict[str, Any] = Field(default_factory=dict)


class ErrorEvent(StreamEvent):
    """Error occurred during streaming"""

    type: Literal["error"] = "error"
    error: str


class IntermittentUpdateEvent(StreamEvent):
    """Interim status update (e.g. 'Thinking...', 'Calling tool: foo')"""

    type: Literal["intermittent_update"] = "intermittent_update"
    text: str
    content: dict = Field(default_factory=dict)


class DiscoveryEvent(StreamEvent):
    """Graph data for the Discovery panel (nodes and edges)."""

    type: Literal["discovery"] = "discovery"
    discovery: DiscoveryPayload


# Total event types: 11
# They are: executed_commands, executed_tool_calls, text_delta, tool_calls, commands, approvals, executed_approvals, done, error, intermittent_update, discovery
