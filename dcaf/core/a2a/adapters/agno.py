"""
Agno A2A adapter.

This adapter implements A2A protocol support using Agno's built-in A2A capabilities.
It wraps Agno's A2A interfaces to provide a clean DCAF-compatible API.
"""

import logging
import os
from typing import TYPE_CHECKING, Any

from ..models import AgentCard, Task, TaskResult
from ..protocols import A2AClientAdapter, A2AServerAdapter

if TYPE_CHECKING:
    from fastapi import APIRouter

    from ...agent import Agent


logger = logging.getLogger(__name__)


class AgnoA2AClient(A2AClientAdapter):
    """
    Agno-based A2A client implementation.

    This adapter uses Agno's A2A client capabilities to communicate
    with remote A2A agents.
    """

    def __init__(self) -> None:
        """Initialize the Agno A2A client.

        Environment Variables:
            BOTO3_READ_TIMEOUT: Read timeout in seconds (default: 20)
            BOTO3_CONNECT_TIMEOUT: Connect timeout in seconds (default: 10)
        """
        # Import Agno here to avoid hard dependency
        try:
            import httpx

            # Configure timeouts from environment variables
            read_timeout = float(os.getenv("BOTO3_READ_TIMEOUT", "20"))
            connect_timeout = float(os.getenv("BOTO3_CONNECT_TIMEOUT", "10"))

            # trust_env=False to avoid proxy issues
            self._http_client = httpx.Client(
                timeout=httpx.Timeout(
                    timeout=read_timeout,  # default timeout for all operations
                    connect=connect_timeout,
                ),
                trust_env=False,
            )
        except ImportError:
            raise RuntimeError(
                "httpx is required for A2A client. Install with: pip install httpx"
            ) from None

    def fetch_agent_card(self, url: str) -> AgentCard:
        """
        Fetch the agent card from a remote agent.

        Args:
            url: Base URL of the remote agent

        Returns:
            AgentCard with the agent's metadata

        Raises:
            ConnectionError: If the agent cannot be reached
            ValueError: If the agent card format is invalid
        """
        # Replace localhost with 127.0.0.1 to avoid IPv6/proxy issues with httpx
        normalized_url = url.replace("localhost", "127.0.0.1")
        agent_card_url = f"{normalized_url}/.well-known/agent.json"

        try:
            response = self._http_client.get(agent_card_url)
            response.raise_for_status()
            data = response.json()
            # Restore the original URL in the card
            card = AgentCard.from_dict(data)
            if card.url and "127.0.0.1" in card.url:
                card.url = card.url.replace("127.0.0.1", "localhost")
            return card
        except Exception as e:
            logger.error(f"Failed to fetch agent card from {url}: {e}")
            raise ConnectionError(f"Cannot reach agent at {url}") from e

    def send_task(self, url: str, task: Task) -> TaskResult:
        """
        Send a task to a remote agent and wait for completion.

        Args:
            url: Base URL of the remote agent
            task: Task to execute

        Returns:
            TaskResult with the agent's response

        Raises:
            ConnectionError: If the agent cannot be reached
            TimeoutError: If the task times out
            ValueError: If the task fails
        """
        # Replace localhost with 127.0.0.1 to avoid IPv6/proxy issues with httpx
        normalized_url = url.replace("localhost", "127.0.0.1")
        task_url = f"{normalized_url}/a2a/tasks/send"

        try:
            response = self._http_client.post(
                task_url,
                json=task.to_dict(),
            )
            response.raise_for_status()
            data = response.json()
            return TaskResult.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to send task to {url}: {e}")
            raise ConnectionError(f"Cannot reach agent at {url}") from e

    def send_task_async(self, url: str, task: Task) -> str:
        """
        Send a task to a remote agent asynchronously.

        Args:
            url: Base URL of the remote agent
            task: Task to execute

        Returns:
            Task ID for tracking

        Raises:
            ConnectionError: If the agent cannot be reached
        """
        # Replace localhost with 127.0.0.1 to avoid IPv6/proxy issues with httpx
        normalized_url = url.replace("localhost", "127.0.0.1")
        task_url = f"{normalized_url}/a2a/tasks/send?async=true"

        try:
            response = self._http_client.post(
                task_url,
                json=task.to_dict(),
            )
            response.raise_for_status()
            data = response.json()
            return str(data["task_id"])
        except Exception as e:
            logger.error(f"Failed to send async task to {url}: {e}")
            raise ConnectionError(f"Cannot reach agent at {url}") from e

    def get_task_status(self, url: str, task_id: str) -> TaskResult:
        """
        Get the status of an async task.

        Args:
            url: Base URL of the remote agent
            task_id: ID returned from send_task_async()

        Returns:
            TaskResult with current status

        Raises:
            ValueError: If the task ID is not found
        """
        # Replace localhost with 127.0.0.1 to avoid IPv6/proxy issues with httpx
        normalized_url = url.replace("localhost", "127.0.0.1")
        status_url = f"{normalized_url}/a2a/tasks/{task_id}"

        try:
            response = self._http_client.get(status_url)
            response.raise_for_status()
            data = response.json()
            return TaskResult.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to get task status from {url}: {e}")
            raise ValueError(f"Task {task_id} not found") from e


