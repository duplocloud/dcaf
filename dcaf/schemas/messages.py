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


class Messages(BaseModel):
    messages: List[Union[UserMessage, AgentMessage]]