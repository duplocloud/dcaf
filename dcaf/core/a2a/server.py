"""
A2A server utilities.

This module provides utilities for exposing DCAF agents via the A2A protocol.
"""

import logging
from typing import TYPE_CHECKING

from .models import AgentCard, Task, TaskResult
from .protocols import A2AServerAdapter

if TYPE_CHECKING:
    from fastapi import APIRouter

    from ..agent import Agent


logger = logging.getLogger(__name__)


def create_a2a_routes(
    agent: "Agent",
    adapter: A2AServerAdapter | None = None,
) -> list["APIRouter"]:
    """
    Create FastAPI routes for A2A endpoints.

    This function creates the necessary routes to expose a DCAF agent
    via the A2A protocol:
    - GET /.well-known/agent.json - Agent card (discovery)
    - POST /a2a/tasks/send - Receive tasks
    - GET /a2a/tasks/{id} - Task status

    Args:
        agent: DCAF Agent instance to expose
        adapter: Optional custom A2A server adapter. If not provided,
                uses the default adapter (Agno).

    Returns:
        List of FastAPI APIRouter instances

    Example:
        from dcaf.core import Agent, create_app
        from dcaf.core.a2a import create_a2a_routes

        agent = Agent(
            name="k8s-assistant",
            tools=[list_pods, delete_pod],
        )

        app = create_app(agent)

        # Add A2A routes
        for router in create_a2a_routes(agent):
            app.include_router(router)
    """
    if adapter is None:
        adapter = _load_default_adapter()

    return adapter.create_routes(agent)


def generate_agent_card(
    agent: "Agent",
    base_url: str,
    adapter: A2AServerAdapter | None = None,
) -> AgentCard:
    """
    Generate an agent card from a DCAF Agent.

    Extracts the agent's name, description, and tools to create
    the A2A agent card metadata.

    Args:
        agent: DCAF Agent instance
        base_url: Base URL where the agent is hosted
        adapter: Optional custom A2A server adapter

    Returns:
        AgentCard describing the agent's capabilities

    Example:
        from dcaf.core import Agent
        from dcaf.core.a2a import generate_agent_card

        agent = Agent(
            name="k8s-assistant",
            description="Manages Kubernetes clusters",
            tools=[list_pods, delete_pod],
        )

        card = generate_agent_card(agent, "http://localhost:8000")
        print(card.name)       # "k8s-assistant"
        print(card.skills)     # ["list_pods", "delete_pod"]
    """
    if adapter is None:
        adapter = _load_default_adapter()

    card = adapter.create_agent_card(agent)
    # Override URL with the provided base_url
    card.url = base_url
    return card


def _load_default_adapter() -> A2AServerAdapter:
    """
    Load the default A2A server adapter.

    Currently uses the Agno adapter. In the future, this could
    be configurable or auto-detect based on available packages.
    """
    try:
        from .adapters.agno import AgnoA2AServer

        return AgnoA2AServer()
    except ImportError as e:
        logger.error(f"Failed to load default A2A server adapter: {e}")
        raise RuntimeError("No A2A adapter available. Install agno with: pip install agno") from e


class A2ATaskManager:
    """
    Manages async A2A tasks.

    This is a simple in-memory task manager for handling async A2A tasks.
    For production use, consider using a persistent backend (Redis, database).

    Attributes:
        tasks: Dictionary of task_id -> TaskResult

    Example:
        manager = A2ATaskManager()
        task_id = manager.create_task(task)
        # ... execute task async ...
        manager.complete_task(task_id, result)
    """

    def __init__(self) -> None:
        """Initialize the task manager."""
        self.tasks: dict[str, TaskResult] = {}

    def create_task(self, task: Task) -> str:
        """
        Create a new task.

        Args:
            task: Task to create

        Returns:
            Task ID
        """
        self.tasks[task.id] = TaskResult(
            task_id=task.id,
            text="",
            status="pending",
        )
        logger.info(f"Created task {task.id}")
        return task.id

    def get_task(self, task_id: str) -> TaskResult:
        """
        Get a task by ID.

        Args:
            task_id: ID of the task

        Returns:
            TaskResult

        Raises:
            KeyError: If task not found
        """
        if task_id not in self.tasks:
            raise KeyError(f"Task {task_id} not found")
        return self.tasks[task_id]

    def update_task(self, task_id: str, result: TaskResult) -> None:
        """
        Update a task with results.

        Args:
            task_id: ID of the task
            result: TaskResult to store
        """
        self.tasks[task_id] = result
        logger.info(f"Updated task {task_id}: status={result.status}")

    def complete_task(
        self,
        task_id: str,
        text: str,
        artifacts: list[dict] | None = None,
    ) -> None:
        """
        Mark a task as completed.

        Args:
            task_id: ID of the task
            text: Response text
            artifacts: Optional artifacts
        """
        self.tasks[task_id] = TaskResult(
            task_id=task_id,
            text=text,
            status="completed",
            artifacts=artifacts or [],
        )
        logger.info(f"Completed task {task_id}")

    def fail_task(self, task_id: str, error: str) -> None:
        """
        Mark a task as failed.

        Args:
            task_id: ID of the task
            error: Error message
        """
        self.tasks[task_id] = TaskResult(
            task_id=task_id,
            text="",
            status="failed",
            error=error,
        )
        logger.error(f"Task {task_id} failed: {error}")
