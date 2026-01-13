"""
DCAF Core Primitives - Data types for custom agent functions.

This module provides the data types used when building custom agent functions:
- AgentResult: What your agent function returns
- ToolApproval: Tool calls needing user approval
- ToolResult: Executed tool results

For making LLM calls, use the Agent class.

Example - Custom multi-call agent:
    from dcaf.core import Agent, serve
    from dcaf.core.primitives import AgentResult
    from dcaf.tools import tool
    
    @tool(requires_approval=True)
    def delete_pod(name: str) -> str:
        return kubectl(f"delete pod {name}")
    
    def my_agent(messages: list, context: dict) -> AgentResult:
        # Create agents for different purposes
        classifier = Agent(system="Classify intent: query or action")
        executor = Agent(tools=[delete_pod], system="K8s assistant")
        
        # Your logic - any structure
        intent = classifier.run(messages)
        
        if "action" in intent.text:
            result = executor.run(messages)
            return AgentResult(
                text=result.text,
                pending_tools=[
                    ToolApproval(
                        id=p.id,
                        name=p.name,
                        input=p.input,
                        description=p.description,
                    )
                    for p in result.pending_tools
                ],
            )
        
        return AgentResult(text=intent.text)
    
    # Serve it
    serve(my_agent)
"""

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from dcaf.schemas.messages import AgentMessage

logger = logging.getLogger(__name__)


# =============================================================================
# Result Types - What custom agent functions return
# =============================================================================

@dataclass
class ToolApproval:
    """
    A tool call that needs user approval before execution.
    
    When your agent wants to run a tool that requires approval,
    include it in AgentResult.pending_tools. The HelpDesk will
    show it to the user for approval.
    
    Attributes:
        id: Unique identifier for this tool call
        name: Name of the tool
        input: Parameters to pass to the tool
        description: Human-readable description of what it will do
        intent: Why the agent wants to call this tool
    """
    id: str
    name: str
    input: dict[str, Any]
    description: str = ""
    intent: str = ""
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "input": self.input,
            "tool_description": self.description,
            "intent": self.intent,
            "execute": False,
            "input_description": {},
        }


@dataclass
class ToolResult:
    """
    Result from an executed tool.
    
    When a tool has been executed (either auto-approved or user-approved),
    include it in AgentResult.executed_tools so the HelpDesk can track
    what was done.
    
    Attributes:
        id: Unique identifier matching the original tool call
        name: Name of the tool that was executed
        input: Parameters that were passed
        output: The result from the tool
        error: Error message if execution failed
    """
    id: str
    name: str
    input: dict[str, Any]
    output: str = ""
    error: str | None = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "input": self.input,
            "output": self.output,
        }


@dataclass
class AgentResult:
    """
    What your custom agent function returns.
    
    This is a simple container that gets translated to the HelpDesk
    protocol by serve(). You don't need to know the protocol details.
    
    Attributes:
        text: The response text to show the user
        pending_tools: Tool calls needing user approval
        executed_tools: Tools that were executed this turn
        metadata: Optional metadata (logged but not shown to user)
        
    Example - Simple response:
        return AgentResult(text="Here are your pods: nginx, redis, api")
        
    Example - Needs approval:
        return AgentResult(
            text="I need approval to delete the pod.",
            pending_tools=[
                ToolApproval(
                    id="tc_123",
                    name="delete_pod",
                    input={"name": "nginx-abc"},
                    description="Delete pod nginx-abc",
                )
            ],
        )
        
    Example - Tool was executed:
        return AgentResult(
            text="Pod deleted successfully.",
            executed_tools=[
                ToolResult(
                    id="tc_123",
                    name="delete_pod",
                    input={"name": "nginx-abc"},
                    output="pod 'nginx-abc' deleted",
                )
            ],
        )
    """
    text: str = ""
    pending_tools: list[ToolApproval] = field(default_factory=list)
    executed_tools: list[ToolResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @property
    def needs_approval(self) -> bool:
        """True if there are pending tool approvals."""
        return len(self.pending_tools) > 0
    
    def to_message(self) -> "AgentMessage":
        """
        Convert to AgentMessage (wire format for HelpDesk).
        
        This creates a Pydantic-validated AgentMessage suitable for
        JSON serialization and the HelpDesk protocol.
        
        Returns:
            AgentMessage ready for serialization
            
        Example:
            result = AgentResult(text="Here are your pods...")
            message = result.to_message()
            return message.model_dump()  # → JSON for HelpDesk
        """
        from dcaf.schemas.messages import AgentMessage, Data, ToolCall, ExecutedToolCall
        
        # Build tool_calls for pending approvals
        tool_calls = []
        for tc in self.pending_tools:
            tool_calls.append(ToolCall(
                id=tc.id,
                name=tc.name,
                input=tc.input,
                execute=False,
                tool_description=tc.description or "",
                intent=tc.intent,
                input_description={},
            ))
        
        # Build executed_tool_calls
        executed_tool_calls = []
        for tc in self.executed_tools:
            executed_tool_calls.append(ExecutedToolCall(
                id=tc.id,
                name=tc.name,
                input=tc.input,
                output=tc.output,
            ))
        
        # Build Data container
        data = Data(
            tool_calls=tool_calls,
            executed_tool_calls=executed_tool_calls,
            cmds=[],
            executed_cmds=[],
        )
        
        # Build meta_data
        meta_data = {
            "has_pending_approvals": self.needs_approval,
            "is_complete": not self.needs_approval,
        }
        if self.metadata:
            meta_data.update(self.metadata)
        
        return AgentMessage(
            content=self.text or "",
            data=data,
            meta_data=meta_data,
        )


# =============================================================================
# Helper for converting Agent responses to AgentResult
# =============================================================================

def from_agent_response(response) -> AgentResult:
    """
    Convert an Agent response to an AgentResult.
    
    This is useful when using Agent inside a custom function.
    
    Args:
        response: AgentResponse from Agent.run()
        
    Returns:
        AgentResult suitable for returning from a custom agent function
        
    Example:
        def my_agent(messages, context) -> AgentResult:
            agent = Agent(tools=[...])
            response = agent.run(messages)
            return from_agent_response(response)
    """
    pending = [
        ToolApproval(
            id=p.id,
            name=p.name,
            input=p.input,
            description=p.description,
        )
        for p in getattr(response, 'pending_tools', [])
    ]
    
    executed = [
        ToolResult(
            id=e.get('id', ''),
            name=e.get('name', ''),
            input=e.get('input', {}),
            output=e.get('output', ''),
        )
        for e in getattr(response, 'executed_tools', [])
    ]
    
    return AgentResult(
        text=response.text,
        pending_tools=pending,
        executed_tools=executed,
    )
