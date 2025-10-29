# Stream event types for NDJSON streaming

from .messages import ExecutedCommand, ToolCall, Command
from typing import List, Optional, Literal
from pydantic import BaseModel

class StreamEvent(BaseModel):
    """Base for all stream events. Type field discriminates."""
    type: str

class ExecutedCommandsEvent(StreamEvent):
    """Commands that were just executed (before LLM call)"""
    type: Literal["executed_commands"] = "executed_commands"
    executed_cmds: List[ExecutedCommand]

class TextDeltaEvent(StreamEvent):
    """Streaming text token(s) from LLM"""
    type: Literal["text_delta"] = "text_delta"
    text: str

class ToolCallsEvent(StreamEvent):
    """Tool calls to show approval boxes"""
    type: Literal["tool_calls"] = "tool_calls"
    tool_calls: List[ToolCall]

class CommandsEvent(StreamEvent):
    """Commands to show approval boxes"""
    type: Literal["commands"] = "commands"
    commands: List[Command]

class DoneEvent(StreamEvent):
    """Stream finished successfully"""
    type: Literal["done"] = "done"
    stop_reason: Optional[str] = None

class ErrorEvent(StreamEvent):
    """Error occurred during streaming"""
    type: Literal["error"] = "error"
    error: str