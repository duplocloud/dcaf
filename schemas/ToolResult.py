from typing import Any, TypedDict


class ToolResult(TypedDict):
    type: str
    tool_use_id: str
    content: Any