"""
A2A (Agent-to-Agent) support for DCAF.

This module provides interfaces for agent-to-agent communication using
Google's A2A protocol. Agents can:
- Expose themselves via A2A (server)
- Call other A2A agents (client)
- Use remote agents as tools

Example - Server (exposing an agent):
    from dcaf.core import Agent, serve
    
    agent = Agent(
        name="k8s-assistant",
        description="Kubernetes helper",
        tools=[list_pods, delete_pod],
    )
    
    serve(agent, port=8000, a2a=True)

Example - Client (calling remote agents):
    from dcaf.core.a2a import RemoteAgent
    
    k8s = RemoteAgent(url="http://k8s-agent:8000")
    result = k8s.send("List failing pods")
    print(result.text)

Example - Orchestration (agent calling agents):
    from dcaf.core import Agent
    from dcaf.core.a2a import RemoteAgent
    
    k8s = RemoteAgent(url="http://k8s-agent:8000")
    aws = RemoteAgent(url="http://aws-agent:8000")
    
    orchestrator = Agent(
        tools=[k8s.as_tool(), aws.as_tool()],
        system="Route to specialist agents"
    )
"""

from .models import AgentCard, Task, TaskResult, Artifact
from .client import RemoteAgent
from .server import create_a2a_routes, generate_agent_card
from .protocols import A2AClientAdapter, A2AServerAdapter

__all__ = [
    # Data models
    "AgentCard",
    "Task",
    "TaskResult",
    "Artifact",
    # Client
    "RemoteAgent",
    # Server utilities
    "create_a2a_routes",
    "generate_agent_card",
    # Protocols (for custom adapters)
    "A2AClientAdapter",
    "A2AServerAdapter",
]

