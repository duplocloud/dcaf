"""ApprovalCallback port - interface for approval mechanisms."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from ...domain.entities import ToolCall


class ApprovalAction(Enum):
    """Possible actions for an approval decision."""

    APPROVE = "approve"
    REJECT = "reject"
    TIMEOUT = "timeout"


@dataclass
class ApprovalDecision:
    """
    Result of a human approval decision.

    Attributes:
        tool_call_id: ID of the tool call this decision applies to
        action: The approval action taken
        reason: Optional reason (especially for rejections)
        approved_by: Optional identifier of who approved
    """

    tool_call_id: str
    action: ApprovalAction
    reason: str | None = None
    approved_by: str | None = None

    @property
    def is_approved(self) -> bool:
        return self.action == ApprovalAction.APPROVE

    @property
    def is_rejected(self) -> bool:
        return self.action == ApprovalAction.REJECT

    @property
    def is_timeout(self) -> bool:
        return self.action == ApprovalAction.TIMEOUT

    @classmethod
    def approve(cls, tool_call_id: str, approved_by: str | None = None) -> "ApprovalDecision":
        """Create an approval decision."""
        return cls(
            tool_call_id=tool_call_id,
            action=ApprovalAction.APPROVE,
            approved_by=approved_by,
        )

    @classmethod
    def reject(
        cls,
        tool_call_id: str,
        reason: str,
        rejected_by: str | None = None,
    ) -> "ApprovalDecision":
        """Create a rejection decision."""
        return cls(
            tool_call_id=tool_call_id,
            action=ApprovalAction.REJECT,
            reason=reason,
            approved_by=rejected_by,
        )

    @classmethod
    def timeout(cls, tool_call_id: str) -> "ApprovalDecision":
        """Create a timeout decision."""
        return cls(
            tool_call_id=tool_call_id,
            action=ApprovalAction.TIMEOUT,
            reason="Approval request timed out",
        )


@runtime_checkable
class ApprovalCallback(Protocol):
    """
    Port for requesting human approval.

    This protocol defines the interface for requesting approval
    from a human. Implementations can use different mechanisms
    (CLI prompts, web UI, Slack, etc.).

    Implementations:
        - CLIApprovalCallback: Prompts user in terminal
        - WebApprovalCallback: Sends to web UI for approval
        - SlackApprovalCallback: Posts to Slack for approval

    Example:
        class CLIApprovalCallback(ApprovalCallback):
            def request_approval(self, tool_calls):
                decisions = []
                for tc in tool_calls:
                    print(f"Approve {tc.tool_name}? [y/n]")
                    if input() == 'y':
                        decisions.append(ApprovalDecision.approve(str(tc.id)))
                    else:
                        decisions.append(ApprovalDecision.reject(str(tc.id), "User rejected"))
                return decisions
    """

    def request_approval(
        self,
        tool_calls: list[ToolCall],
    ) -> list[ApprovalDecision]:
        """
        Request approval for a list of tool calls.

        This method should present the tool calls to a human
        and collect their approval decisions. It may block
        until decisions are made or timeout.

        Args:
            tool_calls: List of tool calls requiring approval

        Returns:
            List of ApprovalDecision objects, one per tool call
        """
        ...

    def notify_execution_result(
        self,
        tool_call_id: str,
        result: str,
        success: bool,
    ) -> None:
        """
        Notify the approval mechanism of execution results.

        This allows the UI to show users what happened after
        they approved a tool call.

        Args:
            tool_call_id: ID of the executed tool call
            result: Execution result or error message
            success: Whether execution succeeded
        """
        ...
