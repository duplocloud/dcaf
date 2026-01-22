"""ApprovalService - handle approval decisions for tool calls."""

import logging

from ...domain.exceptions import ToolCallNotFound
from ...domain.value_objects import ConversationId
from ..dto.requests import ApprovalRequest
from ..dto.responses import AgentResponse, ToolCallDTO
from ..ports.conversation_repository import ConversationRepository
from ..ports.event_publisher import EventPublisher

logger = logging.getLogger(__name__)


class ApprovalService:
    """
    Application service for handling tool call approvals.

    This service handles:
    1. Processing approval decisions
    2. Updating tool call states
    3. Unblocking conversations

    Example:
        approval_service = ApprovalService(
            conversations=conversations,
            events=events,
        )

        response = approval_service.execute(ApprovalRequest(
            conversation_id="conv-123",
            approvals=[
                ToolCallApproval(tool_call_id="tc-1", approved=True),
                ToolCallApproval(tool_call_id="tc-2", approved=False, rejection_reason="Too risky"),
            ],
        ))
    """

    def __init__(
        self,
        conversations: ConversationRepository,
        events: EventPublisher | None = None,
    ) -> None:
        """
        Initialize the service.

        Args:
            conversations: Repository for conversation persistence
            events: Optional event publisher
        """
        self._conversations = conversations
        self._events = events

    def execute(self, request: ApprovalRequest) -> AgentResponse:
        """
        Process approval decisions for tool calls.

        Args:
            request: The approval request with decisions

        Returns:
            AgentResponse with updated tool call states

        Raises:
            ValueError: If conversation not found
            ToolCallNotFound: If a tool call ID is invalid
        """
        # 1. Load conversation
        conv_id = request.get_conversation_id()
        conversation = self._conversations.get(conv_id)

        if not conversation:
            raise ValueError(f"Conversation not found: {request.conversation_id}")

        # 2. Process each approval decision
        for approval in request.approvals:
            try:
                if approval.approved:
                    conversation.approve_tool_call(approval.tool_call_id)
                    logger.info(
                        f"Approved tool call: {approval.tool_call_id}",
                        extra={"conversation_id": str(conv_id)},
                    )
                else:
                    reason = approval.rejection_reason or "User rejected"
                    conversation.reject_tool_call(approval.tool_call_id, reason)
                    logger.info(
                        f"Rejected tool call: {approval.tool_call_id} - {reason}",
                        extra={"conversation_id": str(conv_id)},
                    )
            except ToolCallNotFound:
                logger.warning(
                    f"Tool call not found: {approval.tool_call_id}",
                    extra={"conversation_id": str(conv_id)},
                )
                raise

        # 3. Save conversation
        self._conversations.save(conversation)

        # 4. Publish events
        if self._events:
            events = conversation.clear_events()
            self._events.publish_all(events)

        # 5. Build response
        from ..dto.responses import DataDTO
        data = DataDTO(tool_calls=[ToolCallDTO.from_tool_call(tc) for tc in conversation.all_tool_calls])
        return AgentResponse(
            conversation_id=str(conv_id),
            data=data,
            has_pending_approvals=conversation.has_pending_approvals,
            is_complete=not conversation.has_pending_approvals,
        )

    def approve_single(
        self,
        conversation_id: str,
        tool_call_id: str,
    ) -> AgentResponse:
        """
        Approve a single tool call.

        Convenience method for approving a single tool call.

        Args:
            conversation_id: The conversation ID
            tool_call_id: The tool call ID to approve

        Returns:
            AgentResponse with updated state
        """
        from ..dto.requests import ToolCallApproval

        return self.execute(
            ApprovalRequest(
                conversation_id=conversation_id,
                approvals=[
                    ToolCallApproval(
                        tool_call_id=tool_call_id,
                        approved=True,
                    )
                ],
            )
        )

    def reject_single(
        self,
        conversation_id: str,
        tool_call_id: str,
        reason: str,
    ) -> AgentResponse:
        """
        Reject a single tool call.

        Convenience method for rejecting a single tool call.

        Args:
            conversation_id: The conversation ID
            tool_call_id: The tool call ID to reject
            reason: Reason for rejection

        Returns:
            AgentResponse with updated state
        """
        from ..dto.requests import ToolCallApproval

        return self.execute(
            ApprovalRequest(
                conversation_id=conversation_id,
                approvals=[
                    ToolCallApproval(
                        tool_call_id=tool_call_id,
                        approved=False,
                        rejection_reason=reason,
                    )
                ],
            )
        )

    def approve_all(self, conversation_id: str) -> AgentResponse:
        """
        Approve all pending tool calls in a conversation.

        Args:
            conversation_id: The conversation ID

        Returns:
            AgentResponse with updated state
        """
        from ..dto.requests import ToolCallApproval

        # Load conversation to get pending tool calls
        conv_id = ConversationId(conversation_id)
        conversation = self._conversations.get(conv_id)

        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")

        # Create approvals for all pending
        approvals = [
            ToolCallApproval(tool_call_id=str(tc.id), approved=True)
            for tc in conversation.pending_tool_calls
        ]

        if not approvals:
            # No pending approvals, return current state
            from ..dto.responses import DataDTO
            data = DataDTO(tool_calls=[ToolCallDTO.from_tool_call(tc) for tc in conversation.all_tool_calls])
            return AgentResponse(
                conversation_id=conversation_id,
                data=data,
                has_pending_approvals=False,
                is_complete=True,
            )

        return self.execute(
            ApprovalRequest(
                conversation_id=conversation_id,
                approvals=approvals,
            )
        )

    def reject_all(self, conversation_id: str, reason: str) -> AgentResponse:
        """
        Reject all pending tool calls in a conversation.

        Args:
            conversation_id: The conversation ID
            reason: Reason for rejection

        Returns:
            AgentResponse with updated state
        """
        from ..dto.requests import ToolCallApproval

        # Load conversation to get pending tool calls
        conv_id = ConversationId(conversation_id)
        conversation = self._conversations.get(conv_id)

        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")

        # Create rejections for all pending
        approvals = [
            ToolCallApproval(
                tool_call_id=str(tc.id),
                approved=False,
                rejection_reason=reason,
            )
            for tc in conversation.pending_tool_calls
        ]

        if not approvals:
            # No pending approvals, return current state
            from ..dto.responses import DataDTO
            data = DataDTO(tool_calls=[ToolCallDTO.from_tool_call(tc) for tc in conversation.all_tool_calls])
            return AgentResponse(
                conversation_id=conversation_id,
                data=data,
                has_pending_approvals=False,
                is_complete=True,
            )

        return self.execute(
            ApprovalRequest(
                conversation_id=conversation_id,
                approvals=approvals,
            )
        )
