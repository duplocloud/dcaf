"""ToolCall entity with identity and state transitions."""

from datetime import UTC, datetime
from enum import Enum

from ..exceptions import InvalidStateTransition
from ..value_objects.tool_call_id import ToolCallId
from ..value_objects.tool_input import ToolInput


class ToolCallStatus(Enum):
    """Status of a tool call in its lifecycle."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolCall:
    """
    Entity with identity and state transitions.

    A ToolCall represents a request to execute a tool with specific inputs.
    It has a lifecycle: PENDING -> APPROVED -> EXECUTING -> COMPLETED
    or PENDING -> REJECTED.

    Attributes:
        id: Unique identifier for this tool call
        tool_name: Name of the tool to execute
        input: Input parameters for the tool
        status: Current status in the lifecycle
        description: Human-readable description of what this tool does
        intent: LLM's explanation of why it's calling this tool
        rejection_reason: Reason for rejection (if rejected)
        result: Execution result (if completed)
        error: Error message (if failed)
    """

    def __init__(
        self,
        id: ToolCallId,
        tool_name: str,
        input: ToolInput,
        description: str = "",
        intent: str | None = None,
        requires_approval: bool = True,
    ) -> None:
        """
        Initialize a new ToolCall.

        Args:
            id: Unique identifier
            tool_name: Name of the tool
            input: Input parameters
            description: Human-readable tool description
            intent: LLM's intent for calling this tool
            requires_approval: Whether this call needs human approval
        """
        self._id = id
        self._tool_name = tool_name
        self._input = input
        self._description = description
        self._intent = intent
        self._requires_approval = requires_approval
        self._status = ToolCallStatus.PENDING
        self._rejection_reason: str | None = None
        self._result: str | None = None
        self._error: str | None = None
        self._created_at = datetime.now(UTC)
        self._updated_at = datetime.now(UTC)

    # Properties (read-only access)

    @property
    def id(self) -> ToolCallId:
        return self._id

    @property
    def tool_name(self) -> str:
        return self._tool_name

    @property
    def input(self) -> ToolInput:
        return self._input

    @property
    def description(self) -> str:
        return self._description

    @property
    def intent(self) -> str | None:
        return self._intent

    @property
    def requires_approval(self) -> bool:
        return self._requires_approval

    @property
    def status(self) -> ToolCallStatus:
        return self._status

    @property
    def rejection_reason(self) -> str | None:
        return self._rejection_reason

    @property
    def result(self) -> str | None:
        return self._result

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    # Status predicates

    @property
    def is_pending(self) -> bool:
        return self._status == ToolCallStatus.PENDING

    @property
    def is_approved(self) -> bool:
        return self._status == ToolCallStatus.APPROVED

    @property
    def is_rejected(self) -> bool:
        return self._status == ToolCallStatus.REJECTED

    @property
    def is_completed(self) -> bool:
        return self._status == ToolCallStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        return self._status == ToolCallStatus.FAILED

    @property
    def is_terminal(self) -> bool:
        """Check if the tool call is in a terminal state."""
        return self._status in (
            ToolCallStatus.COMPLETED,
            ToolCallStatus.REJECTED,
            ToolCallStatus.FAILED,
        )

    # State transitions

    def approve(self) -> None:
        """
        Transition from PENDING to APPROVED.

        Raises:
            InvalidStateTransition: If not in PENDING state
        """
        if self._status != ToolCallStatus.PENDING:
            raise InvalidStateTransition(
                f"Can only approve pending tool calls, current status: {self._status.value}",
                current_state=self._status.value,
                attempted_state=ToolCallStatus.APPROVED.value,
            )
        self._status = ToolCallStatus.APPROVED
        self._updated_at = datetime.now(UTC)

    def reject(self, reason: str) -> None:
        """
        Transition from PENDING to REJECTED.

        Args:
            reason: The reason for rejection

        Raises:
            InvalidStateTransition: If not in PENDING state
        """
        if self._status != ToolCallStatus.PENDING:
            raise InvalidStateTransition(
                f"Can only reject pending tool calls, current status: {self._status.value}",
                current_state=self._status.value,
                attempted_state=ToolCallStatus.REJECTED.value,
            )
        self._status = ToolCallStatus.REJECTED
        self._rejection_reason = reason
        self._updated_at = datetime.now(UTC)

    def start_execution(self) -> None:
        """
        Transition from APPROVED to EXECUTING.

        Raises:
            InvalidStateTransition: If not in APPROVED state
        """
        if self._status != ToolCallStatus.APPROVED:
            raise InvalidStateTransition(
                f"Can only execute approved tool calls, current status: {self._status.value}",
                current_state=self._status.value,
                attempted_state=ToolCallStatus.EXECUTING.value,
            )
        self._status = ToolCallStatus.EXECUTING
        self._updated_at = datetime.now(UTC)

    def complete(self, result: str) -> None:
        """
        Transition from EXECUTING to COMPLETED.

        Args:
            result: The execution result

        Raises:
            InvalidStateTransition: If not in EXECUTING state
        """
        if self._status != ToolCallStatus.EXECUTING:
            raise InvalidStateTransition(
                f"Can only complete executing tool calls, current status: {self._status.value}",
                current_state=self._status.value,
                attempted_state=ToolCallStatus.COMPLETED.value,
            )
        self._status = ToolCallStatus.COMPLETED
        self._result = result
        self._updated_at = datetime.now(UTC)

    def fail(self, error: str) -> None:
        """
        Transition from EXECUTING to FAILED.

        Args:
            error: The error message

        Raises:
            InvalidStateTransition: If not in EXECUTING state
        """
        if self._status != ToolCallStatus.EXECUTING:
            raise InvalidStateTransition(
                f"Can only fail executing tool calls, current status: {self._status.value}",
                current_state=self._status.value,
                attempted_state=ToolCallStatus.FAILED.value,
            )
        self._status = ToolCallStatus.FAILED
        self._error = error
        self._updated_at = datetime.now(UTC)

    def auto_approve(self) -> None:
        """
        Auto-approve a tool call that doesn't require approval.

        This is used when requires_approval is False to move
        directly to APPROVED state.
        """
        if not self._requires_approval and self._status == ToolCallStatus.PENDING:
            self._status = ToolCallStatus.APPROVED
            self._updated_at = datetime.now(UTC)

    # Identity

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ToolCall):
            return NotImplemented
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __repr__(self) -> str:
        return (
            f"ToolCall(id={self._id}, tool_name={self._tool_name!r}, status={self._status.value})"
        )
