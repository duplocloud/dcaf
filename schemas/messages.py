from typing import List, Optional, Dict, Any
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class Command(BaseModel):
    command: str
    execute: bool = False
    rejection_reason: Optional[str] = None


class ExecutedCommand(BaseModel):
    command: str
    output: str


class URLConfig(BaseModel):
    url: HttpUrl
    description: str


class PlatformContext(BaseModel):
    k8s_namespace: Optional[str] = None
    tenant_name: Optional[str] = None
    aws_credentials: Optional[Dict[str, Any]] = None
    kubeconfig: Optional[str] = None


class AmbientContext(BaseModel):
    user_terminal_cmds: List[ExecutedCommand] = Field(default_factory=list)


class Data(BaseModel):
    cmds: List[Command] = Field(default_factory=list)
    executed_cmds: List[ExecutedCommand] = Field(default_factory=list)
    url_configs: List[URLConfig] = Field(default_factory=list)


class Message(BaseModel):
    role: str
    content: str = ""
    data: Data = Field(default_factory=Data)
    platform_context: Optional[PlatformContext] = None
    ambient_context: Optional[AmbientContext] = None
    timestamp: Optional[datetime] = None
    user: Optional[str, dict] = None
    agent: Optional[str, dict] = None


class MessagesPayload(BaseModel):
    messages: List[Message]
