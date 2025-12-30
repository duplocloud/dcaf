"""Approval policy domain service."""

from typing import List, Optional, Protocol
from dataclasses import dataclass

from ..value_objects.platform_context import PlatformContext


class ToolLike(Protocol):
    """Protocol for tool-like objects that have approval properties."""
    
    @property
    def name(self) -> str: ...
    
    @property
    def requires_approval(self) -> bool: ...


@dataclass
class ApprovalDecision:
    """Result of an approval policy check."""
    
    requires_approval: bool
    reason: Optional[str] = None
    
    @classmethod
    def approved(cls) -> "ApprovalDecision":
        """Create a decision indicating no approval needed."""
        return cls(requires_approval=False)
    
    @classmethod
    def needs_approval(cls, reason: str) -> "ApprovalDecision":
        """Create a decision indicating approval is needed."""
        return cls(requires_approval=True, reason=reason)


class ApprovalPolicy:
    """
    Domain service that determines what requires human approval.
    
    This service encapsulates the business rules for when a tool
    execution should be gated by human approval. It considers:
    - Tool-level configuration (requires_approval flag)
    - Platform context (environment, tenant)
    - Custom policies that can be injected
    
    Example usage:
        policy = ApprovalPolicy()
        decision = policy.check(tool, context)
        if decision.requires_approval:
            # Request approval
            pass
    """
    
    def __init__(
        self,
        always_approve_read_only: bool = True,
        high_risk_tools: Optional[List[str]] = None,
    ) -> None:
        """
        Initialize the approval policy.
        
        Args:
            always_approve_read_only: If True, tools marked read-only never need approval
            high_risk_tools: List of tool names that always require approval
        """
        self._always_approve_read_only = always_approve_read_only
        self._high_risk_tools = set(high_risk_tools or [])
    
    def requires_approval(
        self, 
        tool: ToolLike, 
        context: Optional[PlatformContext] = None,
    ) -> bool:
        """
        Check if a tool requires approval in the given context.
        
        Args:
            tool: The tool to check
            context: Optional platform context
            
        Returns:
            True if the tool requires human approval
        """
        return self.check(tool, context).requires_approval
    
    def check(
        self, 
        tool: ToolLike, 
        context: Optional[PlatformContext] = None,
    ) -> ApprovalDecision:
        """
        Check if a tool requires approval and get the reason.
        
        Args:
            tool: The tool to check
            context: Optional platform context
            
        Returns:
            ApprovalDecision with the result and reason
        """
        # High-risk tools always require approval
        if tool.name in self._high_risk_tools:
            return ApprovalDecision.needs_approval(
                f"Tool '{tool.name}' is marked as high-risk"
            )
        
        # Check tool-level configuration
        if tool.requires_approval:
            return ApprovalDecision.needs_approval(
                f"Tool '{tool.name}' is configured to require approval"
            )
        
        # No approval needed
        return ApprovalDecision.approved()
    
    def filter_requiring_approval(
        self, 
        tools: List[ToolLike],
        context: Optional[PlatformContext] = None,
    ) -> List[ToolLike]:
        """
        Filter tools to only those requiring approval.
        
        Args:
            tools: List of tools to filter
            context: Optional platform context
            
        Returns:
            List of tools that require approval
        """
        return [t for t in tools if self.requires_approval(t, context)]
    
    def add_high_risk_tool(self, tool_name: str) -> None:
        """Add a tool to the high-risk list."""
        self._high_risk_tools.add(tool_name)
    
    def remove_high_risk_tool(self, tool_name: str) -> None:
        """Remove a tool from the high-risk list."""
        self._high_risk_tools.discard(tool_name)
