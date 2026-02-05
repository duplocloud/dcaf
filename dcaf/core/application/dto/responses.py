"""
Response DTOs for application use cases.

These DTOs are designed for full compatibility with the DuploCloud HelpDesk
messaging protocol, supporting both tool calls and terminal commands with
approval workflows.

Schema Reuse (Category 1):
    The following classes are imported from dcaf.schemas.messages to avoid
    duplication. They are re-exported with DTO aliases for backward compatibility:
    - FileObject (schema) → FileObject
    - Command (schema) → CommandDTO (alias)
    - ExecutedCommand (schema) → ExecutedCommandDTO (alias)
    - ExecutedToolCall (schema) → ExecutedToolCallDTO (alias)

    See docs/plans/schema-reuse-analysis.md for details.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# =============================================================================
# Import reusable schema classes from v2 core schemas
# =============================================================================
from dcaf.core.schemas.messages import (
    Command,
    ExecutedCommand,
    ExecutedToolCall,
)

# Backward-compatible aliases for DTO naming convention
# These allow existing code using CommandDTO, ExecutedCommandDTO, etc. to work
CommandDTO = Command
ExecutedCommandDTO = ExecutedCommand
ExecutedToolCallDTO = ExecutedToolCall


# =============================================================================
# Stream Event Types
# =============================================================================


class StreamEventType(Enum):
    """
    Types of streaming events.

    Matches the HelpDesk protocol event types:
    - text_delta: Streaming text from LLM
    - tool_calls: Tool calls needing approval
    - commands: Terminal commands needing approval
    - executed_tool_calls: Tool calls that were executed
    - executed_commands: Terminal commands that were executed
    - done: Stream finished
    - error: Error occurred

    Additional events for internal use:
    - tool_use_start/delta/end: Fine-grained tool streaming
    - message_start/end: Message lifecycle
    """

    # HelpDesk protocol events
    TEXT_DELTA = "text_delta"
    TOOL_CALLS = "tool_calls"
    COMMANDS = "commands"
    EXECUTED_TOOL_CALLS = "executed_tool_calls"
    EXECUTED_COMMANDS = "executed_commands"
    DONE = "done"
    ERROR = "error"

    # Fine-grained events (internal)
    TOOL_USE_START = "tool_use_start"
    TOOL_USE_DELTA = "tool_use_delta"
    TOOL_USE_END = "tool_use_end"
    MESSAGE_START = "message_start"
    MESSAGE_END = "message_end"


# =============================================================================
# Tool Call DTOs
# =============================================================================


@dataclass
class ToolCallDTO:
    """
    DTO representing a tool call in a response.

    This matches the HelpDesk protocol ToolCall structure.

    Attributes:
        id: Unique identifier for the tool call
        name: Name of the tool
        input: Input parameters for the tool
        execute: Whether approved for execution
        tool_description: Human-readable description of the tool
        input_description: Descriptions of input parameters
        intent: LLM's explanation of why it's calling this tool
        requires_approval: Whether this call needs approval
        status: Current status (pending, approved, executed, etc.)
        result: Execution result (if executed)
        error: Error message (if failed)
        rejection_reason: Why the user rejected (if rejected)
    """

    id: str
    name: str
    input: dict[str, Any]
    execute: bool = False
    tool_description: str = ""
    input_description: dict[str, Any] = field(default_factory=dict)
    intent: str | None = None
    requires_approval: bool = True
    status: str = "pending"
    result: str | None = None
    error: str | None = None
    rejection_reason: str | None = None

    # Alias for backward compatibility
    @property
    def description(self) -> str:
        return self.tool_description

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization (HelpDesk format)."""
        result = {
            "id": self.id,
            "name": self.name,
            "input": self.input,
            "execute": self.execute,
            "tool_description": self.tool_description,
            "input_description": self.input_description,
        }
        if self.intent:
            result["intent"] = self.intent
        if self.rejection_reason:
            result["rejection_reason"] = self.rejection_reason
        # Include status/result for internal tracking
        result["status"] = self.status
        if self.result:
            result["result"] = self.result
        if self.error:
            result["error"] = self.error
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolCallDTO":
        """Create from dictionary (HelpDesk format)."""
        return cls(
            id=data["id"],
            name=data["name"],
            input=data.get("input", {}),
            execute=data.get("execute", False),
            tool_description=data.get("tool_description", ""),
            input_description=data.get("input_description", {}),
            intent=data.get("intent"),
            requires_approval=not data.get("execute", False),
            status=data.get("status", "pending"),
            result=data.get("result"),
            error=data.get("error"),
            rejection_reason=data.get("rejection_reason"),
        )

    @classmethod
    def from_tool_call(cls, tool_call: Any) -> "ToolCallDTO":
        """Create from a domain ToolCall entity."""
        return cls(
            id=str(tool_call.id),
            name=tool_call.tool_name,
            input=tool_call.input.parameters,
            tool_description=tool_call.description,
            intent=tool_call.intent,
            requires_approval=tool_call.requires_approval,
            status=tool_call.status.value,
            result=tool_call.result,
            error=tool_call.error,
        )


