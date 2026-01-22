"""
A2A client for calling remote agents.

This module provides the RemoteAgent class, which is the main user-facing
interface for communicating with remote A2A agents.
"""

import logging
import uuid
from typing import Any

from .models import AgentCard, Task, TaskResult
from .protocols import A2AClientAdapter

logger = logging.getLogger(__name__)


class RemoteAgent:
    """
    Client for communicating with a remote A2A agent.

    RemoteAgent provides a simple interface for calling other agents
    over the A2A protocol. It can be used directly or converted to
    a tool for use by other agents.

    Attributes:
        url: Base URL of the remote agent
        card: Agent card (lazily fetched on first access)
        name: Agent name from card (or specified)

    Example - Direct use:
        k8s = RemoteAgent(url="http://k8s-agent:8000")
        result = k8s.send("List all failing pods in production")
        print(result.text)

    Example - As a tool:
        k8s = RemoteAgent(url="http://k8s-agent:8000", name="k8s")

        orchestrator = Agent(
            tools=[k8s.as_tool()],
            system="Route requests to specialist agents"
        )
    """

    def __init__(
        self,
        url: str,
        name: str | None = None,
        adapter: A2AClientAdapter | None = None,
    ):
        """
        Create a remote agent client.

        Args:
            url: Base URL of the remote agent (e.g., "http://k8s-agent:8000")
            name: Optional name for the agent (for tool name). If not provided,
                  will be fetched from the agent card.
            adapter: Optional custom A2A client adapter. If not provided,
                    uses the default adapter (Agno).
        """
        self.url = url.rstrip("/")  # Remove trailing slash
        self._name = name
        self._card: AgentCard | None = None
        self._adapter = adapter or self._load_default_adapter()

    @property
    def card(self) -> AgentCard:
        """
        Get the agent card (lazily fetched).

        The card is fetched from the remote agent on first access
        and cached for subsequent calls.

        Returns:
            AgentCard with agent metadata

        Raises:
            ConnectionError: If the agent cannot be reached
        """
        if self._card is None:
            self._card = self._adapter.fetch_agent_card(self.url)
        return self._card

    @property
    def name(self) -> str:
        """
        Get the agent name.

        Returns the name specified in __init__() or fetches it
        from the agent card.
        """
        if self._name:
            return self._name
        return self.card.name

    @property
    def description(self) -> str:
        """Get the agent description from the card."""
        return self.card.description

    @property
    def skills(self) -> list[str]:
        """Get the list of skills/capabilities from the card."""
        return self.card.skills

    def send(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        timeout: float = 60.0,  # noqa: ARG002
    ) -> TaskResult:
        """
        Send a message to the remote agent and wait for response.

        This is a synchronous call that blocks until the remote agent
        completes the task.

        Args:
            message: Message/prompt to send to the agent
            context: Optional platform context (tenant, namespace, etc.)
            timeout: Timeout in seconds (default: 60)

        Returns:
            TaskResult with the agent's response

        Raises:
            ConnectionError: If the agent cannot be reached
            TimeoutError: If the task times out
            ValueError: If the task fails

        Example:
            k8s = RemoteAgent(url="http://k8s-agent:8000")
            result = k8s.send(
                "List pods in production",
                context={"tenant_name": "production"}
            )
            print(result.text)
        """
        task = Task(
            id=f"task_{uuid.uuid4().hex[:12]}",
            message=message,
            context=context or {},
            status="pending",
        )

        logger.info(f"Sending task {task.id} to {self.name} at {self.url}")

        try:
            result = self._adapter.send_task(self.url, task)
            logger.info(f"Task {task.id} completed: {result.status}")
            return result
        except Exception as e:
            logger.error(f"Task {task.id} failed: {e}")
            raise

    def send_async(
        self,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Send a message to the remote agent asynchronously.

        Returns immediately with a task ID. Use get_task_status()
        to check on the task's progress.

        Args:
            message: Message/prompt to send to the agent
            context: Optional platform context

        Returns:
            Task ID for tracking

        Example:
            k8s = RemoteAgent(url="http://k8s-agent:8000")
            task_id = k8s.send_async("Analyze all pod logs")

            # Later...
            result = k8s.get_task_status(task_id)
            if result.status == "completed":
                print(result.text)
        """
        task = Task(
            id=f"task_{uuid.uuid4().hex[:12]}",
            message=message,
            context=context or {},
            status="pending",
        )

        logger.info(f"Sending async task {task.id} to {self.name}")
        return self._adapter.send_task_async(self.url, task)

    def get_task_status(self, task_id: str) -> TaskResult:
        """
        Get the status of an async task.

        Args:
            task_id: ID returned from send_async()

        Returns:
            TaskResult with current status

        Raises:
            ValueError: If the task ID is not found
        """
        return self._adapter.get_task_status(self.url, task_id)

    def as_tool(self) -> Any:
        """
        Convert this remote agent to a tool for use by other agents.

        This wraps the remote agent in a tool that can be called by
        another DCAF agent. The LLM will see the remote agent as a
        regular tool it can invoke.

        Returns:
            Tool instance that wraps this remote agent

        Example:
            k8s = RemoteAgent(url="http://k8s-agent:8000")
            aws = RemoteAgent(url="http://aws-agent:8000")

            orchestrator = Agent(
                tools=[k8s.as_tool(), aws.as_tool()],
                system="Route requests to the appropriate specialist"
            )
        """
        from ...tools import tool

        # Create a tool wrapper function
        def remote_agent_call(message: str, **context: Any) -> str:
            """Call a remote agent."""
            result = self.send(message, context=context)
            return result.text

        # Set the function name and docstring
        remote_agent_call.__name__ = self.name
        remote_agent_call.__doc__ = self.description

        # Decorate with @tool
        return tool(
            description=f"{self.description} (remote agent at {self.url})",
            requires_approval=False,
        )(remote_agent_call)

    def _load_default_adapter(self) -> A2AClientAdapter:
        """
        Load the default A2A client adapter.

        Currently uses the Agno adapter. In the future, this could
        be configurable or auto-detect based on available packages.
        """
        try:
            from .adapters.agno import AgnoA2AClient

            return AgnoA2AClient()
        except ImportError as e:
            logger.error(f"Failed to load default A2A adapter: {e}")
            raise RuntimeError(
                "No A2A adapter available. Install agno with: pip install agno"
            ) from e

    def __repr__(self) -> str:
        """String representation."""
        return f"RemoteAgent(name={self.name!r}, url={self.url!r})"
