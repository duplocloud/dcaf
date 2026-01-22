"""Domain-specific exceptions."""


class DomainException(Exception):
    """Base exception for all domain errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConversationBlocked(DomainException):
    """Raised when conversation cannot proceed due to pending approvals."""

    def __init__(self, message: str = "Conversation blocked by pending approvals"):
        super().__init__(message)


class InvalidStateTransition(DomainException):
    """Raised when an invalid state transition is attempted."""

    def __init__(
        self, message: str, current_state: str | None = None, attempted_state: str | None = None
    ):
        super().__init__(
            message,
            details={
                "current_state": current_state,
                "attempted_state": attempted_state,
            },
        )
        self.current_state = current_state
        self.attempted_state = attempted_state


class ToolCallNotFound(DomainException):
    """Raised when a tool call cannot be found."""

    def __init__(self, tool_call_id: str):
        super().__init__(
            f"Tool call not found: {tool_call_id}", details={"tool_call_id": tool_call_id}
        )
        self.tool_call_id = tool_call_id


class ToolNotFound(DomainException):
    """Raised when a tool cannot be found by name."""

    def __init__(self, tool_name: str):
        super().__init__(f"Tool not found: {tool_name}", details={"tool_name": tool_name})
        self.tool_name = tool_name


class InvalidToolInput(DomainException):
    """Raised when tool input is invalid."""

    def __init__(self, message: str, tool_name: str | None = None):
        super().__init__(message, details={"tool_name": tool_name})
        self.tool_name = tool_name