# =============================================================================
# Data Container (HelpDesk Protocol)
# =============================================================================
# Note: ExecutedToolCallDTO is now imported from dcaf.schemas.messages (alias at top)


def _to_dict(obj: Any) -> dict[str, Any]:
    """
    Convert an object to a dictionary.

    Handles both Pydantic models (model_dump) and dataclasses with to_dict().
    """
    if hasattr(obj, "model_dump"):
        # Pydantic model
        return dict(obj.model_dump())
    elif hasattr(obj, "to_dict"):
        # Dataclass with to_dict method
        return dict(obj.to_dict())
    else:
        raise TypeError(f"Cannot convert {type(obj)} to dict")


@dataclass
class DataDTO:
    """
    Container for all actionable data in a message.

    This matches the HelpDesk protocol Data structure, which holds
    both pending and executed items for commands and tool calls,
    plus session state for persistence across conversation turns.

    Attributes:
        cmds: Terminal commands awaiting approval
        executed_cmds: Terminal commands that were executed
        tool_calls: Tool calls awaiting approval
        executed_tool_calls: Tool calls that were executed
        session: Session state that persists across conversation turns
    """

    cmds: list[CommandDTO] = field(default_factory=list)
    executed_cmds: list[ExecutedCommandDTO] = field(default_factory=list)
    tool_calls: list[ToolCallDTO] = field(default_factory=list)
    executed_tool_calls: list[ExecutedToolCallDTO] = field(default_factory=list)
    session: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "cmds": [_to_dict(c) for c in self.cmds],
            "executed_cmds": [_to_dict(c) for c in self.executed_cmds],
            "tool_calls": [_to_dict(t) for t in self.tool_calls],
            "executed_tool_calls": [_to_dict(t) for t in self.executed_tool_calls],
        }
        # Only include session if it has data
        if self.session:
            result["session"] = self.session  # type: ignore[assignment]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DataDTO":
        return cls(
            cmds=[Command(**c) for c in data.get("cmds", [])],
            executed_cmds=[ExecutedCommand(**c) for c in data.get("executed_cmds", [])],
            tool_calls=[ToolCallDTO.from_dict(t) for t in data.get("tool_calls", [])],
            executed_tool_calls=[
                ExecutedToolCall(**t) for t in data.get("executed_tool_calls", [])
            ],
            session=data.get("session", {}),
        )

    @property
    def has_pending_items(self) -> bool:
        """Check if there are any items awaiting approval."""
        pending_cmds = any(not c.execute for c in self.cmds)
        pending_tools = any(not t.execute for t in self.tool_calls)
        return pending_cmds or pending_tools

    @property
    def is_empty(self) -> bool:
        """Check if data container is empty."""
        return (
            not self.cmds
            and not self.executed_cmds
            and not self.tool_calls
            and not self.executed_tool_calls
        )


# =============================================================================
# Agent Response
# =============================================================================


