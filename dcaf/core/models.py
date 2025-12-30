"""
Core data models for DCAF.

These are simple, Pythonic data structures used throughout the framework.
Fully compatible with the DuploCloud HelpDesk messaging protocol.
"""

from dataclasses import dataclass, field
from typing import Literal, Any, Optional


@dataclass
class PlatformContext:
    """
    Platform context passed with user messages.
    
    This provides runtime context about the user's environment,
    used by tools and agents to execute operations in the correct
    tenant, namespace, or cloud account.
    
    Attributes:
        k8s_namespace: Kubernetes namespace for kubectl operations
        duplo_base_url: DuploCloud API base URL
        duplo_token: DuploCloud authentication token
        tenant_name: DuploCloud tenant name
        aws_credentials: AWS credentials dict (access_key, secret_key, session_token, region)
        kubeconfig: Path to kubeconfig file or inline kubeconfig content
        
    Example:
        context = PlatformContext(
            tenant_name="acme-prod",
            k8s_namespace="default",
            duplo_base_url="https://acme.duplocloud.net",
        )
        
        # Pass with a message
        msg = ChatMessage.user("List pods", context=context.to_dict())
    """
    k8s_namespace: Optional[str] = None
    duplo_base_url: Optional[str] = None
    duplo_token: Optional[str] = None
    tenant_name: Optional[str] = None
    aws_credentials: Optional[dict[str, Any]] = None
    kubeconfig: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        result = {}
        if self.k8s_namespace:
            result["k8s_namespace"] = self.k8s_namespace
        if self.duplo_base_url:
            result["duplo_base_url"] = self.duplo_base_url
        if self.duplo_token:
            result["duplo_token"] = self.duplo_token
        if self.tenant_name:
            result["tenant_name"] = self.tenant_name
        if self.aws_credentials:
            result["aws_credentials"] = self.aws_credentials
        if self.kubeconfig:
            result["kubeconfig"] = self.kubeconfig
        return result
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlatformContext":
        """Create from dictionary."""
        return cls(
            k8s_namespace=data.get("k8s_namespace"),
            duplo_base_url=data.get("duplo_base_url"),
            duplo_token=data.get("duplo_token"),
            tenant_name=data.get("tenant_name"),
            aws_credentials=data.get("aws_credentials"),
            kubeconfig=data.get("kubeconfig"),
        )
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a context value by key (dict-like access)."""
        return self.to_dict().get(key, default)


@dataclass
class ChatMessage:
    """
    A single message in a conversation.
    
    This represents one turn in a conversation between a user and an assistant.
    Messages can also be system messages that set the assistant's behavior.
    
    Compatible with the HelpDesk protocol message format.
    
    Attributes:
        role: Who sent the message
            - 'user': Message from the human user
            - 'assistant': Message from the AI assistant  
            - 'system': System prompt/instructions
        content: The message text
        context: Optional platform context for this message (tenant, namespace, etc.)
        data: Optional data container (commands, tool calls) for HelpDesk protocol
        
    Example:
        # Create a user message
        msg = ChatMessage(role="user", content="What pods are running?")
        
        # Create with platform context
        msg = ChatMessage(
            role="user", 
            content="Delete the nginx pod",
            context=PlatformContext(tenant_name="acme", k8s_namespace="production")
        )
        
    Note:
        You can also use plain dicts anywhere ChatMessage is accepted:
        {"role": "user", "content": "Hello"}
    """
    role: Literal["user", "assistant", "system"]
    content: str
    context: PlatformContext | dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dictionary (HelpDesk format)."""
        result = {"role": self.role, "content": self.content}
        if self.context:
            if isinstance(self.context, PlatformContext):
                result["platform_context"] = self.context.to_dict()
            else:
                result["platform_context"] = self.context
        if self.data:
            result["data"] = self.data
        return result
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatMessage":
        """
        Create a ChatMessage from a dictionary.
        
        Args:
            data: Dict with 'role' and 'content' keys
            
        Returns:
            ChatMessage instance
            
        Example:
            msg = ChatMessage.from_dict({"role": "user", "content": "Hello"})
        """
        # Handle platform_context in various formats
        context = data.get("platform_context") or data.get("context")
        if isinstance(context, dict):
            context = PlatformContext.from_dict(context)
        
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            context=context,
            data=data.get("data"),
        )
    
    @classmethod
    def user(
        cls, 
        content: str, 
        context: PlatformContext | dict | None = None,
        data: dict | None = None,
    ) -> "ChatMessage":
        """Create a user message."""
        return cls(role="user", content=content, context=context, data=data)
    
    @classmethod
    def assistant(
        cls, 
        content: str,
        data: dict | None = None,
    ) -> "ChatMessage":
        """Create an assistant message."""
        return cls(role="assistant", content=content, data=data)
    
    @classmethod
    def system(cls, content: str) -> "ChatMessage":
        """Create a system message."""
        return cls(role="system", content=content)
    
    def get_platform_context(self) -> PlatformContext | None:
        """Get platform context as PlatformContext object."""
        if isinstance(self.context, PlatformContext):
            return self.context
        elif isinstance(self.context, dict):
            return PlatformContext.from_dict(self.context)
        return None


def normalize_messages(messages: list[ChatMessage | dict]) -> list[ChatMessage]:
    """
    Normalize a list of messages to ChatMessage instances.
    
    Accepts either ChatMessage instances or plain dicts.
    
    Args:
        messages: List of ChatMessage or dict objects
        
    Returns:
        List of ChatMessage instances
        
    Example:
        # Mixed input
        messages = [
            ChatMessage(role="user", content="Hello"),
            {"role": "assistant", "content": "Hi there!"},
        ]
        normalized = normalize_messages(messages)
        # All are now ChatMessage instances
    """
    result = []
    for msg in messages:
        if isinstance(msg, ChatMessage):
            result.append(msg)
        elif isinstance(msg, dict):
            result.append(ChatMessage.from_dict(msg))
        else:
            raise TypeError(f"Expected ChatMessage or dict, got {type(msg)}")
    return result