class AgnoA2AServer(A2AServerAdapter):
    """
    Agno-based A2A server implementation.

    This adapter creates FastAPI routes to expose a DCAF agent
    via the A2A protocol.
    """

    def __init__(self) -> None:
        """Initialize the Agno A2A server."""
        pass

    def create_agent_card(self, agent: "Agent") -> AgentCard:
        """
        Generate an agent card from a DCAF Agent instance.

        Args:
            agent: DCAF Agent instance

        Returns:
            AgentCard describing the agent's capabilities
        """
        # Extract tool names as skills
        skills = [tool.name for tool in agent.tools] if agent.tools else []

        return AgentCard(
            name=agent.name or "dcaf-agent",
            description=agent.description or agent.system_prompt or "A DCAF agent",
            url="",  # Will be set by caller
            skills=skills,
            version="1.0",
            metadata={
                "framework": "dcaf",
                "model": agent.model,
                "provider": agent.provider,
            },
        )

    def create_routes(
        self, agent: "Agent", agent_card: "AgentCard | dict[str, Any] | None" = None
    ) -> list["APIRouter"]:
        """
        Create FastAPI routes for A2A endpoints.

        Args:
            agent: DCAF Agent instance to expose
            agent_card: Optional custom agent card. Can be an AgentCard instance
                       or a dict with arbitrary A2A spec fields. If not provided,
                       the card is auto-generated from the agent.

        Returns:
            List of FastAPI APIRouter instances
        """
        from fastapi import APIRouter, HTTPException, Request

        router = APIRouter()

        # Store task manager on the agent for async tasks
        from ..server import A2ATaskManager

        if not hasattr(agent, "_a2a_task_manager"):
            agent._a2a_task_manager = A2ATaskManager()  # type: ignore[attr-defined]

        @router.get("/.well-known/agent.json")
        async def get_agent_card(request: Request) -> dict[str, Any]:
            """Get the agent card for A2A discovery."""
            base_url = str(request.base_url).rstrip("/")

            if agent_card is not None:
                # Use custom card
                if isinstance(agent_card, dict):
                    card_dict = dict(agent_card)
                    card_dict["url"] = base_url
                    return card_dict
                else:
                    # AgentCard instance
                    agent_card.url = base_url
                    return agent_card.to_dict()
            else:
                # Auto-generate from agent
                card = self.create_agent_card(agent)
                card.url = base_url
                return card.to_dict()

        @router.post("/a2a/tasks/send")
        async def send_task(
            task_data: dict[str, Any], request: Request, async_mode: bool = False
        ) -> dict[str, Any]:
            """
            Receive and execute an A2A task.

            Query params:
                async: If true, return immediately with task ID
            """
            try:
                task = Task.from_dict(task_data)

                if async_mode or request.query_params.get("async") == "true":
                    # Async mode - return task ID immediately
                    task_id = agent._a2a_task_manager.create_task(task)  # type: ignore[attr-defined]

                    # TODO: Execute task in background
                    # For now, just execute synchronously
                    result = await self.handle_task(agent, task)
                    agent._a2a_task_manager.update_task(task_id, result)  # type: ignore[attr-defined]

                    return {"task_id": task_id, "status": "pending"}
                else:
                    # Sync mode - execute and return result
                    result = await self.handle_task(agent, task)
                    return result.to_dict()

            except Exception as e:
                logger.error(f"Error handling task: {e}")
                raise HTTPException(status_code=500, detail=str(e)) from e

        @router.get("/a2a/tasks/{task_id}")
        async def get_task_status(task_id: str) -> dict[str, Any]:
            """Get the status of an async task."""
            try:
                result = agent._a2a_task_manager.get_task(task_id)  # type: ignore[attr-defined]
                result_dict: dict[str, Any] = result.to_dict()
                return result_dict
            except KeyError as e:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found") from e

        return [router]

    async def handle_task(self, agent: "Agent", task: Task) -> TaskResult:
        """
        Handle an incoming A2A task.

        Converts the A2A task to DCAF format, executes the agent,
        and converts the response back to A2A format.

        Args:
            agent: DCAF Agent instance
            task: Incoming A2A task

        Returns:
            TaskResult with the agent's response
        """
        try:
            # Convert A2A task to DCAF messages format
            messages: list[dict[str, Any]] = [{"role": "user", "content": task.message}]

            # Execute the agent
            response = await agent.run(messages=messages, context=task.context)  # type: ignore[arg-type]

            # Convert response to A2A format
            return TaskResult(
                task_id=task.id,
                text=response.text or "",
                status="completed",
                artifacts=[],
                metadata={
                    "conversation_id": response.conversation_id,
                    "needs_approval": response.needs_approval,
                },
            )

        except Exception as e:
            logger.error(f"Error executing task {task.id}: {e}")
            return TaskResult(
                task_id=task.id,
                text="",
                status="failed",
                error=str(e),
            )