@dataclass
class AgentResponse:
    """
    Response DTO from agent execution.

    This DTO is fully compatible with the HelpDesk messaging protocol,
    supporting both tool calls and terminal commands.

    Attributes:
        conversation_id: ID of the conversation
        text: Text content of the response (maps to 'content' in HelpDesk)
        data: Container with commands and tool calls
        has_pending_approvals: Whether there are items awaiting approval
        is_complete: Whether the agent turn is complete
        metadata: Optional additional metadata, including tracing context:
            - run_id: Unique execution run identifier
            - session_id: Session identifier for grouping runs
            - user_id: User identifier for tracking
            - request_id: HTTP request correlation ID
            - tenant_id: Tenant identifier
            - tenant_name: Tenant name

    Tracing Example:
        response = agent_service.execute(request)
        print(f"Run ID: {response.metadata.get('run_id')}")
        print(f"Session: {response.metadata.get('session_id')}")
    """

    conversation_id: str
    text: str | None = None
    data: DataDTO = field(default_factory=DataDTO)
    has_pending_approvals: bool = False
    is_complete: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    # Convenience accessors for backward compatibility
    @property
    def tool_calls(self) -> list[ToolCallDTO]:
        """Get all tool calls (pending and executed combined for approval)."""
        return self.data.tool_calls

    @property
    def commands(self) -> list[CommandDTO]:
        """Get all commands awaiting approval."""
        return self.data.cmds

    @property
    def pending_tool_calls(self) -> list[ToolCallDTO]:
        """Get tool calls that are pending approval."""
        return [tc for tc in self.data.tool_calls if not tc.execute]

    @property
    def pending_commands(self) -> list[CommandDTO]:
        """Get commands that are pending approval."""
        return [c for c in self.data.cmds if not c.execute]

    @property
    def approved_tool_calls(self) -> list[ToolCallDTO]:
        """Get tool calls that have been approved."""
        return [tc for tc in self.data.tool_calls if tc.execute]

    @property
    def approved_commands(self) -> list[CommandDTO]:
        """Get commands that have been approved."""
        return [c for c in self.data.cmds if c.execute]

    @property
    def executed_tool_calls(self) -> list[ExecutedToolCallDTO]:
        """Get tool calls that have been executed."""
        return self.data.executed_tool_calls

    @property
    def executed_commands(self) -> list[ExecutedCommandDTO]:
        """Get commands that have been executed."""
        return self.data.executed_cmds

    @property
    def session(self) -> dict[str, Any]:
        """
        Get the session data.

        Session state persists across conversation turns. The client
        should send this back in the next request to maintain state.

        Returns:
            Dictionary of session data

        Example:
            # After getting response
            session = response.session

            # Send session back in next request
            next_response = agent.run(
                messages=[...],
                session=session,
            )
        """
        return self.data.session

    def with_session(self, session: dict[str, Any]) -> "AgentResponse":
        """
        Return a copy with updated session data.

        Args:
            session: New session data

        Returns:
            New AgentResponse with updated session
        """
        new_data = DataDTO(
            cmds=self.data.cmds,
            executed_cmds=self.data.executed_cmds,
            tool_calls=self.data.tool_calls,
            executed_tool_calls=self.data.executed_tool_calls,
            session=session,
        )
        return AgentResponse(
            conversation_id=self.conversation_id,
            text=self.text,
            data=new_data,
            has_pending_approvals=self.has_pending_approvals,
            is_complete=self.is_complete,
            metadata=self.metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization (HelpDesk format)."""
        return {
            "conversation_id": self.conversation_id,
            "content": self.text or "",
            "data": self.data.to_dict(),
            "has_pending_approvals": self.has_pending_approvals,
            "is_complete": self.is_complete,
            "metadata": self.metadata,
        }

    def to_helpdesk_message(self, role: str = "assistant") -> dict[str, Any]:
        """
        Convert to full HelpDesk message format.

        Returns a message dict compatible with the HelpDesk protocol.

        Note: For a Pydantic-validated version, use to_agent_message() instead.
        """
        return {
            "role": role,
            "content": self.text or "",
            "data": self.data.to_dict(),
            "meta_data": self.metadata,
        }

    def to_agent_message(
        self,
        agent_name: str | None = None,
        agent_id: str | None = None,
        include_timestamp: bool = True,
    ) -> Any:
        """
        Convert to schema's AgentMessage (Pydantic model).

        This creates a validated Pydantic model that can be serialized to JSON
        for the HelpDesk protocol.

        Args:
            agent_name: Optional agent name for identification
            agent_id: Optional agent ID for identification
            include_timestamp: Whether to include timestamp (default: True)

        Returns:
            AgentMessage from dcaf.core.schemas.messages

        Example:
            response = agent_service.execute(request)
            message = response.to_agent_message(agent_name="k8s-agent")
            json_data = message.model_dump()  # Serialize to JSON
        """
        from dcaf.core.schemas.messages import AgentMessage

        return AgentMessage.from_agent_response(
            self,
            include_timestamp=include_timestamp,
            agent_name=agent_name,
            agent_id=agent_id,
        )

    @classmethod
    def text_only(cls, conversation_id: str, text: str) -> "AgentResponse":
        """Create a text-only response."""
        return cls(
            conversation_id=conversation_id,
            text=text,
            is_complete=True,
        )

    @classmethod
    def with_tool_calls(
        cls,
        conversation_id: str,
        tool_calls: list[ToolCallDTO],
        text: str | None = None,
    ) -> "AgentResponse":
        """Create a response with tool calls awaiting approval."""
        data = DataDTO(tool_calls=tool_calls)
        pending = any(not tc.execute for tc in tool_calls)
        return cls(
            conversation_id=conversation_id,
            text=text,
            data=data,
            has_pending_approvals=pending,
            is_complete=not pending,
        )

    @classmethod
    def with_commands(
        cls,
        conversation_id: str,
        commands: list[CommandDTO],
        text: str | None = None,
    ) -> "AgentResponse":
        """Create a response with commands awaiting approval."""
        data = DataDTO(cmds=commands)
        pending = any(not c.execute for c in commands)
        return cls(
            conversation_id=conversation_id,
            text=text,
            data=data,
            has_pending_approvals=pending,
            is_complete=not pending,
        )

    @classmethod
    def with_data(
        cls,
        conversation_id: str,
        data: DataDTO,
        text: str | None = None,
    ) -> "AgentResponse":
        """Create a response with full data container."""
        return cls(
            conversation_id=conversation_id,
            text=text,
            data=data,
            has_pending_approvals=data.has_pending_items,
            is_complete=not data.has_pending_items,
        )


# =============================================================================
# Stream Events
# =============================================================================


@dataclass
class StreamEvent:
    """
    A single event in a streaming response.

    Fully compatible with HelpDesk protocol stream events.

    Attributes:
        event_type: Type of the event
        data: Event-specific data
        index: Optional index for ordering
    """

    event_type: StreamEventType
    data: dict[str, Any] = field(default_factory=dict)
    index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to HelpDesk stream event format."""
        result = {"type": self.event_type.value}
        result.update(self.data)
        return result

    # -------------------------------------------------------------------------
    # HelpDesk Protocol Events
    # -------------------------------------------------------------------------

    @classmethod
    def text_delta(cls, text: str, index: int = 0) -> "StreamEvent":
        """Create a text delta event."""
        return cls(
            event_type=StreamEventType.TEXT_DELTA,
            data={"text": text},
            index=index,
        )

    @classmethod
    def tool_calls_event(cls, tool_calls: list[ToolCallDTO]) -> "StreamEvent":
        """Create a tool_calls event for approval boxes."""
        return cls(
            event_type=StreamEventType.TOOL_CALLS,
            data={"tool_calls": [_to_dict(tc) for tc in tool_calls]},
        )

    @classmethod
    def commands_event(cls, commands: list[CommandDTO]) -> "StreamEvent":
        """Create a commands event for approval boxes."""
        return cls(
            event_type=StreamEventType.COMMANDS,
            data={"commands": [_to_dict(c) for c in commands]},
        )

    @classmethod
    def executed_tool_calls_event(
        cls,
        executed_tool_calls: list[ExecutedToolCallDTO],
    ) -> "StreamEvent":
        """Create an executed_tool_calls event."""
        return cls(
            event_type=StreamEventType.EXECUTED_TOOL_CALLS,
            data={"executed_tool_calls": [_to_dict(t) for t in executed_tool_calls]},
        )

    @classmethod
    def executed_commands_event(
        cls,
        executed_cmds: list[ExecutedCommandDTO],
    ) -> "StreamEvent":
        """Create an executed_commands event."""
        return cls(
            event_type=StreamEventType.EXECUTED_COMMANDS,
            data={"executed_cmds": [_to_dict(c) for c in executed_cmds]},
        )

    @classmethod
    def done(cls, stop_reason: str | None = None) -> "StreamEvent":
        """Create a done event."""
        data = {}
        if stop_reason:
            data["stop_reason"] = stop_reason
        return cls(event_type=StreamEventType.DONE, data=data)

    @classmethod
    def error(cls, message: str, code: str | None = None) -> "StreamEvent":
        """Create an error event."""
        data = {"error": message}
        if code:
            data["code"] = code
        return cls(event_type=StreamEventType.ERROR, data=data)

    # -------------------------------------------------------------------------
    # Fine-grained Events (for detailed streaming)
    # -------------------------------------------------------------------------

    @classmethod
    def tool_use_start(
        cls,
        tool_call_id: str,
        tool_name: str,
        index: int = 0,
    ) -> "StreamEvent":
        """Create a tool use start event."""
        return cls(
            event_type=StreamEventType.TOOL_USE_START,
            data={"tool_call_id": tool_call_id, "tool_name": tool_name},
            index=index,
        )

    @classmethod
    def tool_use_delta(
        cls,
        tool_call_id: str,
        input_delta: str,
        index: int = 0,
    ) -> "StreamEvent":
        """Create a tool use delta event."""
        return cls(
            event_type=StreamEventType.TOOL_USE_DELTA,
            data={"tool_call_id": tool_call_id, "input_delta": input_delta},
            index=index,
        )

    @classmethod
    def tool_use_end(cls, tool_call_id: str, index: int = 0) -> "StreamEvent":
        """Create a tool use end event."""
        return cls(
            event_type=StreamEventType.TOOL_USE_END,
            data={"tool_call_id": tool_call_id},
            index=index,
        )

    @classmethod
    def message_start(cls) -> "StreamEvent":
        """Create a message start event."""
        return cls(event_type=StreamEventType.MESSAGE_START)

    @classmethod
    def message_end(cls, response: AgentResponse) -> "StreamEvent":
        """Create a message end event with the final response."""
        return cls(
            event_type=StreamEventType.MESSAGE_END,
            data={"response": response.to_dict()},
        )
