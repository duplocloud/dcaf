"""
Server Adapter - Bridge between Core Agent and FastAPI server.

This adapter allows a Core Agent to work with the existing
FastAPI server infrastructure, providing full compatibility
with the DuploCloud helpdesk integration.

Example:
    from dcaf.core import Agent
    from dcaf.core.adapters.inbound import ServerAdapter
    from dcaf.agent_server import create_chat_app
    
    agent = Agent(tools=[...])
    app = create_chat_app(ServerAdapter(agent))
"""

from typing import Dict, Any, List, Iterator
import logging

from ...agent import Agent
from ....schemas.messages import AgentMessage, ExecutedToolCall
from ....schemas.events import (
    StreamEvent,
    TextDeltaEvent,
    ToolCallsEvent,
    DoneEvent,
    ErrorEvent,
)

logger = logging.getLogger(__name__)


class ServerAdapter:
    """
    Adapts a Core Agent to work with the existing FastAPI server.
    
    This implements the AgentProtocol interface expected by
    `dcaf.agent_server.create_chat_app()`.
    
    The adapter:
    - Converts incoming message format to Core format
    - Runs the Core agent
    - Converts responses back to AgentMessage schema
    - Handles tool call approvals
    
    Args:
        agent: The Core Agent instance to wrap
        
    Example:
        from dcaf.core import Agent
        from dcaf.core.adapters.inbound import ServerAdapter
        from dcaf.agent_server import create_chat_app
        import uvicorn
        
        # Create your agent
        agent = Agent(
            tools=[list_pods, delete_pod],
            system_prompt="You are a Kubernetes assistant."
        )
        
        # Wrap it for the server
        adapter = ServerAdapter(agent)
        
        # Create and run the app
        app = create_chat_app(adapter)
        uvicorn.run(app, host="0.0.0.0", port=8000)
    """
    
    def __init__(self, agent: Agent):
        self.agent = agent
    
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        """
        Handle a synchronous chat request.
        
        This is called by the /api/sendMessage endpoint.
        
        Args:
            messages: The message payload from the server
                     Format: {"messages": [{"role": "...", "content": "..."}, ...]}
        
        Returns:
            AgentMessage with the response
        """
        logger.debug(f"ServerAdapter.invoke called with {len(messages.get('messages', []))} messages")
        
        # Extract messages list and platform context
        messages_list = messages.get("messages", [])
        platform_context = self._extract_platform_context(messages_list)
        
        # Check for approved tool calls that need to be processed
        executed_tool_calls = self._process_approved_tool_calls(messages_list, platform_context)
        
        # Convert to Core format (simple list of dicts with role/content)
        core_messages = self._convert_messages(messages_list)
        
        if not core_messages:
            return AgentMessage(content="No messages provided.")
        
        # Run the core agent
        try:
            response = self.agent.run(
                messages=core_messages,
                context=platform_context,
            )
            
            # Convert to AgentMessage using native to_message()
            agent_msg = response.to_message()
            
            # Add any executed tool calls from this request
            if executed_tool_calls:
                agent_msg.data.executed_tool_calls.extend(executed_tool_calls)
            
            # If there are pending approvals, ensure helpful content
            if response.needs_approval and not agent_msg.content:
                agent_msg.content = "I need your approval to execute the following tools:"
            
            return agent_msg
            
        except Exception as e:
            logger.exception(f"Error in agent execution: {e}")
            return AgentMessage(content=f"Error: {str(e)}")
    
    def invoke_stream(
        self, 
        messages: Dict[str, List[Dict[str, Any]]]
    ) -> Iterator[StreamEvent]:
        """
        Handle a streaming chat request.
        
        This is called by the /api/chat-stream endpoint.
        Uses true token-by-token streaming from the Agent.
        
        Args:
            messages: The message payload from the server
            
        Yields:
            StreamEvent objects for NDJSON streaming
        """
        logger.debug(f"ServerAdapter.invoke_stream called")
        
        # Extract messages list and platform context
        messages_list = messages.get("messages", [])
        platform_context = self._extract_platform_context(messages_list)
        
        # Convert to Core format
        core_messages = self._convert_messages(messages_list)
        
        if not core_messages:
            yield ErrorEvent(error="No messages provided")
            return
        
        try:
            # Use true streaming from the Agent
            for event in self.agent.run_stream(
                messages=core_messages,
                context=platform_context,
            ):
                # Events are already in the correct StreamEvent format
                yield event
                
        except Exception as e:
            logger.exception(f"Stream error: {e}")
            yield ErrorEvent(error=str(e))
    
    def _convert_messages(
        self, 
        messages_list: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Convert from server message format to Core format.
        
        Server format includes rich data (tool_calls, executed_cmds, etc.)
        Core format is simple: [{"role": "...", "content": "..."}]
        """
        core_messages = []
        
        for msg in messages_list:
            role = msg.get("role")
            content = msg.get("content", "")
            
            # Only include user and assistant messages
            if role in ["user", "assistant"]:
                core_messages.append({
                    "role": role,
                    "content": content,
                })
        
        return core_messages
    
    def _extract_platform_context(
        self, 
        messages_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extract platform context from the latest user message.
        
        The platform_context contains runtime info like tenant_name,
        k8s_namespace, AWS credentials, etc.
        """
        # Find the last user message
        for msg in reversed(messages_list):
            if msg.get("role") == "user":
                platform_context = msg.get("platform_context", {})
                if platform_context:
                    # Convert Pydantic model to dict if needed
                    if hasattr(platform_context, "model_dump"):
                        return platform_context.model_dump()
                    return platform_context
        return {}
    
    def _process_approved_tool_calls(
        self,
        messages_list: List[Dict[str, Any]],
        platform_context: Dict[str, Any],
    ) -> List[ExecutedToolCall]:
        """
        Process any approved tool calls from incoming messages.
        
        When the user approves tool calls, they come back in the
        message data. We execute them here and return results.
        """
        executed_tools = []
        
        if not messages_list:
            return executed_tools
        
        # Get the latest message's data
        latest_message = messages_list[-1]
        data = latest_message.get("data", {})
        tool_calls = data.get("tool_calls", [])
        
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            tool_input = tool_call.get("input", {})
            tool_id = tool_call.get("id")
            
            if tool_call.get("execute", False):
                # User approved - execute the tool
                result = self._execute_tool(tool_name, tool_input, platform_context)
                executed_tools.append(ExecutedToolCall(
                    id=tool_id,
                    name=tool_name,
                    input=tool_input,
                    output=result,
                ))
            elif tool_call.get("rejection_reason"):
                # User rejected
                executed_tools.append(ExecutedToolCall(
                    id=tool_id,
                    name=tool_name,
                    input=tool_input,
                    output=f"Tool rejected: {tool_call['rejection_reason']}",
                ))
        
        return executed_tools
    
    def _execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        platform_context: Dict[str, Any],
    ) -> str:
        """Execute a tool by name."""
        # Find the tool in the agent's tool list
        for tool in self.agent.tools:
            if getattr(tool, 'name', None) == tool_name:
                try:
                    if hasattr(tool, 'execute'):
                        return tool.execute(tool_input, platform_context)
                    elif callable(tool):
                        return tool(**tool_input)
                except Exception as e:
                    return f"Error executing {tool_name}: {str(e)}"
        
        return f"Tool '{tool_name}' not found"
