from typing import List, Optional, Dict, Any, Literal, Union
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class FileObject(BaseModel):
    file_path: str
    file_content: str


class Command(BaseModel):
    command: str
    execute: bool = False
    rejection_reason: Optional[str] = None
    files: Optional[List[FileObject]] = None


class ExecutedCommand(BaseModel):
    command: str
    output: str


class ToolCall(BaseModel):
    id: str
    name: str
    input: Dict[str, Any]
    execute: bool = False
    tool_description: str
    input_description: Dict[str, Any]
    intent: Optional[str] = None
    rejection_reason: Optional[str] = None


class ExecutedToolCall(BaseModel):
    id: str
    name: str
    input: Dict[str, Any]
    output: str


class URLConfig(BaseModel):
    url: HttpUrl
    description: str


class PlatformContext(BaseModel):
    """
    Platform context for agent execution.
    
    Contains tenant, namespace, credentials, and role information
    needed by tools during execution.
    """
    # Tenant identification
    tenant_id: Optional[str] = None
    tenant_name: Optional[str] = None
    
    # User roles for access control
    user_roles: List[str] = Field(default_factory=list)
    
    # Kubernetes context
    k8s_namespace: Optional[str] = None
    kubeconfig: Optional[str] = None
    
    # DuploCloud context
    duplo_base_url: Optional[str] = None
    duplo_token: Optional[str] = None
    
    # AWS context
    aws_credentials: Optional[Dict[str, Any]] = None
    aws_region: Optional[str] = None
    
    model_config = ConfigDict(extra="allow")  # Allow additional fields to pass through


#unused - covered by executed_cmds
class AmbientContext(BaseModel):
    user_terminal_cmds: List[ExecutedCommand] = Field(default_factory=list)


class Data(BaseModel):
    cmds: List[Command] = Field(default_factory=list)
    executed_cmds: List[ExecutedCommand] = Field(default_factory=list)
    tool_calls: List[ToolCall] = Field(default_factory=list)
    executed_tool_calls: List[ExecutedToolCall] = Field(default_factory=list)
    url_configs: List[URLConfig] = Field(default_factory=list)


class User(BaseModel):
    name: str
    id: str


class Agent(BaseModel):
    name: str
    id: str


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = ""
    data: Data = Field(default_factory=Data)
    meta_data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None
    user: Optional[User] = None
    agent: Optional[Agent] = None


class UserMessage(Message):
    role: Literal["user"] = "user"
    platform_context: Optional[PlatformContext] = None
    ambient_context: Optional[AmbientContext] = None


class AgentMessage(Message):
    role: Literal["assistant"] = "assistant"
    
    @classmethod
    def from_agent_response(
        cls,
        response,  # AgentResponse from core
        include_timestamp: bool = True,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> "AgentMessage":
        """
        Create an AgentMessage from a core AgentResponse.
        
        This provides a bridge between the core's internal AgentResponse
        (from dcaf.core.application.dto.responses) and the schema's AgentMessage
        (wire format for HelpDesk protocol).
        
        Args:
            response: AgentResponse from core (dto/responses.py)
            include_timestamp: Whether to add a timestamp (default: True)
            agent_name: Optional agent name for identification
            agent_id: Optional agent ID for identification
            
        Returns:
            AgentMessage suitable for serialization to JSON
            
        Example:
            # Internal response from AgentService
            core_response = agent_service.execute(request)
            
            # Convert to wire format
            message = AgentMessage.from_agent_response(core_response)
            
            # Serialize to JSON
            json_data = message.model_dump()
        """
        from datetime import datetime, timezone
        
        # Build the Data container from the response
        data_dict = {}
        if hasattr(response, 'data'):
            # Response has DataDTO
            data_dict = response.data.to_dict() if hasattr(response.data, 'to_dict') else {}
        elif hasattr(response, 'tool_calls'):
            # Response has tool_calls directly (user-facing AgentResponse from agent.py)
            data_dict = {
                "cmds": [],
                "executed_cmds": [],
                "tool_calls": [tc.to_dict() if hasattr(tc, 'to_dict') else {} for tc in getattr(response, 'tool_calls', [])],
                "executed_tool_calls": [],
            }
        
        # Create Data object
        data = Data(**data_dict) if data_dict else Data()
        
        # Build meta_data
        meta_data = {}
        if hasattr(response, 'metadata'):
            meta_data = response.metadata or {}
        if hasattr(response, 'conversation_id'):
            meta_data['conversation_id'] = response.conversation_id
        if hasattr(response, 'has_pending_approvals'):
            meta_data['has_pending_approvals'] = response.has_pending_approvals
        if hasattr(response, 'is_complete'):
            meta_data['is_complete'] = response.is_complete
        
        # Build Agent object if provided
        agent_obj = None
        if agent_name or agent_id:
            agent_obj = Agent(
                name=agent_name or "dcaf-agent",
                id=agent_id or "unknown",
            )
        
        return cls(
            content=response.text or "",
            data=data,
            meta_data=meta_data,
            timestamp=datetime.now(timezone.utc) if include_timestamp else None,
            agent=agent_obj,
        )


class Messages(BaseModel):
    messages: List[Union[UserMessage, AgentMessage]]