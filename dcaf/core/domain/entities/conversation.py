"""Conversation aggregate root."""

from datetime import UTC, datetime
from typing import Any

from ..exceptions import ConversationBlocked, ToolCallNotFound
from ..value_objects.conversation_id import ConversationId
from ..value_objects.message_content import MessageContent
from ..value_objects.platform_context import PlatformContext
from .message import Message, MessageRole
from .tool_call import ToolCall


class Conversation:
    """
    Aggregate root for a conversation.

    The Conversation entity is the aggregate root that protects invariants:
    - Can't add messages while approvals are pending
    - Maintains message order
    - Tracks pending tool calls

    A conversation consists of a sequence of messages (turns) between
    a user and an assistant, with potential tool calls that may require
    human approval.

    Attributes:
        id: Unique identifier for this conversation
        messages: Ordered list of messages in the conversation
        pending_tool_calls: Tool calls awaiting approval
        context: Platform context for tool execution
    """

    def __init__(
        self,
        id: ConversationId,
        messages: list[Message] | None = None,
        context: PlatformContext | None = None,
    ) -> None:
        """
        Initialize a new Conversation.

        Args:
            id: Unique identifier
            messages: Initial messages (optional)
            context: Platform context (optional)
        """
        self._id = id
        self._messages: list[Message] = list(messages) if messages else []
        self._pending_tool_calls: list[ToolCall] = []
        self._context = context or PlatformContext.empty()
        self._created_at = datetime.now(UTC)
        self._updated_at = datetime.now(UTC)
        self._domain_events: list = []  # Will hold domain events

    # Properties

    @property
    def id(self) -> ConversationId:
        return self._id

    @property
    def messages(self) -> list[Message]:
        """Get a copy of the messages list."""
        return list(self._messages)

    @property
    def pending_tool_calls(self) -> list[ToolCall]:
        """Get tool calls that are pending approval."""
        return [tc for tc in self._pending_tool_calls if tc.is_pending]

    @property
    def all_tool_calls(self) -> list[ToolCall]:
        """Get all tracked tool calls."""
        return list(self._pending_tool_calls)

    @property
    def context(self) -> PlatformContext:
        return self._context

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    @property
    def has_pending_approvals(self) -> bool:
        """Check if there are any pending tool calls."""
        return len(self.pending_tool_calls) > 0

    @property
    def is_blocked(self) -> bool:
        """Check if conversation is blocked by pending approvals."""
        return self.has_pending_approvals

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @property
    def domain_events(self) -> list:
        """Get pending domain events."""
        return list(self._domain_events)

    # Commands

    def add_user_message(self, content: str | MessageContent) -> Message:
        """
        Add a user message to the conversation.

        Args:
            content: The message text (str) or MessageContent object

        Returns:
            The created message

        Raises:
            ConversationBlocked: If there are pending approvals

        Example:
            conversation.add_user_message("Hello, how are you?")
        """
        if self.has_pending_approvals:
            raise ConversationBlocked(
                "Cannot add user message while tool calls are pending approval. "
                "Please approve or reject pending tool calls first."
            )

        if isinstance(content, str):
            content = MessageContent.from_text(content)

        message = Message(role=MessageRole.USER, content=content)
        self._messages.append(message)
        self._updated_at = datetime.now(UTC)
        return message

    def add_assistant_message(self, content: str | MessageContent) -> Message:
        """
        Add an assistant message to the conversation.

        Args:
            content: The message text (str) or MessageContent object

        Returns:
            The created message

        Example:
            conversation.add_assistant_message("Hello! I'm here to help.")
        """
        if isinstance(content, str):
            content = MessageContent.from_text(content)

        message = Message(role=MessageRole.ASSISTANT, content=content)
        self._messages.append(message)
        self._updated_at = datetime.now(UTC)
        return message

    def add_system_message(self, content: str | MessageContent) -> Message:
        """
        Add a system message to the conversation.

        Args:
            content: The message text (str) or MessageContent object

        Returns:
            The created message

        Example:
            conversation.add_system_message("You are a helpful assistant.")
        """
        if isinstance(content, str):
            content = MessageContent.from_text(content)

        message = Message(role=MessageRole.SYSTEM, content=content)
        self._messages.append(message)
        self._updated_at = datetime.now(UTC)
        return message

    def add_message(self, message: Message) -> None:
        """
        Add a pre-constructed message to the conversation.

        Args:
            message: The message to add

        Raises:
            ConversationBlocked: If adding user message while approvals pending
        """
        if message.is_user_message and self.has_pending_approvals:
            raise ConversationBlocked(
                "Cannot add user message while tool calls are pending approval."
            )
        self._messages.append(message)
        self._updated_at = datetime.now(UTC)

    def request_tool_approval(self, tool_calls: list[ToolCall]) -> None:
        """
        Request approval for tool calls.

        This blocks the conversation until approvals are resolved.

        Args:
            tool_calls: Tool calls requiring approval
        """
        for tc in tool_calls:
            if tc.requires_approval and tc.is_pending:
                self._pending_tool_calls.append(tc)
        self._updated_at = datetime.now(UTC)

        # Record domain event
        from ..events import ApprovalRequested

        self._record_event(
            ApprovalRequested(
                conversation_id=self._id,
                tool_calls=tuple(tool_calls),
            )
        )

    def approve_tool_call(self, tool_call_id: str) -> ToolCall:
        """
        Approve a pending tool call.

        Args:
            tool_call_id: ID of the tool call to approve

        Returns:
            The approved tool call

        Raises:
            ToolCallNotFound: If tool call not found
        """
        tool_call = self._find_tool_call(tool_call_id)
        tool_call.approve()
        self._updated_at = datetime.now(UTC)
        return tool_call

    def reject_tool_call(self, tool_call_id: str, reason: str) -> ToolCall:
        """
        Reject a pending tool call.

        Args:
            tool_call_id: ID of the tool call to reject
            reason: Reason for rejection

        Returns:
            The rejected tool call

        Raises:
            ToolCallNotFound: If tool call not found
        """
        tool_call = self._find_tool_call(tool_call_id)
        tool_call.reject(reason)
        self._updated_at = datetime.now(UTC)
        return tool_call

    def complete_tool_call(self, tool_call_id: str, result: str) -> ToolCall:
        """
        Mark a tool call as completed with a result.

        Args:
            tool_call_id: ID of the tool call
            result: Execution result

        Returns:
            The completed tool call
        """
        tool_call = self._find_tool_call(tool_call_id)
        tool_call.start_execution()
        tool_call.complete(result)
        self._updated_at = datetime.now(UTC)

        # Record domain event
        from ..events import ToolExecuted

        self._record_event(
            ToolExecuted(
                conversation_id=self._id,
                tool_call=tool_call,
                result=result,
            )
        )

        return tool_call

    def fail_tool_call(self, tool_call_id: str, error: str) -> ToolCall:
        """
        Mark a tool call as failed.

        Args:
            tool_call_id: ID of the tool call
            error: Error message

        Returns:
            The failed tool call
        """
        tool_call = self._find_tool_call(tool_call_id)
        tool_call.start_execution()
        tool_call.fail(error)
        self._updated_at = datetime.now(UTC)
        return tool_call

    def update_context(self, context: PlatformContext) -> None:
        """Update the platform context."""
        self._context = context
        self._updated_at = datetime.now(UTC)

    def clear_events(self) -> list:
        """Clear and return domain events."""
        events = self._domain_events
        self._domain_events = []
        return events

    # Private methods

    def _find_tool_call(self, tool_call_id: str) -> ToolCall:
        """Find a tool call by ID."""
        for tc in self._pending_tool_calls:
            if str(tc.id) == tool_call_id:
                return tc
        raise ToolCallNotFound(tool_call_id)

    def _record_event(self, event: Any) -> None:
        """Record a domain event."""
        self._domain_events.append(event)

    # Identity

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Conversation):
            return NotImplemented
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __repr__(self) -> str:
        return (
            f"Conversation(id={self._id}, messages={len(self._messages)}, "
            f"pending_approvals={len(self.pending_tool_calls)})"
        )

    # Factory methods

    @classmethod
    def create(cls, context: PlatformContext | None = None) -> "Conversation":
        """Create a new conversation with a generated ID."""
        conversation = cls(
            id=ConversationId.generate(),
            context=context,
        )

        # Record domain event
        from ..events import ConversationStarted

        conversation._record_event(
            ConversationStarted(
                conversation_id=conversation.id,
            )
        )

        return conversation

    @classmethod
    def with_system_prompt(
        cls,
        system_prompt: str,
        context: PlatformContext | None = None,
    ) -> "Conversation":
        """
        Create a new conversation with a system prompt.

        Args:
            system_prompt: The system prompt text
            context: Optional platform context

        Returns:
            A new Conversation with the system message added

        Example:
            conversation = Conversation.with_system_prompt(
                "You are a Kubernetes assistant."
            )
        """
        conversation = cls.create(context=context)
        conversation.add_system_message(system_prompt)  # Now accepts str directly
        return conversation
