from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class FileObject(BaseModel):
    file_path: str
    file_content: str
    refers_persistent_file: str | None = None  # From main: reference to persistent file storage


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
    """
    Platform context for agent execution.

    Contains tenant, namespace, credentials, and role information
    needed by tools during execution.
    """

    # Tenant identification
    tenant_id: str | None = None
    tenant_name: str | None = None

    # User roles for access control
    user_roles: list[str] = Field(default_factory=list)

    # Kubernetes context
    k8s_namespace: str | None = None
    kubeconfig: str | None = None

    # DuploCloud context
    duplo_base_url: str | None = None
    duplo_token: str | None = None

    # AWS context
    aws_credentials: dict[str, Any] | None = None
    aws_region: str | None = None

    model_config = ConfigDict(extra="allow")  # Allow additional fields to pass through


# unused - covered by executed_cmds
class AmbientContext(BaseModel):
    user_terminal_cmds: list[ExecutedCommand] = Field(default_factory=list)


class Data(BaseModel):
    cmds: list[Command] = Field(default_factory=list)
    executed_cmds: list[ExecutedCommand] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    executed_tool_calls: list[ExecutedToolCall] = Field(default_factory=list)
    url_configs: list[URLConfig] = Field(default_factory=list)
    user_file_uploads: list[FileObject] = Field(default_factory=list)  # From main: user uploaded files
    session: dict[str, Any] = Field(
        default_factory=dict, description="Session state that persists across conversation turns"
    )


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

    @classmethod
    def from_agent_response(
        cls,
        response,  # AgentResponse from core
        include_timestamp: bool = True,
        agent_name: str | None = None,
        agent_id: str | None = None,
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
        from datetime import datetime

        # Build the Data container from the response
        data_dict: dict[str, Any] = {}
        if hasattr(response, "data"):
            # Response has DataDTO
            data_dict = response.data.to_dict() if hasattr(response.data, "to_dict") else {}
        elif hasattr(response, "tool_calls"):
            # Response has tool_calls directly (user-facing AgentResponse from agent.py)
            data_dict = {
                "cmds": [],
                "executed_cmds": [],
                "tool_calls": [
                    tc.to_dict() if hasattr(tc, "to_dict") else {}
                    for tc in getattr(response, "tool_calls", [])
                ],
                "executed_tool_calls": [],
            }

        # Create Data object
        data = Data(**data_dict) if data_dict else Data()

        # Build meta_data
        meta_data: dict[str, Any] = {}
        if hasattr(response, "metadata"):
            meta_data = response.metadata or {}
        if hasattr(response, "conversation_id"):
            meta_data["conversation_id"] = response.conversation_id
        if hasattr(response, "has_pending_approvals"):
            meta_data["has_pending_approvals"] = response.has_pending_approvals
        if hasattr(response, "is_complete"):
            meta_data["is_complete"] = response.is_complete

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
            timestamp=datetime.now(UTC) if include_timestamp else None,
            agent=agent_obj,
        )


class Messages(BaseModel):
    messages: list[UserMessage | AgentMessage]
