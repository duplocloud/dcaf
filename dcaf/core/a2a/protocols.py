"""
A2A protocol interfaces.

These protocols define the abstract interfaces that A2A adapters must implement.
This allows us to swap A2A implementations (e.g., Agno, custom, etc.) without
changing the user-facing API.
"""

from typing import Protocol, Any
from .models import AgentCard, Task, TaskResult


class A2AClientAdapter(Protocol):
    """
    Interface for A2A client implementations.
    
    This protocol defines what a client adapter must implement to communicate
    with remote A2A agents. Implementations handle the details of the A2A
    protocol (HTTP, JSON-RPC, etc.) while providing a simple interface.
    
    Example implementation:
        class AgnoA2AClient(A2AClientAdapter):
            def fetch_agent_card(self, url: str) -> AgentCard:
                # Use Agno's A2A client to fetch card
                ...
            
            def send_task(self, url: str, task: Task) -> TaskResult:
                # Use Agno to send task
                ...
    """
    
    def fetch_agent_card(self, url: str) -> AgentCard:
        """
        Fetch the agent card from a remote agent.
        
        The agent card describes the agent's capabilities (tools, description).
        This is typically fetched from /.well-known/agent.json
        
        Args:
            url: Base URL of the remote agent
            
        Returns:
            AgentCard with the agent's metadata
            
        Raises:
            ConnectionError: If the agent cannot be reached
            ValueError: If the agent card format is invalid
        """
        ...
    
    def send_task(self, url: str, task: Task) -> TaskResult:
        """
        Send a task to a remote agent and wait for completion.
        
        This is a synchronous call that blocks until the remote agent
        completes the task. For long-running tasks, the implementation
        should poll the task status.
        
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
        ...
    
    def send_task_async(self, url: str, task: Task) -> str:
        """
        Send a task to a remote agent asynchronously.
        
        Returns immediately with a task ID. Use get_task_status() to
        check on the task's progress.
        
        Args:
            url: Base URL of the remote agent
            task: Task to execute
            
        Returns:
            Task ID for tracking
            
        Raises:
            ConnectionError: If the agent cannot be reached
        """
        ...
    
    def get_task_status(self, url: str, task_id: str) -> TaskResult:
        """
        Get the status of an async task.
        
        Args:
            url: Base URL of the remote agent
            task_id: ID returned from send_task_async()
            
        Returns:
            TaskResult with current status
            
        Raises:
            ConnectionError: If the agent cannot be reached
            ValueError: If the task ID is not found
        """
        ...


class A2AServerAdapter(Protocol):
    """
    Interface for A2A server implementations.
    
    This protocol defines what a server adapter must implement to expose
    a DCAF agent via the A2A protocol. Implementations handle creating
    the necessary routes and handling incoming A2A requests.
    
    Example implementation:
        class AgnoA2AServer(A2AServerAdapter):
            def create_agent_card(self, agent) -> AgentCard:
                # Generate card from DCAF Agent
                ...
            
            def create_routes(self, agent):
                # Create FastAPI routes for A2A endpoints
                ...
    """
    
    def create_agent_card(self, agent: Any) -> AgentCard:
        """
        Generate an agent card from a DCAF Agent instance.
        
        Extracts the agent's name, description, and tools to create
        the A2A agent card metadata.
        
        Args:
            agent: DCAF Agent instance
            
        Returns:
            AgentCard describing the agent's capabilities
        """
        ...
    
    def create_routes(self, agent: Any) -> list:
        """
        Create FastAPI routes for A2A endpoints.
        
        Creates the necessary routes to handle incoming A2A requests:
        - GET /.well-known/agent.json - Agent card discovery
        - POST /a2a/tasks/send - Receive tasks
        - GET /a2a/tasks/{id} - Task status
        
        Args:
            agent: DCAF Agent instance to expose
            
        Returns:
            List of FastAPI APIRouter instances
        """
        ...
    
    def handle_task(self, agent: Any, task: Task) -> TaskResult:
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
        ...

