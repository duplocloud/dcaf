"""
A2A data models.

These models represent the core A2A protocol data structures in a
framework-agnostic way.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentCard:
    """
    A2A Agent Card - describes an agent's capabilities.
    
    This is the discovery metadata for A2A agents, following Google's
    Agent-to-Agent protocol specification.
    
    Attributes:
        name: Unique identifier for the agent (e.g., "k8s-assistant")
        description: Human-readable description of what the agent does
        url: Base URL where the agent is hosted
        skills: List of tool/capability names this agent can perform
        version: A2A protocol version (default: "1.0")
        metadata: Additional metadata for future extensibility
        
    Example:
        card = AgentCard(
            name="k8s-assistant",
            description="Manages Kubernetes clusters",
            url="http://k8s-agent:8000",
            skills=["list_pods", "delete_pod", "describe_pod"],
        )
    """
    name: str
    description: str
    url: str
    skills: list[str]
    version: str = "1.0"
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "skills": self.skills,
            "version": self.version,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentCard":
        """Create from dictionary format."""
        return cls(
            name=data["name"],
            description=data["description"],
            url=data["url"],
            skills=data.get("skills", []),
            version=data.get("version", "1.0"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Task:
    """
    A2A Task - represents a request to a remote agent.
    
    Tasks are the unit of work in the A2A protocol. They represent
    a message sent to a remote agent for processing.
    
    Attributes:
        id: Unique identifier for this task
        message: The message/prompt to send to the agent
        context: Additional context (tenant, namespace, etc.)
        status: Task status ("pending", "running", "completed", "failed")
        metadata: Additional task metadata
        
    Example:
        task = Task(
            id="task_123",
            message="List all failing pods in production",
            context={"tenant_name": "production"},
            status="pending",
        )
    """
    id: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for JSON serialization."""
        return {
            "id": self.id,
            "message": self.message,
            "context": self.context,
            "status": self.status,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """Create from dictionary format."""
        return cls(
            id=data["id"],
            message=data["message"],
            context=data.get("context", {}),
            status=data.get("status", "pending"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class TaskResult:
    """
    Result from a remote agent task execution.
    
    Represents the response from an A2A agent after processing a task.
    
    Attributes:
        task_id: ID of the task this is a result for
        text: The agent's text response
        status: Final status ("completed", "failed", "pending")
        artifacts: Any structured output artifacts
        error: Error message if status is "failed"
        metadata: Additional result metadata
        
    Example:
        result = TaskResult(
            task_id="task_123",
            text="Found 3 failing pods: nginx-abc, redis-xyz, api-def",
            status="completed",
            artifacts=[],
        )
    """
    task_id: str
    text: str
    status: str = "completed"
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for JSON serialization."""
        result = {
            "task_id": self.task_id,
            "text": self.text,
            "status": self.status,
            "artifacts": self.artifacts,
            "metadata": self.metadata,
        }
        if self.error:
            result["error"] = self.error
        return result
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskResult":
        """Create from dictionary format."""
        return cls(
            task_id=data["task_id"],
            text=data["text"],
            status=data.get("status", "completed"),
            artifacts=data.get("artifacts", []),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Artifact:
    """
    A2A Artifact - structured output from an agent.
    
    Artifacts represent structured data returned by an agent,
    such as files, JSON data, or other typed outputs.
    
    Attributes:
        id: Unique identifier for the artifact
        type: Artifact type ("file", "json", "text", etc.)
        content: The artifact content
        metadata: Additional artifact metadata
        
    Example:
        artifact = Artifact(
            id="artifact_1",
            type="json",
            content={"pods": ["nginx-abc", "redis-xyz"]},
            metadata={"format": "kubernetes-list"},
        )
    """
    id: str
    type: str
    content: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for JSON serialization."""
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Artifact":
        """Create from dictionary format."""
        return cls(
            id=data["id"],
            type=data["type"],
            content=data["content"],
            metadata=data.get("metadata", {}),
        )

