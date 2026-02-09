from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class FileObject(BaseModel):
    file_path: str
    file_content: str
    refers_persistent_file: str | None = None


class Command(BaseModel):
    command: str
    execute: bool = False
    rejection_reason: str | None = None
    files: list[FileObject] | None = None


class ExecutedCommand(BaseModel):
    command: str
    output: str


class ToolCall(BaseModel):
    id: str
    name: str
    input: dict[str, Any]
    execute: bool = False
    tool_description: str
    input_description: dict[str, Any]
    intent: str | None = None
    rejection_reason: str | None = None


class ExecutedToolCall(BaseModel):
    id: str
    name: str
    input: dict[str, Any]
    output: str


class URLConfig(BaseModel):
    url: HttpUrl
    description: str


class PlatformContext(BaseModel):
    k8s_namespace: str | None = None
    duplo_base_url: str | None = None
    duplo_token: str | None = None
    tenant_name: str | None = None
    aws_credentials: dict[str, Any] | None = None
    kubeconfig: str | None = None


# unused - covered by executed_cmds
class AmbientContext(BaseModel):
    user_terminal_cmds: list[ExecutedCommand] = Field(default_factory=list)


class Data(BaseModel):
    cmds: list[Command] = Field(default_factory=list)
    executed_cmds: list[ExecutedCommand] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    executed_tool_calls: list[ExecutedToolCall] = Field(default_factory=list)
    url_configs: list[URLConfig] = Field(default_factory=list)
    user_file_uploads: list[FileObject] = Field(default_factory=list)


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
    meta_data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None
    user: User | None = None
    agent: Agent | None = None


class UserMessage(Message):
    role: Literal["user"] = "user"
    platform_context: PlatformContext | None = None
    ambient_context: AmbientContext | None = None


class AgentMessage(Message):
    role: Literal["assistant"] = "assistant"


class Messages(BaseModel):
    messages: list[UserMessage | AgentMessage]
