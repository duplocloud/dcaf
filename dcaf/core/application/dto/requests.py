"""Request DTOs for application use cases."""

from dataclasses import dataclass, field
from typing import Any

from ...domain.value_objects import ConversationId, PlatformContext


@dataclass
class ToolCallApproval:
    """
    Approval decision for a single tool call.

    Attributes:
        tool_call_id: ID of the tool call
        approved: Whether the tool call is approved
        rejection_reason: Reason for rejection (if not approved)
    """

    tool_call_id: str
    approved: bool
    rejection_reason: str | None = None


@dataclass
class AgentRequest:
    """
    Request DTO for agent execution.

    This DTO carries all the information needed to execute
    an agent turn, including the user message, conversation
    context, and available tools.

    Attributes:
        content: The user's message content
        messages: Optional conversation history (list of message dicts)
        conversation_id: Optional ID of existing conversation
        context: Platform context for tool execution
        tools: List of tools available to the agent
        system_prompt: Optional system prompt
        static_system: Static portion of system prompt (for caching)
        dynamic_system: Dynamic portion of system prompt (not cached)
        stream: Whether to stream the response
        session: Session data that persists across conversation turns
        user_id: User identifier for tracing and observability
        session_id: Session identifier for grouping related runs
        run_id: Unique execution run identifier
        request_id: HTTP request correlation ID

    Example with message history:
        request = AgentRequest(
            content="What else can you tell me?",
            messages=[
                {"role": "user", "content": "What pods are running?"},
                {"role": "assistant", "content": "There are 3 pods: nginx, redis, api"},
            ],
            tools=[...],
        )

    Example with session:
        request = AgentRequest(
            content="Continue the wizard",
            session={"wizard_step": 2, "user_name": "Alice"},
        )

    Example with tracing:
        request = AgentRequest(
            content="Deploy my app",
            user_id="user-123",
            session_id="session-abc",
            run_id="run-xyz",
            request_id="req-456",
            tools=[...],
        )
    """

    content: str
    messages: list[dict[str, Any]] | None = None  # Conversation history from external source
    conversation_id: str | None = None
    context: dict[str, Any] | None = None
    tools: list[Any] = field(default_factory=list)  # List[Tool]
    system_prompt: str | None = None
    static_system: str | None = None  # Static system prompt (cached)
    dynamic_system: str | None = None  # Dynamic system prompt (not cached)
    stream: bool = False
    session: dict[str, Any] | None = None  # Session data for persistence

    # Tracing fields for distributed tracing and observability
    user_id: str | None = None  # User making the request
    session_id: str | None = None  # Session grouping related runs
    run_id: str | None = None  # Unique identifier for this execution run
    request_id: str | None = None  # HTTP request correlation ID

    def get_conversation_id(self) -> ConversationId | None:
        """Get the conversation ID as a value object."""
        if self.conversation_id:
            return ConversationId(self.conversation_id)
        return None

    def get_platform_context(self) -> PlatformContext:
        """
        Get the platform context as a value object.

        If tracing fields (user_id, session_id, run_id, request_id) are set
        on the request, they will be automatically merged into the platform
        context for propagation to the agent runtime.
        """
        ctx = PlatformContext.from_dict(self.context) if self.context else PlatformContext.empty()

        # Merge tracing fields into platform context if provided
        if any([self.user_id, self.session_id, self.run_id, self.request_id]):
            ctx = ctx.with_tracing(
                user_id=self.user_id,
                session_id=self.session_id,
                run_id=self.run_id,
                request_id=self.request_id,
            )

        return ctx

    def get_session(self) -> dict[str, Any]:
        """Get the session data as a dict."""
        return self.session or {}


@dataclass
class ApprovalRequest:
    """
    Request DTO for approving/rejecting tool calls.

    This DTO carries the user's approval decisions for
    pending tool calls.

    Attributes:
        conversation_id: ID of the conversation
        approvals: List of approval decisions
    """

    conversation_id: str
    approvals: list[ToolCallApproval]

    def get_conversation_id(self) -> ConversationId:
        """Get the conversation ID as a value object."""
        return ConversationId(self.conversation_id)

    @property
    def approved_ids(self) -> list[str]:
        """Get IDs of approved tool calls."""
        return [a.tool_call_id for a in self.approvals if a.approved]

    @property
    def rejected_ids(self) -> list[str]:
        """Get IDs of rejected tool calls."""
        return [a.tool_call_id for a in self.approvals if not a.approved]
