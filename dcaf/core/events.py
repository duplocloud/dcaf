# dcaf/core/events.py
"""
Unified Event System for DCAF.

This module provides a simple, unified event system for subscribing to
real-time events during agent execution. Events include tool calls,
text streaming, reasoning steps, and more.

Example:
    from dcaf import Agent

    agent = Agent(tools=[weather_tool])

    @agent.on("tool_call_started")
    async def handle_tool_start(event):
        print(f"Calling {event.tool_name}...")

    @agent.on("text_delta")
    async def handle_text(event):
        print(event.text, end="")
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class Event:
    """
    A single event emitted during agent execution.

    Events are lightweight, ephemeral notifications about what's happening
    in real-time. They are not persisted - use them for UI updates,
    logging, or triggering side effects.

    Attributes:
        type: The event type (e.g., "tool_call_started", "text_delta")
        data: Event-specific payload
        timestamp: When the event occurred

    Example:
        event = Event(
            type="tool_call_started",
            data={"tool_name": "weather", "tool_call_id": "abc123"}
        )
        print(f"Calling {event.tool_name}...")
    """

    type: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Convenience accessors for common fields

    @property
    def tool_name(self) -> str | None:
        """Get the tool name, if present."""
        return self.data.get("tool_name")

    @property
    def tool_call_id(self) -> str | None:
        """Get the tool call ID, if present."""
        return self.data.get("tool_call_id")

    @property
    def text(self) -> str | None:
        """Get the text content, if present."""
        return self.data.get("text")

    @property
    def content(self) -> str | None:
        """Get the content (for reasoning steps), if present."""
        return self.data.get("content")

    @property
    def error(self) -> str | None:
        """Get the error message, if present."""
        return self.data.get("error")

    @property
    def result(self) -> Any | None:
        """Get the result (for tool completions), if present."""
        return self.data.get("result")


# =============================================================================
# Event Type Constants
# =============================================================================
# These constants are provided for discoverability and autocomplete.
# You can also use plain strings - they're equivalent.

# Tool lifecycle
TOOL_CALL_STARTED = "tool_call_started"
"""Fired when a tool begins execution. Data: tool_name, tool_call_id, arguments"""

TOOL_CALL_COMPLETED = "tool_call_completed"
"""Fired when a tool finishes. Data: tool_name, tool_call_id, result"""

TOOL_CALL_FAILED = "tool_call_failed"
"""Fired when a tool execution fails. Data: tool_name, tool_call_id, error"""

# Streaming content
TEXT_DELTA = "text_delta"
"""Fired for each chunk of streamed text. Data: text"""

# Reasoning (model-dependent)
REASONING_STARTED = "reasoning_started"
"""Fired when model begins reasoning. Data: (empty)"""

REASONING_STEP = "reasoning_step"
"""Fired for each reasoning step. Data: content"""

REASONING_COMPLETED = "reasoning_completed"
"""Fired when reasoning finishes. Data: (empty)"""

# Message lifecycle
MESSAGE_START = "message_start"
"""Fired when a new message begins. Data: (empty)"""

MESSAGE_END = "message_end"
"""Fired when a message completes. Data: response (dict)"""

# Errors
ERROR = "error"
"""Fired when an error occurs. Data: error, code (optional)"""
