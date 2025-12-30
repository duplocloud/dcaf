"""Domain events for the DCAF framework."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from abc import ABC

from ..value_objects.conversation_id import ConversationId


@dataclass(frozen=True)
class DomainEvent(ABC):
    """
    Base class for all domain events.
    
    Domain events are immutable records of something significant
    that happened in the domain. They include a timestamp and
    can be used for audit trails, event sourcing, or triggering
    side effects.
    """
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def event_type(self) -> str:
        """Return the event type name."""
        return self.__class__.__name__


@dataclass(frozen=True)
class ConversationStarted(DomainEvent):
    """Event raised when a new conversation is started."""
    
    conversation_id: ConversationId = field(default=None)  # type: ignore
    
    def __post_init__(self) -> None:
        if self.conversation_id is None:
            raise ValueError("conversation_id is required")


@dataclass(frozen=True)
class ApprovalRequested(DomainEvent):
    """
    Event raised when tool calls require human approval.
    
    This event indicates that the conversation is now blocked
    until approvals are resolved.
    """
    
    conversation_id: ConversationId = field(default=None)  # type: ignore
    tool_calls: tuple = field(default_factory=tuple)  # Tuple for immutability
    
    def __post_init__(self) -> None:
        if self.conversation_id is None:
            raise ValueError("conversation_id is required")
        # Convert list to tuple if necessary
        if isinstance(self.tool_calls, list):
            object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
    
    @property
    def tool_call_ids(self) -> List[str]:
        """Get the IDs of all tool calls requiring approval."""
        return [str(tc.id) for tc in self.tool_calls]
    
    @property
    def tool_call_count(self) -> int:
        """Get the number of tool calls requiring approval."""
        return len(self.tool_calls)


@dataclass(frozen=True)
class ToolCallApproved(DomainEvent):
    """Event raised when a tool call is approved."""
    
    conversation_id: ConversationId = field(default=None)  # type: ignore
    tool_call_id: str = ""
    tool_name: str = ""
    approved_by: Optional[str] = None
    
    def __post_init__(self) -> None:
        if self.conversation_id is None:
            raise ValueError("conversation_id is required")
        if not self.tool_call_id:
            raise ValueError("tool_call_id is required")


@dataclass(frozen=True)
class ToolCallRejected(DomainEvent):
    """Event raised when a tool call is rejected."""
    
    conversation_id: ConversationId = field(default=None)  # type: ignore
    tool_call_id: str = ""
    tool_name: str = ""
    reason: str = ""
    rejected_by: Optional[str] = None
    
    def __post_init__(self) -> None:
        if self.conversation_id is None:
            raise ValueError("conversation_id is required")
        if not self.tool_call_id:
            raise ValueError("tool_call_id is required")


@dataclass(frozen=True)
class ToolExecuted(DomainEvent):
    """Event raised when a tool is successfully executed."""
    
    conversation_id: ConversationId = field(default=None)  # type: ignore
    tool_call: object = field(default=None)  # ToolCall type, but avoiding circular import
    result: str = ""
    execution_time_ms: Optional[int] = None
    
    def __post_init__(self) -> None:
        if self.conversation_id is None:
            raise ValueError("conversation_id is required")
    
    @property
    def tool_call_id(self) -> str:
        """Get the tool call ID."""
        return str(self.tool_call.id) if self.tool_call else ""
    
    @property
    def tool_name(self) -> str:
        """Get the tool name."""
        return self.tool_call.tool_name if self.tool_call else ""


@dataclass(frozen=True)
class ToolExecutionFailed(DomainEvent):
    """Event raised when a tool execution fails."""
    
    conversation_id: ConversationId = field(default=None)  # type: ignore
    tool_call_id: str = ""
    tool_name: str = ""
    error: str = ""
    
    def __post_init__(self) -> None:
        if self.conversation_id is None:
            raise ValueError("conversation_id is required")
        if not self.tool_call_id:
            raise ValueError("tool_call_id is required")
