"""Request DTOs for application use cases."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

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
    rejection_reason: Optional[str] = None


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
        
    Example with message history:
        request = AgentRequest(
            content="What else can you tell me?",
            messages=[
                {"role": "user", "content": "What pods are running?"},
                {"role": "assistant", "content": "There are 3 pods: nginx, redis, api"},
            ],
            tools=[...],
        )
    """
    
    content: str
    messages: Optional[List[Dict[str, Any]]] = None  # Conversation history from external source
    conversation_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    tools: List[Any] = field(default_factory=list)  # List[Tool]
    system_prompt: Optional[str] = None
    static_system: Optional[str] = None  # Static system prompt (cached)
    dynamic_system: Optional[str] = None  # Dynamic system prompt (not cached)
    stream: bool = False
    
    def get_conversation_id(self) -> Optional[ConversationId]:
        """Get the conversation ID as a value object."""
        if self.conversation_id:
            return ConversationId(self.conversation_id)
        return None
    
    def get_platform_context(self) -> PlatformContext:
        """Get the platform context as a value object."""
        if self.context:
            return PlatformContext.from_dict(self.context)
        return PlatformContext.empty()


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
    approvals: List[ToolCallApproval]
    
    def get_conversation_id(self) -> ConversationId:
        """Get the conversation ID as a value object."""
        return ConversationId(self.conversation_id)
    
    @property
    def approved_ids(self) -> List[str]:
        """Get IDs of approved tool calls."""
        return [a.tool_call_id for a in self.approvals if a.approved]
    
    @property
    def rejected_ids(self) -> List[str]:
        """Get IDs of rejected tool calls."""
        return [a.tool_call_id for a in self.approvals if not a.approved]
